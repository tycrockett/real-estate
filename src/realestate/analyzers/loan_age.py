from __future__ import annotations

from datetime import date

from realestate.analyzers import register
from realestate.models import Property, Score


@register("loan_age")
class LoanAgeScorer:
    name = "loan_age"
    weight = 1.5  # Older loans = more equity built up

    def score(self, prop: Property, context: list[Property]) -> Score:
        raw = prop.raw or {}
        orig_rec_date = raw.get("orig_rec_date", "")

        if not orig_rec_date:
            return Score(name=self.name, value=30.0, detail="No loan origination date")

        try:
            month, day, year = orig_rec_date.split("/")
            orig = date(int(year), int(month), int(day))
        except (ValueError, IndexError):
            return Score(name=self.name, value=30.0, detail=f"Bad date: {orig_rec_date}")

        age_years = (date.today() - orig).days / 365.25

        # Scoring curve:
        # 10+ years = 95 (lots of equity)
        # 7 years = 80
        # 5 years = 65
        # 3 years = 45
        # 1 year = 25
        # <1 year = 15 (little equity, likely underwater)
        if age_years >= 10:
            value = 95.0
        elif age_years >= 1:
            value = round(15 + (age_years / 10) * 80, 1)
        else:
            value = 15.0

        return Score(
            name=self.name,
            value=min(100.0, value),
            detail=f"Loan originated {orig_rec_date} ({age_years:.1f} years)",
        )
