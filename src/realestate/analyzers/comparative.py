from __future__ import annotations

import statistics

from realestate.analyzers import register
from realestate.models import Property, Score


@register("comparative")
class ComparativeScorer:
    name = "comparative"
    weight = 1.0

    def score(self, prop: Property, context: list[Property]) -> Score:
        comps = self._find_comps(prop, context)

        if len(comps) < 2:
            return Score(name=self.name, value=50.0, detail="Too few comparable properties")

        comp_prices = [c.price for c in comps]
        median_price = statistics.median(comp_prices)

        if median_price == 0:
            return Score(name=self.name, value=50.0, detail="Median comp price is zero")

        ratio = prop.price / median_price
        value = max(0.0, min(100.0, round((2 - ratio) * 50, 2)))

        diff = prop.price - median_price
        direction = "below" if diff < 0 else "above"

        return Score(
            name=self.name,
            value=value,
            detail=f"${prop.price:,.0f} vs ${median_price:,.0f} median ({len(comps)} comps, ${abs(diff):,.0f} {direction})",
        )

    def _find_comps(self, prop: Property, context: list[Property]) -> list[Property]:
        comps = []
        for c in context:
            if c.source_id == prop.source_id:
                continue
            if c.zip_code != prop.zip_code:
                continue
            if prop.bedrooms is not None and c.bedrooms is not None:
                if abs(c.bedrooms - prop.bedrooms) > 1:
                    continue
            if prop.sqft is not None and c.sqft is not None:
                if abs(c.sqft - prop.sqft) / prop.sqft > 0.3:
                    continue
            comps.append(c)
        return comps
