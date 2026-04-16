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
    normalized_address TEXT,
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

CREATE_LEAD_PHONES_TABLE = """
CREATE TABLE IF NOT EXISTS lead_phones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL REFERENCES leads(id),
    phone TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0
);
"""

CREATE_SMS_TEMPLATES_TABLE = """
CREATE TABLE IF NOT EXISTS sms_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0
);
"""

CREATE_SHORT_CODES_TABLE = """
CREATE TABLE IF NOT EXISTS short_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    property_id INTEGER NOT NULL REFERENCES properties(id),
    created_at TEXT NOT NULL,
    click_count INTEGER DEFAULT 0
);
"""

CREATE_NOTIFICATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT DEFAULT '',
    lead_id INTEGER REFERENCES leads(id),
    read INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
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
            self._conn.execute(CREATE_LEAD_PHONES_TABLE)
            self._conn.execute(CREATE_SMS_TEMPLATES_TABLE)
            self._conn.execute(CREATE_MESSAGES_TABLE)
            self._conn.execute(CREATE_VALUATIONS_TABLE)
            self._conn.execute(CREATE_SHORT_CODES_TABLE)
            self._conn.execute(CREATE_NOTIFICATIONS_TABLE)
            for idx in CREATE_INDEXES:
                self._conn.execute(idx)
            self._migrate_add_normalized_address()
            self._migrate_lead_phones()

    def _migrate_add_normalized_address(self) -> None:
        """Add normalized_address column if it doesn't exist yet."""
        cols = [r[1] for r in self._conn.execute("PRAGMA table_info(properties)").fetchall()]
        if "normalized_address" not in cols:
            self._conn.execute("ALTER TABLE properties ADD COLUMN normalized_address TEXT")

    def _migrate_lead_phones(self) -> None:
        """One-time migration: move phone_1/2/3 from leads into lead_phones table."""
        has_phones = self._conn.execute("SELECT COUNT(*) as cnt FROM lead_phones").fetchone()["cnt"]
        if has_phones > 0:
            return
        rows = self._conn.execute(
            "SELECT id, phone_1, phone_1_type, phone_2, phone_2_type, phone_3, phone_3_type FROM leads"
        ).fetchall()
        with self._conn:
            for row in rows:
                for i in range(1, 4):
                    phone = row[f"phone_{i}"] or ""
                    ptype = row[f"phone_{i}_type"] or ""
                    if phone:
                        self._conn.execute(
                            "INSERT INTO lead_phones (lead_id, phone, type, position) VALUES (?, ?, ?, ?)",
                            (row["id"], phone, ptype, i - 1),
                        )

    def get_lead_phones(self, lead_id: int) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM lead_phones WHERE lead_id = ? ORDER BY position, id",
            (lead_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_leads_phones(self, lead_ids: list[int]) -> dict[int, list[dict]]:
        if not lead_ids:
            return {}
        placeholders = ",".join("?" for _ in lead_ids)
        rows = self._conn.execute(
            f"SELECT * FROM lead_phones WHERE lead_id IN ({placeholders}) ORDER BY position, id",
            lead_ids,
        ).fetchall()
        result: dict[int, list[dict]] = {lid: [] for lid in lead_ids}
        for r in rows:
            result[r["lead_id"]].append(dict(r))
        return result

    def add_lead_phone(self, lead_id: int, phone: str, phone_type: str = "") -> dict:
        max_pos = self._conn.execute(
            "SELECT COALESCE(MAX(position), -1) as mp FROM lead_phones WHERE lead_id = ?",
            (lead_id,),
        ).fetchone()["mp"]
        with self._conn:
            self._conn.execute(
                "INSERT INTO lead_phones (lead_id, phone, type, position) VALUES (?, ?, ?, ?)",
                (lead_id, phone, phone_type, max_pos + 1),
            )
        row = self._conn.execute(
            "SELECT * FROM lead_phones WHERE lead_id = ? ORDER BY id DESC LIMIT 1",
            (lead_id,),
        ).fetchone()
        return dict(row)

    def update_lead_phone(self, phone_id: int, **kwargs) -> dict | None:
        allowed = {"phone", "type"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            row = self._conn.execute("SELECT * FROM lead_phones WHERE id = ?", (phone_id,)).fetchone()
            return dict(row) if row else None
        sets = ", ".join(f"{k}=?" for k in updates)
        vals = list(updates.values()) + [phone_id]
        with self._conn:
            self._conn.execute(f"UPDATE lead_phones SET {sets} WHERE id=?", vals)
        row = self._conn.execute("SELECT * FROM lead_phones WHERE id = ?", (phone_id,)).fetchone()
        return dict(row) if row else None

    def delete_lead_phone(self, phone_id: int) -> bool:
        with self._conn:
            self._conn.execute("DELETE FROM lead_phones WHERE id = ?", (phone_id,))
        return True

    def find_lead_by_phone(self, phone: str) -> dict | None:
        row = self._conn.execute(
            "SELECT l.* FROM leads l JOIN lead_phones lp ON lp.lead_id = l.id WHERE lp.phone = ? LIMIT 1",
            (phone,),
        ).fetchone()
        return dict(row) if row else None

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
                            normalized_address, data, first_seen, last_seen, status)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')""",
                        (
                            prop.source, prop.source_id, prop.address, prop.city,
                            prop.state, prop.zip_code, prop.price,
                            prop.normalized_address, data_json, now, now,
                        ),
                    )
                    result.new += 1
                elif existing["data"] != data_json:
                    self._conn.execute(
                        """UPDATE properties
                           SET address = ?, city = ?, state = ?, zip_code = ?, price = ?,
                               normalized_address = ?, data = ?, last_seen = ?, updated_at = ?, status = 'active'
                           WHERE id = ?""",
                        (
                            prop.address, prop.city, prop.state, prop.zip_code, prop.price,
                            prop.normalized_address, data_json, now, now, existing["id"],
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
            "status", "notes", "email_1", "email_2", "skip_source", "custom_data",
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

    def create_notification(self, type: str, title: str, body: str = "", lead_id: int | None = None) -> dict:
        now = datetime.now(UTC).isoformat()
        with self._conn:
            self._conn.execute(
                "INSERT INTO notifications (type, title, body, lead_id, created_at) VALUES (?, ?, ?, ?, ?)",
                (type, title, body, lead_id, now),
            )
        row = self._conn.execute(
            "SELECT * FROM notifications ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row)

    def get_notifications(self, unread_only: bool = False) -> list[dict]:
        query = "SELECT * FROM notifications"
        if unread_only:
            query += " WHERE read = 0"
        query += " ORDER BY created_at DESC"
        return [dict(r) for r in self._conn.execute(query).fetchall()]

    def mark_notification_read(self, notification_id: int) -> bool:
        with self._conn:
            self._conn.execute(
                "UPDATE notifications SET read = 1 WHERE id = ?", (notification_id,)
            )
        return True

    def get_unread_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) as cnt FROM notifications WHERE read = 0").fetchone()
        return row["cnt"]

    def get_properties_missing_normalized_address(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, address, city, state, zip_code FROM properties "
            "WHERE normalized_address IS NULL AND status = 'active'"
        ).fetchall()
        return [dict(r) for r in rows]

    def set_normalized_address(self, property_id: int, normalized_address: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE properties SET normalized_address = ? WHERE id = ?",
                (normalized_address, property_id),
            )
            # Also update the JSON data blob
            row = self._conn.execute(
                "SELECT data FROM properties WHERE id = ?", (property_id,)
            ).fetchone()
            if row:
                data = json.loads(row["data"])
                data["normalized_address"] = normalized_address
                self._conn.execute(
                    "UPDATE properties SET data = ? WHERE id = ?",
                    (json.dumps(data), property_id),
                )

    def close(self) -> None:
        self._conn.close()
