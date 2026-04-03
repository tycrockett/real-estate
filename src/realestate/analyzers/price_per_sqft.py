from __future__ import annotations

import statistics

from realestate.analyzers import register
from realestate.models import Property, Score


@register("price_per_sqft")
class PricePerSqftScorer:
    name = "price_per_sqft"
    weight = 1.0

    def score(self, prop: Property, context: list[Property]) -> Score:
        if prop.price_per_sqft is None:
            return Score(name=self.name, value=50.0, detail="No sqft data; neutral score")

        market_values = [p.price_per_sqft for p in context if p.price_per_sqft is not None]
        if not market_values:
            return Score(name=self.name, value=50.0, detail="No market data for comparison")

        median = statistics.median(market_values)
        if median == 0:
            return Score(name=self.name, value=50.0, detail="Median price/sqft is zero")

        ratio = prop.price_per_sqft / median
        value = max(0.0, min(100.0, round((2 - ratio) * 50, 2)))
        return Score(
            name=self.name,
            value=value,
            detail=f"${prop.price_per_sqft:.0f}/sqft vs median ${median:.0f}/sqft",
        )
