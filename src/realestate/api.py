from __future__ import annotations

import json
import os
import secrets
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from realestate.analyzers import score_properties
from realestate.auth import get_current_user
from realestate.models import Property
from realestate.valuation import estimate_remaining_balance, lookup_ugrc_value, _normalize_address_for_search, _get_rate
from realestate.store import DEFAULT_DB_PATH, PropertyStore
from realestate.geocoding import normalize_address
from realestate.sources import get_source

DISTRESS_SCORERS = [
    ("distress_stage", 2.0),
    ("loan_age", 1.5),
    ("equity_estimate", 1.5),
    ("time_pressure", 1.0),
    ("owner_occupied", 0.5),
]

app = FastAPI(title="Real Estate Deal Finder")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/refresh")
def refresh_data(user: dict = Depends(get_current_user)):
    src = get_source("meridian_nod")
    properties = src.fetch()

    for prop in properties:
        if not prop.normalized_address:
            prop.normalized_address = normalize_address(
                prop.address, prop.city, prop.state, prop.zip_code,
            )

    store = PropertyStore()
    result = store.upsert(properties)

    current_ids = {p.source_id for p in properties}
    removed = store.mark_removed("meridian_nod", current_ids)
    store.close()

    return {
        "fetched": len(properties),
        "new": result.new,
        "updated": result.updated,
        "unchanged": result.unchanged,
        "removed": removed,
    }


@app.post("/api/backfill-normalized-addresses")
def backfill_normalized_addresses(user: dict = Depends(get_current_user)):
    store = PropertyStore()
    rows = store.get_properties_missing_normalized_address()
    updated = 0
    failed = 0
    for row in rows:
        result = normalize_address(row["address"], row["city"], row["state"], row["zip_code"])
        if result:
            store.set_normalized_address(row["id"], result)
            updated += 1
        else:
            failed += 1
    store.close()
    return {"total": len(rows), "updated": updated, "failed": failed}


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DEFAULT_DB_PATH))
    conn.row_factory = sqlite3.Row
    # Ensure all tables exist
    from realestate.store import CREATE_TABLE, CREATE_CONTACTS_TABLE, CREATE_LEADS_TABLE, CREATE_LEAD_PHONES_TABLE, CREATE_SMS_TEMPLATES_TABLE, CREATE_MESSAGES_TABLE, CREATE_VALUATIONS_TABLE, CREATE_SHORT_CODES_TABLE
    conn.execute(CREATE_TABLE)
    conn.execute(CREATE_CONTACTS_TABLE)
    conn.execute(CREATE_LEADS_TABLE)
    conn.execute(CREATE_LEAD_PHONES_TABLE)
    conn.execute(CREATE_SMS_TEMPLATES_TABLE)
    conn.execute(CREATE_MESSAGES_TABLE)
    conn.execute(CREATE_VALUATIONS_TABLE)
    conn.execute(CREATE_SHORT_CODES_TABLE)
    # Migrate: add normalized_address if missing
    cols = [r[1] for r in conn.execute("PRAGMA table_info(properties)").fetchall()]
    if "normalized_address" not in cols:
        conn.execute("ALTER TABLE properties ADD COLUMN normalized_address TEXT")
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    data = json.loads(row["data"])
    data["_id"] = row["id"]
    data["_first_seen"] = row["first_seen"]
    data["_last_seen"] = row["last_seen"]
    data["_updated_at"] = row["updated_at"]
    data["_status"] = row["status"]
    data["normalized_address"] = row["normalized_address"]
    return data


def _score_results(rows: list, conn: sqlite3.Connection | None = None) -> list[dict]:
    properties = []
    row_meta = []
    property_ids = []
    for row in rows:
        prop = Property.model_validate_json(row["data"])
        properties.append(prop)
        property_ids.append(row["id"])
        row_meta.append({
            "_id": row["id"],
            "_first_seen": row["first_seen"],
            "_last_seen": row["last_seen"],
            "_updated_at": row["updated_at"],
            "_status": row["status"],
            "normalized_address": row["normalized_address"],
        })

    # Load contacts, valuations, and leads
    contacts = {}
    valuations = {}
    leads = {}
    if conn and property_ids:
        placeholders = ",".join("?" for _ in property_ids)
        contact_rows = conn.execute(
            f"SELECT * FROM contacts WHERE property_id IN ({placeholders})",
            property_ids,
        ).fetchall()
        contacts = {r["property_id"]: dict(r) for r in contact_rows}

        val_rows = conn.execute(
            f"SELECT * FROM valuations WHERE property_id IN ({placeholders})",
            property_ids,
        ).fetchall()
        valuations = {r["property_id"]: dict(r) for r in val_rows}

        lead_rows = conn.execute(
            f"SELECT * FROM leads WHERE property_id IN ({placeholders})",
            property_ids,
        ).fetchall()
        leads = {r["property_id"]: dict(r) for r in lead_rows}

    # Inject valuation data into properties so scorers can use it
    for prop, pid in zip(properties, property_ids):
        val = valuations.get(pid)
        if val and prop.raw is not None:
            prop.raw["_equity_percent"] = val.get("equity_percent")
            prop.raw["_estimated_equity"] = val.get("estimated_equity")
            prop.raw["_estimated_market_value"] = val.get("estimated_market_value")
            prop.raw["_remaining_balance"] = val.get("remaining_balance")

    scored = score_properties(properties, scorers=DISTRESS_SCORERS)

    results = []
    meta_by_key = {}
    id_by_key = {}
    for prop, meta, pid in zip(properties, row_meta, property_ids):
        meta_by_key[(prop.source, prop.source_id)] = meta
        id_by_key[(prop.source, prop.source_id)] = pid

    for sp in scored:
        prop_dict = sp.property.model_dump(mode="json")
        key = (sp.property.source, sp.property.source_id)
        meta = meta_by_key.get(key, {})
        prop_dict.update(meta)
        prop_dict["_score"] = sp.total_score
        prop_dict["_scores"] = {s.name: {"value": s.value, "detail": s.detail} for s in sp.scores}

        pid = id_by_key.get(key)
        contact = contacts.get(pid)
        if contact:
            prop_dict["_contact"] = {
                "phone_1": contact["phone_1"],
                "phone_1_type": contact["phone_1_type"],
                "phone_2": contact["phone_2"],
                "phone_2_type": contact["phone_2_type"],
                "phone_3": contact["phone_3"],
                "phone_3_type": contact["phone_3_type"],
                "email_1": contact["email_1"],
                "email_2": contact["email_2"],
                "skip_source": contact["skip_source"],
                "skip_date": contact["skip_date"],
            }
        else:
            prop_dict["_contact"] = None

        valuation = valuations.get(pid)
        if valuation:
            prop_dict["_valuation"] = {
                "assessed_value": valuation["assessed_value"],
                "estimated_market_value": valuation["estimated_market_value"],
                "remaining_balance": valuation["remaining_balance"],
                "estimated_equity": valuation["estimated_equity"],
                "equity_percent": valuation["equity_percent"],
                "bldg_sqft": valuation["bldg_sqft"],
                "built_yr": valuation["built_yr"],
                "monthly_payment": valuation["monthly_payment"],
                "rate_used": valuation["rate_used"],
                "valuation_date": valuation["valuation_date"],
            }
        else:
            prop_dict["_valuation"] = None

        lead = leads.get(pid)
        if lead:
            lead_phones = []
            if conn:
                phone_rows = conn.execute(
                    "SELECT * FROM lead_phones WHERE lead_id = ? ORDER BY position, id",
                    (lead["id"],),
                ).fetchall()
                lead_phones = [{"id": r["id"], "phone": r["phone"], "type": r["type"]} for r in phone_rows]
            prop_dict["_lead"] = {
                "id": lead["id"],
                "status": lead["status"],
                "notes": lead["notes"],
                "phones": lead_phones,
                "email_1": lead["email_1"],
                "email_2": lead["email_2"],
                "custom_data": lead["custom_data"],
                "created_at": lead["created_at"],
                "updated_at": lead["updated_at"],
            }
        else:
            prop_dict["_lead"] = None

        results.append(prop_dict)

    return results


@app.get("/api/properties")
def list_properties(
    source: str | None = None,
    county: str | None = None,
    city: str | None = None,
    doc_type: str | None = None,
    lien_position: str | None = None,
    property_type_raw: str | None = None,
    status: str = "active",
    user: dict = Depends(get_current_user),
):
    conn = _get_conn()
    query = "SELECT * FROM properties WHERE status = ?"
    params: list = [status]

    if source:
        query += " AND source = ?"
        params.append(source)
    if city:
        query += " AND LOWER(city) = LOWER(?)"
        params.append(city)
    if county:
        query += " AND LOWER(json_extract(data, '$.raw.county')) = LOWER(?)"
        params.append(county)
    if lien_position:
        query += " AND json_extract(data, '$.raw.lien_position') = ?"
        params.append(lien_position)
    if doc_type:
        query += " AND LOWER(json_extract(data, '$.raw.doc_type')) LIKE LOWER(?)"
        params.append(f"%{doc_type}%")
    if property_type_raw:
        query += " AND LOWER(json_extract(data, '$.raw.property_type_raw')) = LOWER(?)"
        params.append(property_type_raw)

    query += " ORDER BY first_seen DESC"
    rows = conn.execute(query, params).fetchall()
    result = _score_results(rows, conn)
    conn.close()
    return result


@app.get("/api/properties/{property_id}")
def get_property(property_id: int, user: dict = Depends(get_current_user)):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM properties WHERE id = ?", (property_id,)).fetchone()
    if not row:
        conn.close()
        return {"error": "Not found"}, 404
    results = _score_results([row], conn)
    conn.close()
    return results[0] if results else {"error": "Not found"}


@app.get("/api/stats")
def get_stats(user: dict = Depends(get_current_user)):
    conn = _get_conn()

    total = conn.execute(
        "SELECT COUNT(*) as cnt FROM properties WHERE status = 'active'"
    ).fetchone()["cnt"]

    by_county = conn.execute("""
        SELECT json_extract(data, '$.raw.county') as county, COUNT(*) as cnt
        FROM properties WHERE status = 'active' AND source = 'meridian_nod'
        GROUP BY county ORDER BY cnt DESC
    """).fetchall()

    by_doc_type = conn.execute("""
        SELECT json_extract(data, '$.raw.doc_type') as doc_type, COUNT(*) as cnt
        FROM properties WHERE status = 'active' AND source = 'meridian_nod'
        GROUP BY doc_type ORDER BY cnt DESC
    """).fetchall()

    by_source = conn.execute("""
        SELECT source, COUNT(*) as cnt
        FROM properties WHERE status = 'active'
        GROUP BY source ORDER BY cnt DESC
    """).fetchall()

    by_lien = conn.execute("""
        SELECT json_extract(data, '$.raw.lien_position') as lien, COUNT(*) as cnt
        FROM properties WHERE status = 'active' AND source = 'meridian_nod'
        AND json_extract(data, '$.raw.lien_position') != ''
        AND json_extract(data, '$.raw.lien_position') IS NOT NULL
        GROUP BY lien ORDER BY lien
    """).fetchall()

    cities = conn.execute("""
        SELECT DISTINCT city FROM properties
        WHERE status = 'active' ORDER BY city
    """).fetchall()

    leads_count = conn.execute("SELECT COUNT(*) as cnt FROM leads").fetchone()["cnt"]

    conn.close()

    return {
        "total": total,
        "by_county": [{"county": r["county"], "count": r["cnt"]} for r in by_county],
        "by_doc_type": [{"doc_type": r["doc_type"], "count": r["cnt"]} for r in by_doc_type],
        "by_source": [{"source": r["source"], "count": r["cnt"]} for r in by_source],
        "by_lien_position": [{"lien": r["lien"], "count": r["cnt"]} for r in by_lien],
        "cities": [r["city"] for r in cities],
        "leads_count": leads_count,
    }


# Utah assessed values are typically 85-95% of market value
MARKET_ADJUSTMENT = 1.10  # Conservative 10% uplift


@app.post("/api/properties/{property_id}/equity")
def estimate_equity(property_id: int, user: dict = Depends(get_current_user)):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM properties WHERE id = ?", (property_id,)).fetchone()
    if not row:
        conn.close()
        return {"error": "Property not found"}

    data = json.loads(row["data"])
    raw = data.get("raw", {})

    address = data.get("address", "")
    county = raw.get("county", "")
    orig_mtg = raw.get("orig_mtg_amt")
    orig_rec_date_str = raw.get("orig_rec_date", "")

    # Step 1: Get assessed value from UGRC
    ugrc = lookup_ugrc_value(address, county, data.get("city", ""))
    assessed_value = ugrc.get("total_mkt_value")
    estimated_market = round(assessed_value * MARKET_ADJUSTMENT) if assessed_value else None

    # Step 2: Estimate remaining balance from amortization
    remaining = None
    amort = {}
    if orig_mtg and orig_rec_date_str:
        try:
            m, d, y = orig_rec_date_str.split("/")
            orig_date = date(int(y), int(m), int(d))
            amort = estimate_remaining_balance(orig_mtg, orig_date)
            remaining = amort.get("remaining_balance")
        except (ValueError, IndexError):
            pass

    # Step 3: Calculate equity
    estimated_equity = None
    equity_percent = None
    if estimated_market and remaining is not None:
        estimated_equity = round(estimated_market - remaining)
        equity_percent = round((estimated_equity / estimated_market) * 100, 1) if estimated_market > 0 else None

    # Store it
    now = datetime.now(UTC).isoformat()
    existing = conn.execute(
        "SELECT id FROM valuations WHERE property_id = ?", (property_id,)
    ).fetchone()

    val_data = {
        "assessed_value": assessed_value,
        "estimated_market_value": estimated_market,
        "remaining_balance": remaining,
        "estimated_equity": estimated_equity,
        "equity_percent": equity_percent,
        "bldg_sqft": ugrc.get("bldg_sqft"),
        "built_yr": ugrc.get("built_yr"),
        "monthly_payment": amort.get("monthly_payment"),
        "rate_used": amort.get("rate_used"),
        "valuation_date": now,
        "raw_data": json.dumps({"ugrc": ugrc, "amort": amort}),
    }

    with conn:
        if existing:
            sets = ", ".join(f"{k}=?" for k in val_data)
            conn.execute(
                f"UPDATE valuations SET {sets} WHERE property_id=?",
                list(val_data.values()) + [property_id],
            )
        else:
            cols = ", ".join(["property_id"] + list(val_data.keys()))
            placeholders = ", ".join(["?"] * (len(val_data) + 1))
            conn.execute(
                f"INSERT INTO valuations ({cols}) VALUES ({placeholders})",
                [property_id] + list(val_data.values()),
            )

    conn.close()

    return {
        "success": True,
        "valuation": {k: v for k, v in val_data.items() if k != "raw_data"},
    }


@app.post("/api/properties/{property_id}/short-code")
def create_short_code(property_id: int, user: dict = Depends(get_current_user)):
    conn = _get_conn()
    row = conn.execute("SELECT id FROM properties WHERE id = ?", (property_id,)).fetchone()
    if not row:
        conn.close()
        return {"error": "Property not found"}

    existing = conn.execute(
        "SELECT code FROM short_codes WHERE property_id = ?", (property_id,)
    ).fetchone()
    if existing:
        conn.close()
        return {"code": existing["code"]}

    code = secrets.token_urlsafe(6)
    now = datetime.now(UTC).isoformat()
    with conn:
        conn.execute(
            "INSERT INTO short_codes (code, property_id, created_at) VALUES (?, ?, ?)",
            (code, property_id, now),
        )
    conn.close()
    return {"code": code}


@app.get("/api/intake/link/{code}")
def resolve_short_code(code: str):
    conn = _get_conn()
    row = conn.execute(
        "SELECT sc.property_id, p.data, p.address, p.city, p.state, p.zip_code FROM short_codes sc "
        "JOIN properties p ON p.id = sc.property_id WHERE sc.code = ?",
        (code,),
    ).fetchone()
    if not row:
        conn.close()
        return {"error": "Not found"}

    with conn:
        conn.execute(
            "UPDATE short_codes SET click_count = click_count + 1 WHERE code = ?",
            (code,),
        )

    data = json.loads(row["data"])
    raw = data.get("raw", {})

    orig_date_str = None
    orig_date_raw = raw.get("orig_rec_date", "")
    if orig_date_raw:
        try:
            m, d, y = orig_date_raw.split("/")
            orig_date_str = f"{y}-{m.zfill(2)}"
        except (ValueError, IndexError):
            pass

    street = data.get("address", row["address"])
    city = data.get("city", row["city"])
    state = data.get("state", row["state"])
    zip_code = data.get("zip_code", row["zip_code"])
    formatted = f"{street}, {city}, {state} {zip_code}"

    conn.close()
    return {
        "address": formatted,
        "street": street,
        "city": city,
        "county": raw.get("county", ""),
        "origination_date": orig_date_str,
        "original_loan_amount": raw.get("orig_mtg_amt"),
    }


@app.post("/api/intake/valuation")
def intake_valuation(body: dict):
    """Public endpoint for the intake flow.

    Checks the local DB first for known properties (NOD records with mortgage data),
    then falls back to UGRC for assessed value.
    """
    address = body.get("address", "")
    county = body.get("county", "")
    city = body.get("city", "")
    user_orig_date = body.get("origination_date")
    last_month_paid = body.get("last_month_paid")
    user_loan_amount = body.get("original_loan_amount")
    user_home_value = body.get("estimated_home_value")
    user_loan_balance = body.get("loan_balance")

    estimated_market = None
    bldg_sqft = None
    built_yr = None
    source = None
    orig_mtg = None
    orig_date_str = None
    db_match = False

    # Primary: check local DB for NOD records
    conn = _get_conn()
    normalized = _normalize_address_for_search(address)

    # Extract street number + street name for fuzzy matching
    # "804 BOURDEAUX DR" -> number "804", name "BOURDEAUX"
    addr_parts = normalized.split()
    street_num = addr_parts[0] if addr_parts else ""
    # Strip direction prefixes and suffixes to get the core street name
    core_words = [w for w in addr_parts[1:] if w not in (
        "N", "S", "E", "W", "NE", "NW", "SE", "SW",
        "ST", "AVE", "DR", "RD", "BLVD", "LN", "CT", "CIR", "PL", "WAY", "TRL", "PKWY",
    )]
    core_name = " ".join(core_words)

    row = conn.execute(
        "SELECT data FROM properties WHERE UPPER(address) = ? AND status = 'active'",
        (normalized,),
    ).fetchone()
    if not row:
        row = conn.execute(
            "SELECT data FROM properties WHERE UPPER(address) LIKE ? AND status = 'active'",
            (f"{normalized}%",),
        ).fetchone()
    if not row and street_num and core_name:
        row = conn.execute(
            "SELECT data FROM properties WHERE UPPER(address) LIKE ? AND status = 'active'",
            (f"{street_num}%{core_name}%",),
        ).fetchone()
    conn.close()

    if row:
        data = json.loads(row["data"])
        raw = data.get("raw", {})
        orig_mtg = raw.get("orig_mtg_amt")
        orig_date_raw = raw.get("orig_rec_date", "")
        if orig_date_raw:
            try:
                m, d, y = orig_date_raw.split("/")
                orig_date_str = f"{y}-{m.zfill(2)}"
            except (ValueError, IndexError):
                pass
        db_match = True

    # Use user-provided values if DB didn't have them
    if not orig_date_str and user_orig_date:
        orig_date_str = user_orig_date
    if not orig_mtg and user_loan_amount:
        orig_mtg = float(user_loan_amount)

    # Get property value from UGRC
    if county:
        ugrc = lookup_ugrc_value(address, county, city)
        assessed_value = ugrc.get("total_mkt_value")
        if assessed_value:
            estimated_market = round(assessed_value * MARKET_ADJUSTMENT)
            bldg_sqft = ugrc.get("bldg_sqft")
            built_yr = ugrc.get("built_yr")
            source = "ugrc"

    if not estimated_market and user_home_value:
        estimated_market = round(float(user_home_value))
        source = "user"

    # Amortize to get monthly payment; override balance with user-provided value if given
    remaining = None
    amort = {}
    if orig_mtg and orig_date_str:
        try:
            parts = orig_date_str.split("-")
            orig_date = date(int(parts[0]), int(parts[1]), 1)
            amort = estimate_remaining_balance(float(orig_mtg), orig_date)
            remaining = amort.get("remaining_balance")
        except (ValueError, IndexError):
            pass
    if user_loan_balance:
        remaining = round(float(user_loan_balance))

    monthly_payment = amort.get("monthly_payment")
    if not monthly_payment and remaining and orig_date_str:
        try:
            parts = orig_date_str.split("-")
            orig_date = date(int(parts[0]), int(parts[1]), 1)
            rate = _get_rate(orig_date.year)
            monthly_rate = rate / 100 / 12
            months_elapsed = (date.today().year - orig_date.year) * 12 + (date.today().month - orig_date.month)
            months_remaining = max(1, 360 - months_elapsed)
            if monthly_rate > 0:
                monthly_payment = round(
                    remaining * (monthly_rate * (1 + monthly_rate) ** months_remaining)
                    / ((1 + monthly_rate) ** months_remaining - 1), 2
                )
            else:
                monthly_payment = round(remaining / months_remaining, 2)
        except (ValueError, IndexError):
            pass
    months_behind = None
    estimated_arrears = None
    late_fees = None
    legal_fees = None
    total_fees = None
    equity_after_fees = None

    if last_month_paid and monthly_payment:
        try:
            lmp_parts = last_month_paid.split("-")
            lmp_date = date(int(lmp_parts[0]), int(lmp_parts[1]), 1)
            today = date.today()
            months_behind = (today.year - lmp_date.year) * 12 + (today.month - lmp_date.month)
            months_behind = max(0, months_behind)

            estimated_arrears = round(months_behind * monthly_payment, 2)
            late_fees = round(estimated_arrears * 0.05, 2)
            legal_fees = 3000
            total_fees = round(estimated_arrears + late_fees + legal_fees, 2)
        except (ValueError, IndexError):
            pass

    estimated_equity = None
    equity_percent = None
    if estimated_market and remaining is not None:
        estimated_equity = round(estimated_market - remaining)
        equity_percent = round((estimated_equity / estimated_market) * 100, 1) if estimated_market > 0 else None
        if total_fees is not None:
            equity_after_fees = round(estimated_equity - total_fees)

    return {
        "estimated_market_value": estimated_market,
        "remaining_balance": remaining,
        "estimated_equity": estimated_equity,
        "equity_percent": equity_percent,
        "monthly_payment": monthly_payment,
        "rate_used": amort.get("rate_used"),
        "bldg_sqft": bldg_sqft,
        "built_yr": built_yr,
        "origination_date": orig_date_str,
        "months_behind": months_behind,
        "estimated_arrears": estimated_arrears,
        "late_fees": late_fees,
        "legal_fees": legal_fees,
        "total_fees": total_fees,
        "equity_after_fees": equity_after_fees,
        "source": source,
        "db_match": db_match,
    }


@app.post("/api/intake/submit")
def intake_submit(body: dict):
    """Public endpoint: save an intake lead and send notification."""
    email = body.get("email", "")
    intent = body.get("intent", "")
    selected_structure = body.get("selected_structure", "")
    recommended_structure = body.get("recommended_structure") or ""
    facts = body.get("property_facts", {})

    address = facts.get("address", "") or facts.get("street", "")
    city = facts.get("city", "")
    county = facts.get("county", "")

    if not email or not address:
        return {"error": "email and address are required"}

    conn = _get_conn()

    # Try to match existing lead by email first
    row = None
    if email:
        lead_row = conn.execute(
            "SELECT property_id FROM leads WHERE email_1 = ? LIMIT 1",
            (email,),
        ).fetchone()
        if lead_row:
            row = conn.execute(
                "SELECT id FROM properties WHERE id = ? AND status = 'active'",
                (lead_row["property_id"],),
            ).fetchone()

    # Fall back to property address matching
    if not row and address:
        row = conn.execute(
            "SELECT id FROM properties WHERE normalized_address = ? AND status = 'active'",
            (address,),
        ).fetchone()

        if not row:
            normalized = _normalize_address_for_search(address)
            addr_parts = normalized.split()
            street_num = addr_parts[0] if addr_parts else ""
            core_words = [w for w in addr_parts[1:] if w not in (
                "N", "S", "E", "W", "NE", "NW", "SE", "SW",
                "ST", "AVE", "DR", "RD", "BLVD", "LN", "CT", "CIR", "PL", "WAY", "TRL", "PKWY",
            )]
            core_name = " ".join(core_words)

            row = conn.execute(
                "SELECT id FROM properties WHERE UPPER(address) = ? AND status = 'active'",
                (normalized,),
            ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT id FROM properties WHERE UPPER(address) LIKE ? AND status = 'active'",
                    (f"{normalized}%",),
                ).fetchone()
            if not row and street_num and core_name:
                row = conn.execute(
                    "SELECT id FROM properties WHERE UPPER(address) LIKE ? AND status = 'active'",
                    (f"%{street_num}%{core_name}%",),
                ).fetchone()

    if row:
        property_id = row["id"]
    else:
        # Create a new property record from intake data
        now = datetime.now(UTC).isoformat()
        prop_data = {
            "source": "intake",
            "source_id": f"intake-{secrets.token_urlsafe(8)}",
            "address": address,
            "normalized_address": address,
            "city": city,
            "state": "",
            "zip_code": "",
            "price": facts.get("estimatedValue") or 0,
            "raw": {
                "county": county,
                "intent": intent,
                "selected_structure": selected_structure,
                "recommended_structure": recommended_structure,
            },
        }
        with conn:
            conn.execute(
                """INSERT INTO properties (source, source_id, address, city, state, zip_code, price, normalized_address, data, first_seen, last_seen, updated_at, status)
                   VALUES (?, ?, ?, ?, '', '', ?, ?, ?, ?, ?, ?, 'active')""",
                (
                    "intake",
                    prop_data["source_id"],
                    address,
                    city,
                    prop_data["price"],
                    address,
                    json.dumps(prop_data),
                    now, now, now,
                ),
            )
        property_id = conn.execute(
            "SELECT id FROM properties WHERE source = ? AND source_id = ?",
            ("intake", prop_data["source_id"]),
        ).fetchone()["id"]

    # Create or update lead
    existing_lead = conn.execute(
        "SELECT * FROM leads WHERE property_id = ?", (property_id,)
    ).fetchone()

    custom = json.dumps({
        "intent": intent,
        "selected_structure": selected_structure,
        "recommended_structure": recommended_structure,
        "property_facts": facts,
    })
    now = datetime.now(UTC).isoformat()

    if existing_lead:
        lead_id = existing_lead["id"]
        with conn:
            conn.execute(
                "UPDATE leads SET email_1 = ?, custom_data = ?, updated_at = ? WHERE id = ?",
                (email, custom, now, lead_id),
            )
    else:
        with conn:
            conn.execute(
                """INSERT INTO leads (property_id, status, email_1, custom_data, created_at, updated_at)
                   VALUES (?, 'new', ?, ?, ?, ?)""",
                (property_id, email, custom, now, now),
            )
        lead_id = conn.execute(
            "SELECT id FROM leads WHERE property_id = ?", (property_id,)
        ).fetchone()["id"]

    # Create notification
    est_value = facts.get("estimatedValue")
    loan_balance = facts.get("loanBalance")
    structure_label = selected_structure
    if recommended_structure and recommended_structure != selected_structure:
        structure_label = f"{selected_structure} (recommended: {recommended_structure})"
    notif_body = f"{address} — {email} — {structure_label}"
    if est_value:
        notif_body += f" | Value: ${est_value:,.0f}"
    if loan_balance:
        notif_body += f" | Balance: ${loan_balance:,.0f}"

    with conn:
        conn.execute(
            "INSERT INTO notifications (type, title, body, lead_id, created_at) VALUES (?, ?, ?, ?, ?)",
            ("intake_lead", "New intake lead", notif_body, lead_id, now),
        )

    conn.close()

    # Send SMS via Quo
    notify_phone = os.environ.get("INTAKE_NOTIFY_PHONE", "")
    quo_api_key = os.environ.get("QUO_API_KEY", "")
    quo_from = os.environ.get("QUO_PHONE_NUMBER", "")
    if notify_phone and quo_api_key and quo_from:
        import requests as _req
        sms_body = f"New intake lead!\n📍 {address}\n📧 {email}\n🏠 {structure_label}"
        if est_value:
            sms_body += f"\n💰 Value: ${est_value:,.0f}"
        if loan_balance:
            sms_body += f" | Balance: ${loan_balance:,.0f}"
        try:
            _req.post(
                "https://api.openphone.com/v1/messages",
                headers={"Authorization": quo_api_key, "Content-Type": "application/json"},
                json={"content": sms_body, "from": quo_from, "to": [notify_phone]},
                timeout=10,
            )
        except Exception as e:
            print(f"[INTAKE] Quo SMS failed: {e}")

    return {"id": lead_id}


@app.get("/api/notifications")
def list_notifications(unread_only: bool = False, user: dict = Depends(get_current_user)):
    store = PropertyStore()
    notifications = store.get_notifications(unread_only=unread_only)
    store.close()
    return notifications


@app.put("/api/notifications/{notification_id}/read")
def mark_notification_read(notification_id: int, user: dict = Depends(get_current_user)):
    store = PropertyStore()
    store.mark_notification_read(notification_id)
    store.close()
    return {"success": True}


@app.get("/api/notifications/unread-count")
def unread_notification_count(user: dict = Depends(get_current_user)):
    store = PropertyStore()
    count = store.get_unread_count()
    store.close()
    return {"count": count}


LEAD_STATUSES = ["new", "contacted", "callback", "interested", "negotiating", "under_contract", "closed", "dead"]


@app.post("/api/properties/{property_id}/create-lead")
def create_lead(property_id: int, user: dict = Depends(get_current_user)):
    """Create a lead from a property."""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM properties WHERE id = ?", (property_id,)).fetchone()
    if not row:
        conn.close()
        return {"error": "Property not found"}

    existing = conn.execute("SELECT * FROM leads WHERE property_id = ?", (property_id,)).fetchone()
    if existing:
        conn.close()
        return {"lead": dict(existing)}

    now = datetime.now(UTC).isoformat()
    with conn:
        conn.execute(
            "INSERT INTO leads (property_id, status, created_at, updated_at) VALUES (?, 'new', ?, ?)",
            (property_id, now, now),
        )

    lead = conn.execute("SELECT * FROM leads WHERE property_id = ?", (property_id,)).fetchone()
    conn.close()
    return {"lead": dict(lead)}


@app.put("/api/leads/{lead_id}")
def update_lead(lead_id: int, body: dict, user: dict = Depends(get_current_user)):
    """Update a lead's status, notes, contact info, or custom data."""
    conn = _get_conn()
    lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    if not lead:
        conn.close()
        return {"error": "Lead not found"}

    allowed = {
        "status", "notes", "email_1", "email_2", "custom_data",
    }
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        conn.close()
        return {"lead": dict(lead)}

    updates["updated_at"] = datetime.now(UTC).isoformat()
    sets = ", ".join(f"{k}=?" for k in updates)
    vals = list(updates.values()) + [lead_id]

    with conn:
        conn.execute(f"UPDATE leads SET {sets} WHERE id=?", vals)

    updated = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    conn.close()
    return {"lead": dict(updated)}


@app.post("/api/leads/{lead_id}/phones")
def add_lead_phone(lead_id: int, body: dict, user: dict = Depends(get_current_user)):
    """Add a phone number to a lead."""
    conn = _get_conn()
    lead = conn.execute("SELECT id FROM leads WHERE id = ?", (lead_id,)).fetchone()
    if not lead:
        conn.close()
        return {"error": "Lead not found"}

    phone = body.get("phone", "")
    phone_type = body.get("type", "")
    max_pos = conn.execute(
        "SELECT COALESCE(MAX(position), -1) as mp FROM lead_phones WHERE lead_id = ?",
        (lead_id,),
    ).fetchone()["mp"]

    with conn:
        conn.execute(
            "INSERT INTO lead_phones (lead_id, phone, type, position) VALUES (?, ?, ?, ?)",
            (lead_id, phone, phone_type, max_pos + 1),
        )
    row = conn.execute(
        "SELECT * FROM lead_phones WHERE lead_id = ? ORDER BY id DESC LIMIT 1",
        (lead_id,),
    ).fetchone()
    conn.close()
    return {"phone": {"id": row["id"], "phone": row["phone"], "type": row["type"]}}


@app.put("/api/leads/{lead_id}/phones/{phone_id}")
def update_lead_phone(lead_id: int, phone_id: int, body: dict, user: dict = Depends(get_current_user)):
    """Update a phone number on a lead."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM lead_phones WHERE id = ? AND lead_id = ?", (phone_id, lead_id)
    ).fetchone()
    if not row:
        conn.close()
        return {"error": "Phone not found"}

    updates = {}
    if "phone" in body:
        updates["phone"] = body["phone"]
    if "type" in body:
        updates["type"] = body["type"]

    if updates:
        sets = ", ".join(f"{k}=?" for k in updates)
        vals = list(updates.values()) + [phone_id]
        with conn:
            conn.execute(f"UPDATE lead_phones SET {sets} WHERE id=?", vals)

    updated = conn.execute("SELECT * FROM lead_phones WHERE id = ?", (phone_id,)).fetchone()
    conn.close()
    return {"phone": {"id": updated["id"], "phone": updated["phone"], "type": updated["type"]}}


@app.delete("/api/leads/{lead_id}/phones/{phone_id}")
def delete_lead_phone(lead_id: int, phone_id: int, user: dict = Depends(get_current_user)):
    """Remove a phone number from a lead."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM lead_phones WHERE id = ? AND lead_id = ?", (phone_id, lead_id)
    ).fetchone()
    if not row:
        conn.close()
        return {"error": "Phone not found"}

    with conn:
        conn.execute("DELETE FROM lead_phones WHERE id = ?", (phone_id,))
    conn.close()
    return {"success": True}


@app.get("/api/leads")
def list_leads(status: str | None = None, user: dict = Depends(get_current_user)):
    """List all leads, optionally filtered by status."""
    conn = _get_conn()
    query = """
        SELECT l.*, p.data, p.address, p.city,
               v.assessed_value, v.estimated_market_value, v.remaining_balance,
               v.estimated_equity, v.equity_percent, v.bldg_sqft, v.built_yr,
               v.monthly_payment, v.rate_used
        FROM leads l
        JOIN properties p ON p.id = l.property_id
        LEFT JOIN valuations v ON v.property_id = l.property_id
    """
    params = []
    if status:
        query += " WHERE l.status = ?"
        params.append(status)
    query += " ORDER BY l.updated_at DESC"

    rows = conn.execute(query, params).fetchall()

    # Collect lead IDs to batch-load phones
    lead_ids = [r["id"] for r in rows]
    phones_by_lead = {}
    if lead_ids:
        ph_placeholders = ",".join("?" for _ in lead_ids)
        phone_rows = conn.execute(
            f"SELECT * FROM lead_phones WHERE lead_id IN ({ph_placeholders}) ORDER BY position, id",
            lead_ids,
        ).fetchall()
        for pr in phone_rows:
            phones_by_lead.setdefault(pr["lead_id"], []).append(
                {"id": pr["id"], "phone": pr["phone"], "type": pr["type"]}
            )

    conn.close()

    results = []
    for r in rows:
        lead = {k: r[k] for k in r.keys() if k not in ("data",)}
        lead["property_data"] = json.loads(r["data"])
        lead["phones"] = phones_by_lead.get(r["id"], [])
        if r["estimated_market_value"] is not None or r["remaining_balance"] is not None:
            lead["valuation"] = {
                "assessed_value": r["assessed_value"],
                "estimated_market_value": r["estimated_market_value"],
                "remaining_balance": r["remaining_balance"],
                "estimated_equity": r["estimated_equity"],
                "equity_percent": r["equity_percent"],
                "bldg_sqft": r["bldg_sqft"],
                "built_yr": r["built_yr"],
                "monthly_payment": r["monthly_payment"],
                "rate_used": r["rate_used"],
            }
        else:
            lead["valuation"] = None
        results.append(lead)
    return results


@app.post("/api/messages/send")
def send_message(body: dict, user: dict = Depends(get_current_user)):
    """Send an SMS or email to a lead."""
    from realestate.messaging import send_sms, send_email, get_twilio_number, get_sendgrid_config

    lead_id = body.get("lead_id")
    channel = body.get("channel")  # "sms" or "email"
    to = body.get("to", "")
    subject = body.get("subject", "")
    text = body.get("body", "")

    if not lead_id or not channel or not to or not text:
        return {"error": "Missing required fields: lead_id, channel, to, body"}

    conn = _get_conn()
    lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    if not lead:
        conn.close()
        return {"error": "Lead not found"}

    if channel == "sms":
        result = send_sms(to, text)
        from_addr = get_twilio_number()
    elif channel == "email":
        result = send_email(to, subject, text)
        _, from_addr = get_sendgrid_config()
    else:
        conn.close()
        return {"error": f"Unknown channel: {channel}"}

    if not result.get("success"):
        conn.close()
        return {"error": result.get("error", "Send failed")}

    now = datetime.now(UTC).isoformat()
    external_id = result.get("sid") or result.get("message_id") or ""

    with conn:
        conn.execute(
            """INSERT INTO messages
               (lead_id, direction, channel, to_addr, from_addr, subject, body, status, external_id, created_at)
               VALUES (?, 'outbound', ?, ?, ?, ?, ?, 'sent', ?, ?)""",
            (lead_id, channel, to, from_addr, subject, text, external_id, now),
        )

    msg = conn.execute("SELECT * FROM messages ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return {"success": True, "message": dict(msg)}


@app.get("/api/messages/{lead_id}")
def get_messages(lead_id: int, user: dict = Depends(get_current_user)):
    """Get all messages for a lead."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM messages WHERE lead_id = ? ORDER BY created_at ASC",
        (lead_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/messaging/status")
def messaging_status(user: dict = Depends(get_current_user)):
    """Check if Twilio and SendGrid are configured."""
    from realestate.messaging import get_twilio_number, get_sendgrid_config
    import os

    twilio_ok = bool(os.environ.get("TWILIO_ACCOUNT_SID") and os.environ.get("TWILIO_AUTH_TOKEN") and get_twilio_number())
    sg_key, sg_from = get_sendgrid_config()
    sendgrid_ok = bool(sg_key and sg_from)

    return {
        "twilio": twilio_ok,
        "twilio_number": get_twilio_number() if twilio_ok else None,
        "sendgrid": sendgrid_ok,
        "sendgrid_from": sg_from if sendgrid_ok else None,
    }


DEFAULT_SMS_TEMPLATES = [
    {"label": "Initial Outreach", "body": "Hi {name}, my name is Ty. I came across your property at {address} and wanted to reach out. I help homeowners explore options when they're facing difficult situations with their mortgage. No pressure at all \u2014 just wanted to see if there's anything I can help with. Feel free to call or text me back anytime."},
    {"label": "Follow Up", "body": "Hi {name}, I reached out a few days ago about your property at {address}. I know things can get busy \u2014 just wanted to check in and see if you had any questions or wanted to chat. I'm happy to help however I can."},
    {"label": "Callback Reminder", "body": "Hi {name}, just a quick reminder about our chat regarding {address}. Looking forward to connecting \u2014 let me know what time works best for you."},
]


@app.get("/api/sms-templates")
def list_sms_templates(user: dict = Depends(get_current_user)):
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM sms_templates ORDER BY position, id").fetchall()
    if not rows:
        # Seed defaults on first access
        with conn:
            for i, t in enumerate(DEFAULT_SMS_TEMPLATES):
                conn.execute(
                    "INSERT INTO sms_templates (label, body, position) VALUES (?, ?, ?)",
                    (t["label"], t["body"], i),
                )
        rows = conn.execute("SELECT * FROM sms_templates ORDER BY position, id").fetchall()
    conn.close()
    return [{"id": r["id"], "label": r["label"], "body": r["body"]} for r in rows]


@app.post("/api/sms-templates")
def create_sms_template(body: dict, user: dict = Depends(get_current_user)):
    conn = _get_conn()
    label = body.get("label", "New Template")
    text = body.get("body", "")
    max_pos = conn.execute("SELECT COALESCE(MAX(position), -1) as mp FROM sms_templates").fetchone()["mp"]
    with conn:
        conn.execute(
            "INSERT INTO sms_templates (label, body, position) VALUES (?, ?, ?)",
            (label, text, max_pos + 1),
        )
    row = conn.execute("SELECT * FROM sms_templates ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return {"id": row["id"], "label": row["label"], "body": row["body"]}


@app.put("/api/sms-templates/{template_id}")
def update_sms_template(template_id: int, body: dict, user: dict = Depends(get_current_user)):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM sms_templates WHERE id = ?", (template_id,)).fetchone()
    if not row:
        conn.close()
        return {"error": "Template not found"}
    updates = {}
    if "label" in body:
        updates["label"] = body["label"]
    if "body" in body:
        updates["body"] = body["body"]
    if updates:
        sets = ", ".join(f"{k}=?" for k in updates)
        vals = list(updates.values()) + [template_id]
        with conn:
            conn.execute(f"UPDATE sms_templates SET {sets} WHERE id=?", vals)
    updated = conn.execute("SELECT * FROM sms_templates WHERE id = ?", (template_id,)).fetchone()
    conn.close()
    return {"id": updated["id"], "label": updated["label"], "body": updated["body"]}


@app.delete("/api/sms-templates/{template_id}")
def delete_sms_template(template_id: int, user: dict = Depends(get_current_user)):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM sms_templates WHERE id = ?", (template_id,)).fetchone()
    if not row:
        conn.close()
        return {"error": "Template not found"}
    with conn:
        conn.execute("DELETE FROM sms_templates WHERE id = ?", (template_id,))
    conn.close()
    return {"success": True}


_quo_phone_number_id: str | None = None


def _get_quo_phone_number_id() -> str | None:
    """Resolve and cache the Quo phoneNumberId from the configured phone number."""
    global _quo_phone_number_id
    if _quo_phone_number_id:
        return _quo_phone_number_id
    import requests as _req
    api_key = os.environ.get("QUO_API_KEY", "")
    from_number = os.environ.get("QUO_PHONE_NUMBER", "")
    if not api_key or not from_number:
        return None
    resp = _req.get(
        "https://api.openphone.com/v1/phone-numbers",
        headers={"Authorization": api_key},
        timeout=10,
    )
    if resp.status_code != 200:
        return None
    for pn in resp.json().get("data", []):
        if pn.get("phoneNumber") == from_number:
            _quo_phone_number_id = pn["id"]
            return _quo_phone_number_id
    return None


@app.get("/api/quo/messages")
def quo_messages(phone: str, user: dict = Depends(get_current_user)):
    """Fetch SMS messages from the Quo API for a given participant phone number."""
    import requests as _req

    api_key = os.environ.get("QUO_API_KEY", "")
    if not api_key:
        return {"error": "Quo is not configured"}

    pn_id = _get_quo_phone_number_id()
    if not pn_id:
        return {"error": "Could not resolve Quo phone number ID"}

    resp = _req.get(
        "https://api.openphone.com/v1/messages",
        headers={"Authorization": api_key},
        params={"phoneNumberId": pn_id, "participants[]": phone, "maxResults": 50},
        timeout=15,
    )
    if resp.status_code != 200:
        return {"error": f"Quo API error ({resp.status_code}): {resp.text[:200]}"}

    data = resp.json().get("data", [])
    messages = []
    for m in data:
        messages.append({
            "id": m.get("id", ""),
            "direction": "inbound" if m.get("direction") == "incoming" else "outbound",
            "body": m.get("text") or m.get("content") or "",
            "from": m.get("from", ""),
            "to": m.get("to", []),
            "status": m.get("status", ""),
            "created_at": m.get("createdAt", ""),
        })
    # Quo returns newest first; reverse for chronological display
    messages.reverse()
    return {"messages": messages}


@app.post("/api/quo/send")
def quo_send(body: dict, user: dict = Depends(get_current_user)):
    """Send an SMS via the Quo (OpenPhone) API."""
    import requests

    api_key = os.environ.get("QUO_API_KEY", "")
    from_number = os.environ.get("QUO_PHONE_NUMBER", "")
    if not api_key or not from_number:
        return {"error": "Quo is not configured (QUO_API_KEY / QUO_PHONE_NUMBER)"}

    lead_id = body.get("lead_id")
    to = body.get("to", "")
    content = body.get("content", "")
    if not lead_id or not to or not content:
        return {"error": "Missing required fields: lead_id, to, content"}

    resp = requests.post(
        "https://api.openphone.com/v1/messages",
        headers={"Authorization": api_key, "Content-Type": "application/json"},
        json={"content": content, "from": from_number, "to": [to]},
        timeout=15,
    )

    if resp.status_code not in (200, 201, 202):
        detail = resp.text[:200]
        return {"error": f"Quo API error ({resp.status_code}): {detail}"}

    return {"success": True}


@app.post("/api/webhooks/twilio")
async def twilio_inbound(request: Request):
    """Receive inbound SMS from Twilio. Configure your Twilio number's webhook to point here."""
    form = await request.form()
    from_number = form.get("From", "")
    to_number = form.get("To", "")
    body = form.get("Body", "")
    message_sid = form.get("MessageSid", "")

    if not from_number or not body:
        return PlainTextResponse("<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response></Response>",
                                 media_type="text/xml")

    conn = _get_conn()

    # Match sender to a lead by phone number
    lead = conn.execute(
        "SELECT l.* FROM leads l JOIN lead_phones lp ON lp.lead_id = l.id WHERE lp.phone = ? LIMIT 1",
        (from_number,),
    ).fetchone()

    if lead:
        now = datetime.now(UTC).isoformat()
        with conn:
            conn.execute(
                """INSERT INTO messages
                   (lead_id, direction, channel, to_addr, from_addr, subject, body, status, external_id, created_at)
                   VALUES (?, 'inbound', 'sms', ?, ?, '', ?, 'received', ?, ?)""",
                (lead["id"], to_number, from_number, body, message_sid, now),
            )

    conn.close()

    # Return empty TwiML (no auto-reply)
    return PlainTextResponse(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response></Response>",
        media_type="text/xml",
    )


# Serve React frontend in production
DIST_DIR = Path(os.environ.get("WEB_DIST_DIR", Path(__file__).resolve().parent.parent.parent / "web" / "dist"))

if DIST_DIR.exists():
    from fastapi.responses import FileResponse

    # Serve static assets
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")

    # Catch-all: serve index.html for any non-API route (SPA routing)
    @app.get("/{path:path}")
    async def serve_spa(path: str):
        if path.startswith("api/"):
            return {"error": "Not found"}, 404
        file_path = DIST_DIR / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(DIST_DIR / "index.html"))
