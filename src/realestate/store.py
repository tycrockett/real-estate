from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from realestate.models import Property

DEFAULT_DB_PATH = Path(os.environ.get("REALESTATE_DB_PATH", Path.home() / ".realestate" / "properties.db"))

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    address TEXT NOT NULL,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    zip_code TEXT NOT NULL,
    price REAL NOT NULL,
    data TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    updated_at TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    UNIQUE(source, source_id)
);
"""

CREATE_CONTACTS_TABLE = """
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL REFERENCES properties(id),
    owner_name TEXT,
    phone_1 TEXT,
    phone_1_type TEXT,
    phone_2 TEXT,
    phone_2_type TEXT,
    phone_3 TEXT,
    phone_3_type TEXT,
    email_1 TEXT,
    email_2 TEXT,
    skip_source TEXT,
    skip_date TEXT,
    raw_data TEXT,
    UNIQUE(property_id)
);
"""

CREATE_LEADS_TABLE = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL REFERENCES properties(id),
    status TEXT NOT NULL DEFAULT 'new',
    notes TEXT DEFAULT '',
    phone_1 TEXT DEFAULT '',
    phone_1_type TEXT DEFAULT '',
    phone_2 TEXT DEFAULT '',
    phone_2_type TEXT DEFAULT '',
    phone_3 TEXT DEFAULT '',
    phone_3_type TEXT DEFAULT '',
    email_1 TEXT DEFAULT '',
    email_2 TEXT DEFAULT '',
    skip_source TEXT DEFAULT '',
    custom_data TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(property_id)
);
"""

CREATE_MESSAGES_TABLE = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL REFERENCES leads(id),
    direction TEXT NOT NULL,
    channel TEXT NOT NULL,
    to_addr TEXT NOT NULL,
    from_addr TEXT DEFAULT '',
    subject TEXT DEFAULT '',
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'sent',
    external_id TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
"""

CREATE_VALUATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS valuations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL REFERENCES properties(id),
    assessed_value REAL,
    estimated_market_value REAL,
    remaining_balance REAL,
    estimated_equity REAL,
    equity_percent REAL,
    bldg_sqft INTEGER,
    built_yr INTEGER,
    monthly_payment REAL,
    rate_used REAL,
    valuation_date TEXT,
    raw_data TEXT,
    UNIQUE(property_id)
);
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_source ON properties(source);",
    "CREATE INDEX IF NOT EXISTS idx_first_seen ON properties(first_seen);",
    "CREATE INDEX IF NOT EXISTS idx_status ON properties(status);",
    "CREATE INDEX IF NOT EXISTS idx_city ON properties(city);",
    "CREATE INDEX IF NOT EXISTS idx_state ON properties(state);",
    "CREATE INDEX IF NOT EXISTS idx_contacts_property_id ON contacts(property_id);",
]


@dataclass
class UpsertResult:
    new: int = 0
    updated: int = 0
    unchanged: int = 0

    @property
    def total(self) -> int:
        return self.new + self.updated + self.unchanged


class PropertyStore:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self._conn:
            self._conn.execute(CREATE_TABLE)
            self._conn.execute(CREATE_CONTACTS_TABLE)
            self._conn.execute(CREATE_LEADS_TABLE)
            self._conn.execute(CREATE_MESSAGES_TABLE)
            self._conn.execute(CREATE_VALUATIONS_TABLE)
            for idx in CREATE_INDEXES:
                self._conn.execute(idx)

    def upsert(self, properties: list[Property]) -> UpsertResult:
        result = UpsertResult()
        now = datetime.now(UTC).isoformat()

        with self._conn:
            for prop in properties:
                data_json = prop.model_dump_json()

                existing = self._conn.execute(
                    "SELECT id, data FROM properties WHERE source = ? AND source_id = ?",
                    (prop.source, prop.source_id),
                ).fetchone()

                if existing is None:
                    self._conn.execute(
                        """INSERT INTO properties
                           (source, source_id, address, city, state, zip_code, price,
                            data, first_seen, last_seen, status)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')""",
                        (
                            prop.source, prop.source_id, prop.address, prop.city,
                            prop.state, prop.zip_code, prop.price,
                            data_json, now, now,
                        ),
                    )
                    result.new += 1
                elif existing["data"] != data_json:
                    self._conn.execute(
                        """UPDATE properties
                           SET address = ?, city = ?, state = ?, zip_code = ?, price = ?,
                               data = ?, last_seen = ?, updated_at = ?, status = 'active'
                           WHERE id = ?""",
                        (
                            prop.address, prop.city, prop.state, prop.zip_code, prop.price,
                            data_json, now, now, existing["id"],
                        ),
                    )
                    result.updated += 1
                else:
                    self._conn.execute(
                        "UPDATE properties SET last_seen = ?, status = 'active' WHERE id = ?",
                        (now, existing["id"]),
                    )
                    result.unchanged += 1

        return result

    def get_new(self, since: datetime | str) -> list[Property]:
        if isinstance(since, datetime):
            since = since.isoformat()
        rows = self._conn.execute(
            "SELECT data FROM properties WHERE first_seen >= ? AND status = 'active' ORDER BY first_seen DESC",
            (since,),
        ).fetchall()
        return [Property.model_validate_json(row["data"]) for row in rows]

    def get_all(
        self,
        source: str | None = None,
        city: str | None = None,
        state: str | None = None,
        status: str = "active",
    ) -> list[Property]:
        query = "SELECT data FROM properties WHERE status = ?"
        params: list = [status]

        if source:
            query += " AND source = ?"
            params.append(source)
        if city:
            query += " AND city = ?"
            params.append(city)
        if state:
            query += " AND state = ?"
            params.append(state)

        query += " ORDER BY first_seen DESC"
        rows = self._conn.execute(query, params).fetchall()
        return [Property.model_validate_json(row["data"]) for row in rows]

    def mark_removed(self, source: str, current_ids: set[str]) -> int:
        rows = self._conn.execute(
            "SELECT id, source_id FROM properties WHERE source = ? AND status = 'active'",
            (source,),
        ).fetchall()

        now = datetime.now(UTC).isoformat()
        removed = 0
        with self._conn:
            for row in rows:
                if row["source_id"] not in current_ids:
                    self._conn.execute(
                        "UPDATE properties SET status = 'removed', updated_at = ? WHERE id = ?",
                        (now, row["id"]),
                    )
                    removed += 1
        return removed

    def count(self, status: str = "active") -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM properties WHERE status = ?", (status,)
        ).fetchone()
        return row["cnt"]

    def upsert_contact(
        self,
        property_id: int,
        owner_name: str = "",
        phone_1: str = "",
        phone_1_type: str = "",
        phone_2: str = "",
        phone_2_type: str = "",
        phone_3: str = "",
        phone_3_type: str = "",
        email_1: str = "",
        email_2: str = "",
        skip_source: str = "",
        raw_data: str = "",
    ) -> bool:
        now = datetime.now(UTC).isoformat()
        with self._conn:
            existing = self._conn.execute(
                "SELECT id FROM contacts WHERE property_id = ?", (property_id,)
            ).fetchone()
            if existing:
                self._conn.execute(
                    """UPDATE contacts SET owner_name=?, phone_1=?, phone_1_type=?,
                       phone_2=?, phone_2_type=?, phone_3=?, phone_3_type=?,
                       email_1=?, email_2=?, skip_source=?, skip_date=?, raw_data=?
                       WHERE property_id=?""",
                    (owner_name, phone_1, phone_1_type, phone_2, phone_2_type,
                     phone_3, phone_3_type, email_1, email_2, skip_source, now,
                     raw_data, property_id),
                )
            else:
                self._conn.execute(
                    """INSERT INTO contacts
                       (property_id, owner_name, phone_1, phone_1_type,
                        phone_2, phone_2_type, phone_3, phone_3_type,
                        email_1, email_2, skip_source, skip_date, raw_data)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (property_id, owner_name, phone_1, phone_1_type,
                     phone_2, phone_2_type, phone_3, phone_3_type,
                     email_1, email_2, skip_source, now, raw_data),
                )
        return True

    def get_contact(self, property_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM contacts WHERE property_id = ?", (property_id,)
        ).fetchone()
        if not row:
            return None
        return dict(row)

    def get_contacts_by_ids(self, property_ids: list[int]) -> dict[int, dict]:
        if not property_ids:
            return {}
        placeholders = ",".join("?" for _ in property_ids)
        rows = self._conn.execute(
            f"SELECT * FROM contacts WHERE property_id IN ({placeholders})",
            property_ids,
        ).fetchall()
        return {row["property_id"]: dict(row) for row in rows}

    def get_property_ids_with_contacts(self) -> set[int]:
        rows = self._conn.execute("SELECT property_id FROM contacts").fetchall()
        return {row["property_id"] for row in rows}

    def get_properties_for_export(
        self,
        county: str | None = None,
        city: str | None = None,
        doc_type: str | None = None,
        skip_existing: bool = False,
    ) -> list[sqlite3.Row]:
        query = "SELECT * FROM properties WHERE status = 'active'"
        params: list = []

        if county:
            query += " AND LOWER(json_extract(data, '$.raw.county')) = LOWER(?)"
            params.append(county)
        if city:
            query += " AND LOWER(city) = LOWER(?)"
            params.append(city)
        if doc_type:
            query += " AND LOWER(json_extract(data, '$.raw.doc_type')) LIKE LOWER(?)"
            params.append(f"%{doc_type}%")
        if skip_existing:
            query += " AND id NOT IN (SELECT property_id FROM contacts)"

        query += " ORDER BY first_seen DESC"
        return self._conn.execute(query, params).fetchall()

    def create_lead(self, property_id: int) -> dict:
        now = datetime.now(UTC).isoformat()
        existing = self._conn.execute(
            "SELECT * FROM leads WHERE property_id = ?", (property_id,)
        ).fetchone()
        if existing:
            return dict(existing)
        with self._conn:
            self._conn.execute(
                """INSERT INTO leads (property_id, status, created_at, updated_at)
                   VALUES (?, 'new', ?, ?)""",
                (property_id, now, now),
            )
        row = self._conn.execute(
            "SELECT * FROM leads WHERE property_id = ?", (property_id,)
        ).fetchone()
        return dict(row)

    def update_lead(self, lead_id: int, **kwargs) -> dict | None:
        now = datetime.now(UTC).isoformat()
        allowed = {
            "status", "notes", "phone_1", "phone_1_type", "phone_2", "phone_2_type",
            "phone_3", "phone_3_type", "email_1", "email_2", "skip_source", "custom_data",
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return self.get_lead(lead_id)
        updates["updated_at"] = now
        sets = ", ".join(f"{k}=?" for k in updates)
        vals = list(updates.values()) + [lead_id]
        with self._conn:
            self._conn.execute(f"UPDATE leads SET {sets} WHERE id=?", vals)
        return self.get_lead(lead_id)

    def get_lead(self, lead_id: int) -> dict | None:
        row = self._conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        return dict(row) if row else None

    def get_lead_by_property(self, property_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM leads WHERE property_id = ?", (property_id,)
        ).fetchone()
        return dict(row) if row else None

    def upsert_valuation(self, property_id: int, **kwargs) -> bool:
        now = datetime.now(UTC).isoformat()
        kwargs["valuation_date"] = now
        with self._conn:
            existing = self._conn.execute(
                "SELECT id FROM valuations WHERE property_id = ?", (property_id,)
            ).fetchone()
            fields = [
                "assessed_value", "estimated_market_value", "remaining_balance",
                "estimated_equity", "equity_percent", "bldg_sqft", "built_yr",
                "monthly_payment", "rate_used", "valuation_date", "raw_data",
            ]
            if existing:
                sets = ", ".join(f"{f}=?" for f in fields)
                vals = [kwargs.get(f) for f in fields]
                vals.append(property_id)
                self._conn.execute(
                    f"UPDATE valuations SET {sets} WHERE property_id=?", vals
                )
            else:
                cols = ", ".join(["property_id"] + fields)
                placeholders = ", ".join(["?"] * (len(fields) + 1))
                vals = [property_id] + [kwargs.get(f) for f in fields]
                self._conn.execute(
                    f"INSERT INTO valuations ({cols}) VALUES ({placeholders})", vals
                )
        return True

    def get_valuation(self, property_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM valuations WHERE property_id = ?", (property_id,)
        ).fetchone()
        return dict(row) if row else None

    def find_property_id(self, source: str, source_id: str) -> int | None:
        row = self._conn.execute(
            "SELECT id FROM properties WHERE source = ? AND source_id = ?",
            (source, source_id),
        ).fetchone()
        return row["id"] if row else None

    def close(self) -> None:
        self._conn.close()
