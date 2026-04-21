#!/usr/bin/env python3
"""Seed the database with dummy data for testing."""

import random
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from realestate.models import Property
from realestate.store import PropertyStore

STREETS = [
    "123 Maple Ave", "456 Oak Dr", "789 Pine St", "1010 Cedar Ln",
    "222 Birch Ct", "333 Elm Way", "444 Spruce Blvd", "555 Willow Rd",
    "666 Aspen Trl", "777 Juniper Cir", "888 Sycamore Pl", "999 Poplar Dr",
    "101 Redwood Ave", "202 Magnolia St", "303 Chestnut Ln", "404 Cypress Way",
    "505 Walnut Rd", "606 Hickory Ct", "707 Alder Blvd", "808 Sequoia Dr",
]

CITIES = [
    ("Salt Lake City", "UT", "84101", "Salt Lake"),
    ("Provo", "UT", "84601", "Utah"),
    ("Ogden", "UT", "84401", "Weber"),
    ("Sandy", "UT", "84070", "Salt Lake"),
    ("West Jordan", "UT", "84084", "Salt Lake"),
    ("Lehi", "UT", "84043", "Utah"),
    ("Draper", "UT", "84020", "Salt Lake"),
    ("American Fork", "UT", "84003", "Utah"),
    ("Layton", "UT", "84041", "Davis"),
    ("St George", "UT", "84770", "Washington"),
]

OWNER_NAMES = [
    "John Smith", "Maria Garcia", "James Johnson", "Sarah Williams",
    "Robert Brown", "Lisa Davis", "Michael Wilson", "Jennifer Martinez",
    "David Anderson", "Emily Thomas", "Daniel Taylor", "Jessica Moore",
    "Chris Jackson", "Amanda White", "Kevin Harris", "Michelle Martin",
    "Brian Thompson", "Stephanie Lee", "Jason Clark", "Nicole Lewis",
]

DOC_TYPES = [
    "NOTICE OF DEFAULT", "NOTICE OF DEFAULT", "NOTICE OF DEFAULT",
    "TRUSTEE'S SALE", "LIS PENDENS",
]

LENDERS = [
    "Wells Fargo", "Chase", "Bank of America", "US Bank",
    "Nationstar", "Ocwen", "PHH Mortgage", "Flagstar Bank",
]

TRUSTEES = [
    "Orange Title Insurance", "Halliday Watkins & Mann",
    "Lincoln Title Insurance", "First American Title",
]

PHONE_TYPES = ["mobile", "landline", "work", "home", ""]

LEAD_STATUSES = ["new", "contactable", "contacted", "callback", "interested", "negotiating", "dead"]

NOTE_TEMPLATES = [
    "Left voicemail, will follow up next week.",
    "Spoke with owner, interested in discussing options.",
    "No answer, tried twice.",
    "Owner aware of situation, wants to explore alternatives.",
    "Callback requested for Thursday afternoon.",
    "",
    "",
    "Very motivated seller. Wants to avoid foreclosure.",
    "Owner has moved out of state. Property vacant.",
    "Tenant occupied, owner behind on payments.",
]

MESSAGE_TEMPLATES = [
    "Hi {name}, I noticed your property at {address} and wanted to reach out about some options that might help.",
    "Thanks for getting back to me. I'd love to set up a time to talk about your situation.",
    "Just following up on our conversation. Let me know if you have any questions.",
    "Hi, who is this?",
    "Yes I'm interested in hearing more. When can we talk?",
    "I'm not interested, please don't contact me again.",
    "Can you tell me more about how this works?",
    "Thanks for the info. I'll think about it and get back to you.",
]


def random_phone():
    area = random.choice(["801", "385", "435"])
    return f"+1{area}{random.randint(2000000, 9999999)}"


def random_date(start_days_ago=365, end_days_ago=30):
    days_ago = random.randint(end_days_ago, start_days_ago)
    return datetime.now(UTC) - timedelta(days=days_ago)


def random_past_date_str(start_year=2018, end_year=2023):
    y = random.randint(start_year, end_year)
    m = random.randint(1, 12)
    d = random.randint(1, 28)
    return f"{m:02d}/{d:02d}/{y}"


def seed(num_properties=20):
    store = PropertyStore()
    print(f"Database: {store.db_path}")

    # 1. Create properties
    properties = []
    for i in range(num_properties):
        city, state, zip_code, county = random.choice(CITIES)
        street = random.choice(STREETS)
        owner = random.choice(OWNER_NAMES)
        orig_mtg = random.randint(150000, 550000)
        orig_date = random_past_date_str()
        doc_type = random.choice(DOC_TYPES)

        prop = Property(
            source="seed",
            source_id=f"seed-{i+1:04d}",
            address=street,
            city=city,
            state=state,
            zip_code=zip_code,
            price=float(orig_mtg),
            raw={
                "county": county,
                "owner_name": owner,
                "doc_type": doc_type,
                "lien_position": str(random.choice([1, 1, 1, 2])),
                "orig_mtg_amt": float(orig_mtg),
                "orig_rec_date": orig_date,
                "recording_date": random_past_date_str(2024, 2025),
                "fore_effective": random_past_date_str(2024, 2025),
                "lender": random.choice(LENDERS),
                "trustee": random.choice(TRUSTEES),
                "owner_occupied": random.choice(["Y", "Y", "N"]),
                "parcel_id": f"{random.randint(10,99)}-{random.randint(100,999)}-{random.randint(1000,9999)}",
                "owner_mail_street": f"{random.randint(100,9999)} {random.choice(['Main', 'Center', 'State', '200 E', '400 S'])} St",
                "owner_mail_city_state_zip": f"{city}, {state} {zip_code}",
                "property_type_raw": random.choice(["SFR", "SFR", "CONDO", "TOWNHOUSE"]),
            },
        )
        properties.append(prop)

    result = store.upsert(properties)
    print(f"Properties: {result.new} new, {result.updated} updated, {result.unchanged} unchanged")

    # Get property IDs
    rows = store._conn.execute(
        "SELECT id, source_id, data FROM properties WHERE source = 'seed' ORDER BY id"
    ).fetchall()
    prop_rows = [(r["id"], r["source_id"], r["data"]) for r in rows]

    # 2. Create valuations for most properties
    val_count = 0
    for pid, sid, data in prop_rows:
        if random.random() < 0.2:
            continue
        import json
        pdata = json.loads(data)
        raw = pdata.get("raw", {})
        orig_mtg = raw.get("orig_mtg_amt", 300000)
        assessed = int(orig_mtg * random.uniform(0.8, 1.4))
        market = int(assessed * 1.1)
        remaining = int(orig_mtg * random.uniform(0.5, 0.95))
        equity = market - remaining
        equity_pct = round((equity / market) * 100, 1) if market > 0 else 0
        rate = round(random.uniform(3.0, 7.5), 2)
        monthly = round(remaining * (rate / 100 / 12) / (1 - (1 + rate / 100 / 12) ** -240), 2)

        store.upsert_valuation(
            pid,
            assessed_value=assessed,
            estimated_market_value=market,
            remaining_balance=remaining,
            estimated_equity=equity,
            equity_percent=equity_pct,
            bldg_sqft=random.choice([1200, 1600, 1800, 2200, 2800, 3200]),
            built_yr=random.randint(1970, 2015),
            monthly_payment=monthly,
            rate_used=rate,
        )
        val_count += 1
    print(f"Valuations: {val_count} created")

    # 3. Create leads for a subset of properties
    lead_count = 0
    lead_ids = []
    num_leads = min(len(prop_rows), random.randint(8, 15))
    lead_props = random.sample(prop_rows, num_leads)

    for pid, sid, data in lead_props:
        lead = store.create_lead(pid)
        lead_id = lead["id"]
        lead_ids.append((lead_id, data))

        status = random.choice(LEAD_STATUSES)
        notes = random.choice(NOTE_TEMPLATES)
        email = f"{random.choice(OWNER_NAMES).split()[0].lower()}{random.randint(10,99)}@gmail.com" if random.random() > 0.4 else ""

        store.update_lead(
            lead_id,
            status=status,
            notes=notes,
            email_1=email,
        )

        # Add 1-4 phone numbers per lead
        num_phones = random.randint(1, 4)
        for j in range(num_phones):
            store.add_lead_phone(lead_id, random_phone(), random.choice(PHONE_TYPES))

        lead_count += 1
    print(f"Leads: {lead_count} created with phones")

    # 4. Create some messages for leads that are past 'new' status
    msg_count = 0
    for lead_id, data in lead_ids:
        lead = store.get_lead(lead_id)
        if lead["status"] == "new":
            continue
        if random.random() < 0.3:
            continue

        phones = store.get_lead_phones(lead_id)
        if not phones:
            continue

        import json
        pdata = json.loads(data)
        owner = pdata.get("raw", {}).get("owner_name", "there")
        address = pdata.get("address", "your property")
        first_name = owner.split()[0] if owner else "there"

        to_phone = phones[0]["phone"]
        num_msgs = random.randint(1, 4)
        base_time = random_date(60, 5)

        for k in range(num_msgs):
            direction = "outbound" if k % 2 == 0 else "inbound"
            template = random.choice(MESSAGE_TEMPLATES)
            body = template.format(name=first_name, address=address)
            msg_time = (base_time + timedelta(hours=k * random.randint(1, 48))).isoformat()

            with store._conn:
                store._conn.execute(
                    """INSERT INTO messages
                       (lead_id, direction, channel, to_addr, from_addr, subject, body, status, external_id, created_at)
                       VALUES (?, ?, 'sms', ?, ?, '', ?, ?, '', ?)""",
                    (
                        lead_id, direction,
                        to_phone if direction == "outbound" else "+18015551234",
                        "+18015551234" if direction == "outbound" else to_phone,
                        body,
                        "sent" if direction == "outbound" else "received",
                        msg_time,
                    ),
                )
            msg_count += 1
    print(f"Messages: {msg_count} created")

    store.close()
    print("Done!")


if __name__ == "__main__":
    seed()
