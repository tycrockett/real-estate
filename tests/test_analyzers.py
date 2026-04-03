from realestate.analyzers import available, score_properties
from realestate.analyzers.price_per_sqft import PricePerSqftScorer
from realestate.analyzers.cash_flow import CashFlowScorer
from realestate.analyzers.comparative import ComparativeScorer
from realestate.models import Property, PropertyType


def _make_property(price, sqft, rent=None, zip_code="75001", bedrooms=3, source_id=None):
    return Property(
        source="test",
        source_id=source_id or f"T-{price}",
        address=f"{price} Test St",
        city="Testville",
        state="TX",
        zip_code=zip_code,
        price=price,
        sqft=sqft,
        bedrooms=bedrooms,
        estimated_rent=rent,
        property_type=PropertyType.SINGLE_FAMILY,
    )


class TestPricePerSqftScorer:
    def test_below_median_scores_high(self):
        scorer = PricePerSqftScorer()
        cheap = _make_property(100_000, 2000)  # $50/sqft
        expensive = _make_property(400_000, 2000)  # $200/sqft
        context = [cheap, expensive]

        score = scorer.score(cheap, context)
        assert score.value > 50

    def test_above_median_scores_low(self):
        scorer = PricePerSqftScorer()
        cheap = _make_property(100_000, 2000)
        expensive = _make_property(400_000, 2000)
        context = [cheap, expensive]

        score = scorer.score(expensive, context)
        assert score.value < 50

    def test_no_sqft_returns_neutral(self):
        scorer = PricePerSqftScorer()
        prop = _make_property(200_000, None)
        score = scorer.score(prop, [prop])
        assert score.value == 50.0


class TestCashFlowScorer:
    def test_high_rent_ratio_scores_high(self):
        scorer = CashFlowScorer()
        good = _make_property(100_000, 1000, rent=1200)  # 1.2% rent ratio
        bad = _make_property(100_000, 1000, rent=400)  # 0.4% rent ratio
        context = [good, bad]

        good_score = scorer.score(good, context)
        bad_score = scorer.score(bad, context)
        assert good_score.value > bad_score.value

    def test_no_rent_returns_neutral(self):
        scorer = CashFlowScorer()
        prop = _make_property(200_000, 1000, rent=None)
        score = scorer.score(prop, [prop])
        assert score.value == 50.0


class TestComparativeScorer:
    def test_below_median_comps_scores_high(self):
        scorer = ComparativeScorer()
        cheap = _make_property(150_000, 1500, zip_code="75001", source_id="A")
        mid = _make_property(250_000, 1500, zip_code="75001", source_id="B")
        pricey = _make_property(350_000, 1500, zip_code="75001", source_id="C")
        context = [cheap, mid, pricey]

        score = scorer.score(cheap, context)
        assert score.value > 50

    def test_no_comps_returns_neutral(self):
        scorer = ComparativeScorer()
        prop = _make_property(200_000, 1500, zip_code="99999", source_id="ALONE")
        other = _make_property(200_000, 1500, zip_code="00000", source_id="FAR")
        score = scorer.score(prop, [prop, other])
        assert score.value == 50.0


class TestScoringPipeline:
    def test_score_properties_returns_sorted(self, sample_properties):
        results = score_properties(sample_properties)
        assert len(results) == len(sample_properties)
        scores = [r.total_score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_good_deal_ranks_first(self):
        good = _make_property(100_000, 2000, rent=1500, zip_code="75001", source_id="GOOD")
        bad = _make_property(500_000, 1000, rent=500, zip_code="75001", source_id="BAD")
        mid = _make_property(250_000, 1500, rent=800, zip_code="75001", source_id="MID")
        context = [good, bad, mid]

        results = score_properties(context)
        assert results[0].property.source_id == "GOOD"

    def test_empty_list(self):
        results = score_properties([])
        assert results == []

    def test_custom_scorers(self, sample_properties):
        results = score_properties(sample_properties, scorers=[("price_per_sqft", 1.0)])
        assert len(results) == len(sample_properties)
        assert all(len(r.scores) == 1 for r in results)

    def test_scorer_registry(self):
        assert "price_per_sqft" in available()
        assert "cash_flow" in available()
        assert "comparative" in available()
