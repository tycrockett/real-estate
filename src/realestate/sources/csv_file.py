from __future__ import annotations

import csv
from pathlib import Path

from pydantic import ValidationError

from realestate.models import Property
from realestate.sources import register

DEFAULT_COLUMN_MAP: dict[str, str] = {
    "source": "source",
    "source_id": "source_id",
    "address": "address",
    "city": "city",
    "state": "state",
    "zip_code": "zip_code",
    "price": "price",
    "bedrooms": "bedrooms",
    "bathrooms": "bathrooms",
    "sqft": "sqft",
    "lot_sqft": "lot_sqft",
    "property_type": "property_type",
    "year_built": "year_built",
    "list_date": "list_date",
    "estimated_rent": "estimated_rent",
    "hoa": "hoa",
    "tax_annual": "tax_annual",
    "url": "url",
}


@register("csv")
class CsvSource:
    name = "csv"

    def __init__(self, path: str | None = None, column_map: dict[str, str] | None = None):
        self.path = path
        self.column_map = column_map or DEFAULT_COLUMN_MAP

    def fetch(self, **filters) -> list[Property]:
        path = filters.get("path") or self.path
        if not path:
            raise ValueError("CsvSource requires a 'path' (constructor arg or filter)")

        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"CSV file not found: {path}")

        properties = []
        with open(file_path, newline="") as f:
            reader = csv.DictReader(f)
            for row_num, row in enumerate(reader, start=2):
                data = {}
                for model_field, csv_col in self.column_map.items():
                    if csv_col in row and row[csv_col].strip():
                        data[model_field] = row[csv_col].strip()

                if "source" not in data:
                    data["source"] = "csv"
                if "source_id" not in data:
                    data["source_id"] = f"CSV-{row_num}"

                try:
                    prop = Property.model_validate(data)
                except ValidationError:
                    continue

                min_price = filters.get("min_price")
                max_price = filters.get("max_price")
                if min_price is not None and prop.price < min_price:
                    continue
                if max_price is not None and prop.price > max_price:
                    continue

                properties.append(prop)

        return properties
