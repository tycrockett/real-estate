#!/usr/bin/env python3
"""One-time backfill: populate normalized_address for existing properties via Google Places API."""

import sys
import time
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

from realestate.geocoding import normalize_address
from realestate.store import PropertyStore


def main():
    store = PropertyStore()
    rows = store.get_properties_missing_normalized_address()

    if not rows:
        print("All properties already have normalized addresses.")
        store.close()
        return

    print(f"Found {len(rows)} properties missing normalized_address.")
    updated = 0
    failed = 0

    for i, row in enumerate(rows, 1):
        full = f"{row['address']}, {row['city']}, {row['state']} {row['zip_code']}"
        result = normalize_address(row["address"], row["city"], row["state"], row["zip_code"])
        if result:
            store.set_normalized_address(row["id"], result)
            updated += 1
            print(f"  [{i}/{len(rows)}] {full} -> {result}")
        else:
            failed += 1
            print(f"  [{i}/{len(rows)}] FAILED: {full}")

        # Respect Google API rate limits (50 req/s for Geocoding)
        if i % 50 == 0:
            time.sleep(1)

    store.close()
    print(f"\nDone. Updated: {updated}, Failed: {failed}")


if __name__ == "__main__":
    main()
