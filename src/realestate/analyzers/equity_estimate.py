from __future__ import annotations

from realestate.analyzers import register
from realestate.models import Property, Score


@register("equity_estimate")
class EquityEstimateScorer:
    name = "equity_estimate"
    weight = 1.5

    def score(self, prop: Property, context: list[Property]) -> Score:
        raw = prop.raw or {}

        # Best: use pre-computed equity from valuations table (UGRC + amortization)
        equity_pct = raw.get("_equity_percent")
        estimated_equity = raw.get("_estimated_equity")
        market_value = raw.get("_estimated_market_value")
        remaining = raw.get("_remaining_balance")

        if equity_pct is not None and estimated_equity is not None:
            value = max(0.0, min(100.0, round(equity_pct, 1)))
            return Score(
                name=self.name,
                value=value,
                detail=f"${estimated_equity:,.0f} equity ({equity_pct:.0f}%) — mkt ${market_value:,.0f} vs ${remaining:,.0f} owed",
            )

        # Fallback: CLTV ratio from NOD PDF
        cltv_str = raw.get("cltv_ratio", "")
        if cltv_str:
            try:
                cltv = float(cltv_str)
                if cltv > 0:
                    equity_pct = 100 - cltv
                    value = max(0.0, min(100.0, round(equity_pct, 1)))
                    return Score(
                        name=self.name,
                        value=value,
                        detail=f"CLTV {cltv:.0f}% → ~{equity_pct:.0f}% equity",
                    )
            except ValueError:
                pass

        # No data
        return Score(name=self.name, value=35.0, detail="No equity data available")
