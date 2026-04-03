from __future__ import annotations

from realestate.analyzers import register
from realestate.models import Property, Score

# Further along in foreclosure = more motivated seller = better deal opportunity
STAGE_SCORES = {
    "NOTICE OF TRUSTEE'S SALE": 95,
    "NOTICE OF SALE": 90,
    "NOTICE OF DEFAULT": 60,
    "LIS PENDENS": 40,
}


@register("distress_stage")
class DistressStageScorer:
    name = "distress_stage"
    weight = 2.0  # Highest weight — most important signal

    def score(self, prop: Property, context: list[Property]) -> Score:
        doc_type = (prop.raw or {}).get("doc_type", "")
        value = STAGE_SCORES.get(doc_type, 30.0)

        return Score(
            name=self.name,
            value=value,
            detail=doc_type or "Unknown stage",
        )
