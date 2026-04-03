from __future__ import annotations

import csv
import json
import sys
from datetime import UTC, datetime

import click

from realestate import sources, analyzers, output
from realestate.store import PropertyStore


@click.group()
def main():
    """Real estate deal finder — find distressed properties and owner contacts."""
    pass


@main.command()
@click.option("--source", "-s", default="mock", help=f"Data source ({', '.join(sources.available())})")
@click.option("--format", "-f", "fmt", default="table", help=f"Output format ({', '.join(output.available())})")
@click.option("--top", "-n", default=10, type=int, help="Show top N deals")
@click.option("--city", default=None, help="Filter by city")
@click.option("--state", default=None, help="Filter by state")
@click.option("--min-price", type=float, default=None, help="Minimum price")
@click.option("--max-price", type=float, default=None, help="Maximum price")
@click.option("--csv-path", default=None, help="Path to CSV file (for csv source)")
@click.option("--county", default=None, help="Filter by county (for meridian_nod source)")
@click.option("--doc-type", default=None, help="Filter by doc type: DEFAULT, SALE, LIS PENDENS")
@click.option("--out", "-o", default=None, help="Output file path (default: stdout)")
@click.option("--no-store", is_flag=True, help="Skip persistence (stateless mode)")
@click.option("--new-only", is_flag=True, help="Only show properties first seen on this run")
@click.option("--since", default=None, help="Only show properties first seen since date (YYYY-MM-DD)")
@click.option("--db", default=None, help="Custom database path")
def search(source, fmt, top, city, state, min_price, max_price, csv_path, county, doc_type, out,
           no_store, new_only, since, db):
    """Fetch, score, and display real estate deals."""
    filters = {}
    if city:
        filters["city"] = city
    if state:
        filters["state"] = state
    if min_price is not None:
        filters["min_price"] = min_price
    if max_price is not None:
        filters["max_price"] = max_price
    if csv_path:
        filters["path"] = csv_path
    if county:
        filters["county"] = county
    if doc_type:
        filters["doc_type"] = doc_type

    source_kwargs = {}
    if source == "csv" and csv_path:
        source_kwargs["path"] = csv_path

    src = sources.get_source(source, **source_kwargs)
    properties = src.fetch(**filters)

    if not properties:
        click.echo("No properties found matching filters.")
        return

    click.echo(f"Fetched {len(properties)} properties from '{source}' source.")

    if not no_store:
        store = PropertyStore(db_path=db)
        run_start = datetime.now(UTC)

        result = store.upsert(properties)
        click.echo(
            f"Store: {result.new} new, {result.updated} updated, "
            f"{result.unchanged} unchanged ({store.count()} total active)"
        )

        current_ids = {p.source_id for p in properties}
        removed = store.mark_removed(source, current_ids)
        if removed:
            click.echo(f"Store: {removed} properties no longer in source (marked removed)")

        if new_only:
            properties = store.get_new(since=run_start)
            click.echo(f"Showing {len(properties)} new properties.")
        elif since:
            since_dt = datetime.fromisoformat(since)
            properties = store.get_new(since=since_dt)
            click.echo(f"Showing {len(properties)} properties first seen since {since}.")

        store.close()

    if not properties:
        click.echo("No new properties to display.")
        return

    scored = analyzers.score_properties(properties)
    top_deals = scored[:top]

    formatter = output.get_formatter(fmt)
    formatter.format(top_deals, dest=out)


def _split_owner_name(full_name: str) -> tuple[str, str]:
    """Split 'FIRST MIDDLE LAST' or 'FIRST LAST & FIRST2 LAST2' into (first, last)."""
    if not full_name:
        return ("", "")
    # Take the first person if multiple (split on &)
    primary = full_name.split("&")[0].strip()
    parts = primary.split()
    if len(parts) == 1:
        return (parts[0], "")
    return (parts[0], " ".join(parts[1:]))


@main.command("skip-export")
@click.option("--county", default=None, help="Filter by county")
@click.option("--city", default=None, help="Filter by city")
@click.option("--doc-type", default=None, help="Filter by doc type")
@click.option("--no-existing", is_flag=True, help="Skip properties that already have contacts")
@click.option("--out", "-o", default=None, help="Output CSV path (default: stdout)")
@click.option("--db", default=None, help="Custom database path")
def skip_export(county, city, doc_type, no_existing, out, db):
    """Export a CSV for skip trace upload (BatchSkipTracing, REISkip, etc.)."""
    store = PropertyStore(db_path=db)
    rows = store.get_properties_for_export(
        county=county, city=city, doc_type=doc_type, skip_existing=no_existing,
    )

    if not rows:
        click.echo("No properties to export.")
        store.close()
        return

    fieldnames = [
        "property_id", "first_name", "last_name",
        "address", "city", "state", "zip",
        "mailing_address", "mailing_city", "mailing_state", "mailing_zip",
    ]

    dest = open(out, "w", newline="") if out else sys.stdout
    writer = csv.DictWriter(dest, fieldnames=fieldnames)
    writer.writeheader()

    for row in rows:
        data = json.loads(row["data"])
        raw = data.get("raw", {})
        owner_name = raw.get("owner_name", "")
        first_name, last_name = _split_owner_name(owner_name)

        # Parse mailing city/state/zip from "CITY, ST ZIP"
        mail_csz = raw.get("owner_mail_city_state_zip", "")
        mail_city, mail_state, mail_zip = "", "", ""
        if ", " in mail_csz:
            parts = mail_csz.split(", ", 1)
            mail_city = parts[0]
            rest = parts[1].split(" ", 1) if len(parts) > 1 else []
            mail_state = rest[0] if rest else ""
            mail_zip = rest[1] if len(rest) > 1 else ""

        writer.writerow({
            "property_id": row["id"],
            "first_name": first_name.title(),
            "last_name": last_name.title(),
            "address": data.get("address", ""),
            "city": data.get("city", ""),
            "state": data.get("state", ""),
            "zip": data.get("zip_code", ""),
            "mailing_address": raw.get("owner_mail_street", ""),
            "mailing_city": mail_city,
            "mailing_state": mail_state,
            "mailing_zip": mail_zip,
        })

    if out:
        dest.close()
        click.echo(f"Exported {len(rows)} properties to {out}")
    else:
        click.echo(f"\n# Exported {len(rows)} properties", err=True)

    store.close()


# Common column name mappings from various skip trace providers
PHONE_COLUMN_ALIASES = {
    "phone_1": ["phone_1", "phone1", "phone number 1", "phone", "mobile", "cell"],
    "phone_2": ["phone_2", "phone2", "phone number 2", "landline", "home phone"],
    "phone_3": ["phone_3", "phone3", "phone number 3", "work phone"],
}
PHONE_TYPE_ALIASES = {
    "phone_1_type": ["phone_1_type", "phone1_type", "phone type 1", "phone_type"],
    "phone_2_type": ["phone_2_type", "phone2_type", "phone type 2"],
    "phone_3_type": ["phone_3_type", "phone3_type", "phone type 3"],
}
EMAIL_ALIASES = {
    "email_1": ["email_1", "email1", "email", "email address"],
    "email_2": ["email_2", "email2", "email address 2"],
}


def _find_column(headers: list[str], aliases: list[str]) -> str | None:
    headers_lower = {h.lower().strip(): h for h in headers}
    for alias in aliases:
        if alias.lower() in headers_lower:
            return headers_lower[alias.lower()]
    return None


@main.command("skip-import")
@click.option("--file", "-f", "filepath", required=True, help="Path to enriched CSV from skip trace service")
@click.option("--source", "-s", "skip_source", default="unknown", help="Skip trace provider name")
@click.option("--db", default=None, help="Custom database path")
def skip_import(filepath, skip_source, db):
    """Import skip trace results (phone, email) from an enriched CSV."""
    store = PropertyStore(db_path=db)

    with open(filepath, newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        # Auto-map columns
        col_map = {}
        for field, aliases in {**PHONE_COLUMN_ALIASES, **PHONE_TYPE_ALIASES, **EMAIL_ALIASES}.items():
            col = _find_column(headers, aliases)
            if col:
                col_map[field] = col

        pid_col = _find_column(headers, ["property_id", "id", "prop_id"])

        imported = 0
        skipped = 0

        for row in reader:
            # Find the property ID
            property_id = None
            if pid_col and row.get(pid_col):
                try:
                    property_id = int(row[pid_col])
                except ValueError:
                    pass

            if property_id is None:
                skipped += 1
                continue

            # Extract contact fields
            kwargs = {"skip_source": skip_source, "raw_data": json.dumps(dict(row))}

            # Owner name
            first = row.get("first_name", row.get("First Name", ""))
            last = row.get("last_name", row.get("Last Name", ""))
            if first or last:
                kwargs["owner_name"] = f"{first} {last}".strip()

            for field, col in col_map.items():
                val = row.get(col, "").strip()
                if val:
                    kwargs[field] = val

            store.upsert_contact(property_id, **kwargs)
            imported += 1

    click.echo(f"Imported {imported} contacts from '{skip_source}' ({skipped} skipped)")
    store.close()


if __name__ == "__main__":
    main()
