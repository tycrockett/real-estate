from __future__ import annotations

from datetime import date

from realestate.analyzers import register
from realestate.models import Property, Score


@register("time_pressure")
class TimePressureScorer:
    name = "time_pressure"
    weight = 1.0

    def score(self, prop: Property, context: list[Property]) -> Score:
        raw = prop.raw or {}
        recording_date_str = raw.get("recording_date", "")

        if not recording_date_str:
            return Score(name=self.name, value=30.0, detail="No recording date")

        try:
            month, day, year = recording_date_str.split("/")
            rec_date = date(int(year), int(month), int(day))
        except (ValueError, IndexError):
            return Score(name=self.name, value=30.0, detail=f"Bad date: {recording_date_str}")

        days_ago = (date.today() - rec_date).days

        # Fresher filings = more actionable
        # 0-14 days = 95 (just filed, very fresh)
        # 14-30 days = 85
        # 30-60 days = 70
        # 60-90 days = 55
        # 90-120 days = 40
        # 120+ days = 25 (stale — may already be resolved)
        if days_ago <= 14:
            value = 95.0
        elif days_ago <= 30:
            value = 85.0
        elif days_ago <= 60:
            value = 70.0
        elif days_ago <= 90:
            value = 55.0
        elif days_ago <= 120:
            value = 40.0
        else:
            value = 25.0

        return Score(
            name=self.name,
            value=value,
            detail=f"Filed {days_ago} days ago ({recording_date_str})",
        )
