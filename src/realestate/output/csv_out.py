from __future__ import annotations

import csv
import sys

from realestate.models import ScoredProperty
from realestate.output import register


@register("csv")
class CsvFormatter:
    name = "csv"

    def format(self, results: list[ScoredProperty], dest: str | None = None) -> None:
        if not results:
            return

        rows = []
        for r in results:
            prop = r.property
            row = {
                "rank": len(rows) + 1,
                "address": prop.address,
                "city": prop.city,
                "state": prop.state,
                "zip_code": prop.zip_code,
                "price": prop.price,
                "bedrooms": prop.bedrooms,
                "bathrooms": prop.bathrooms,
                "sqft": prop.sqft,
                "price_per_sqft": prop.price_per_sqft,
                "estimated_rent": prop.estimated_rent,
                "property_type": prop.property_type.value if prop.property_type else None,
                "year_built": prop.year_built,
                "total_score": r.total_score,
                "source": prop.source,
                "source_id": prop.source_id,
                "url": prop.url,
            }
            for score in r.scores:
                row[f"score_{score.name}"] = score.value
                row[f"detail_{score.name}"] = score.detail
            rows.append(row)

        fieldnames = list(rows[0].keys())

        if dest:
            with open(dest, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        else:
            writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
