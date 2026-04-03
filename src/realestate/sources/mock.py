from __future__ import annotations

import random
from datetime import date, timedelta

from realestate.models import Property, PropertyType
from realestate.sources import register


@register("mock")
class MockSource:
    name = "mock"

    def __init__(self, seed: int = 42, count: int = 50):
        self.seed = seed
        self.count = count

    def fetch(self, **filters) -> list[Property]:
        rng = random.Random(self.seed)
        properties = []

        city = filters.get("city", "Testville")
        state = filters.get("state", "TX")
        min_price = filters.get("min_price")
        max_price = filters.get("max_price")

        streets = ["Oak", "Elm", "Main", "Park", "Cedar", "Maple", "Pine", "Birch"]
        suffixes = ["St", "Ave", "Dr", "Ln", "Blvd", "Way"]

        for i in range(self.count):
            sqft = rng.randint(800, 4000)
            price_per_sqft = rng.uniform(80, 300)
            price = round(sqft * price_per_sqft, -3)

            if min_price is not None and price < min_price:
                continue
            if max_price is not None and price > max_price:
                continue

            rent_ratio = rng.uniform(0.005, 0.012)

            properties.append(Property(
                source="mock",
                source_id=f"MOCK-{i:04d}",
                address=f"{rng.randint(100, 9999)} {rng.choice(streets)} {rng.choice(suffixes)}",
                city=city,
                state=state,
                zip_code=f"{rng.randint(10000, 99999)}",
                price=price,
                bedrooms=rng.randint(1, 6),
                bathrooms=rng.choice([1.0, 1.5, 2.0, 2.5, 3.0, 3.5]),
                sqft=sqft,
                lot_sqft=sqft * rng.randint(2, 8),
                property_type=rng.choice(list(PropertyType)),
                year_built=rng.randint(1950, 2024),
                list_date=date.today() - timedelta(days=rng.randint(1, 180)),
                estimated_rent=round(price * rent_ratio / 12, 2),
                tax_annual=round(price * rng.uniform(0.008, 0.025), 2),
            ))

        return properties
