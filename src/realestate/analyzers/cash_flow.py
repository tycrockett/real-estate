from __future__ import annotations

from realestate.analyzers import register
from realestate.models import Property, Score


@register("cash_flow")
class CashFlowScorer:
    name = "cash_flow"
    weight = 1.0

    def score(self, prop: Property, context: list[Property]) -> Score:
        if prop.estimated_rent is None or prop.price <= 0:
            return Score(name=self.name, value=50.0, detail="No rent data; neutral score")

        monthly_rent = prop.estimated_rent
        annual_rent = monthly_rent * 12

        # Gross rent multiplier: price / annual_rent (lower = better)
        grm = prop.price / annual_rent if annual_rent > 0 else float("inf")

        # 1% rule: monthly rent should be >= 1% of price
        rent_ratio = monthly_rent / prop.price

        # Score based on rent ratio: 1% = 70, 1.2% = 90, 0.5% = 20
        value = max(0.0, min(100.0, round(rent_ratio * 7000, 2)))

        expenses_note = ""
        if prop.tax_annual is not None:
            monthly_tax = prop.tax_annual / 12
            net_monthly = monthly_rent - monthly_tax
            if prop.hoa is not None:
                net_monthly -= prop.hoa
            expenses_note = f", est. net ${net_monthly:,.0f}/mo"

        return Score(
            name=self.name,
            value=value,
            detail=f"Rent ${monthly_rent:,.0f}/mo ({rent_ratio:.2%} of price), GRM {grm:.1f}{expenses_note}",
        )
