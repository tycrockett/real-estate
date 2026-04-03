from __future__ import annotations

from realestate.analyzers import register
from realestate.models import Property, Score


@register("owner_occupied")
class OwnerOccupiedScorer:
    name = "owner_occupied"
    weight = 0.5  # Tiebreaker — useful but less important

    def score(self, prop: Property, context: list[Property]) -> Score:
        raw = prop.raw or {}
        occupied = raw.get("owner_occupied", "")

        if occupied == "Y":
            return Score(
                name=self.name,
                value=75.0,
                detail="Owner occupied — more motivated to negotiate",
            )
        elif occupied == "N":
            return Score(
                name=self.name,
                value=45.0,
                detail="Not owner occupied — investor/absentee owner",
            )
        else:
            return Score(
                name=self.name,
                value=50.0,
                detail="Owner occupancy unknown",
            )
