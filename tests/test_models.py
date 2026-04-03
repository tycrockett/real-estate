from realestate.models import Property, PropertyType, Score, ScoredProperty


def test_property_minimal():
    p = Property(
        source="test",
        source_id="1",
        address="123 Main St",
        city="Austin",
        state="TX",
        zip_code="78701",
        price=250_000,
    )
    assert p.price == 250_000
    assert p.bedrooms is None
    assert p.price_per_sqft is None


def test_property_price_per_sqft():
    p = Property(
        source="test",
        source_id="1",
        address="123 Main St",
        city="Austin",
        state="TX",
        zip_code="78701",
        price=300_000,
        sqft=1500,
    )
    assert p.price_per_sqft == 200.0


def test_property_price_per_sqft_zero_sqft():
    p = Property(
        source="test",
        source_id="1",
        address="123 Main St",
        city="Austin",
        state="TX",
        zip_code="78701",
        price=300_000,
        sqft=0,
    )
    assert p.price_per_sqft is None


def test_property_serialization_roundtrip():
    p = Property(
        source="test",
        source_id="1",
        address="123 Main St",
        city="Austin",
        state="TX",
        zip_code="78701",
        price=250_000,
        bedrooms=3,
        property_type=PropertyType.SINGLE_FAMILY,
    )
    data = p.model_dump()
    p2 = Property.model_validate(data)
    assert p == p2


def test_scored_property():
    p = Property(
        source="test",
        source_id="1",
        address="123 Main St",
        city="Austin",
        state="TX",
        zip_code="78701",
        price=250_000,
    )
    scores = [Score(name="test_score", value=80.0, detail="Looks good")]
    sp = ScoredProperty(property=p, scores=scores, total_score=80.0)
    assert sp.total_score == 80.0
    assert sp.scores[0].name == "test_score"
