import pytest

from realestate.models import Property, PropertyType
from realestate.sources.mock import MockSource


@pytest.fixture
def mock_source():
    return MockSource(seed=42, count=20)


@pytest.fixture
def sample_properties(mock_source):
    return mock_source.fetch()


@pytest.fixture
def cheap_property():
    return Property(
        source="test",
        source_id="CHEAP-001",
        address="123 Bargain Ave",
        city="Dealtown",
        state="TX",
        zip_code="75001",
        price=100_000,
        bedrooms=3,
        bathrooms=2.0,
        sqft=2000,
        property_type=PropertyType.SINGLE_FAMILY,
        year_built=2000,
        estimated_rent=1200.0,
        tax_annual=2000.0,
    )


@pytest.fixture
def expensive_property():
    return Property(
        source="test",
        source_id="EXPENSIVE-001",
        address="999 Luxury Blvd",
        city="Dealtown",
        state="TX",
        zip_code="75001",
        price=900_000,
        bedrooms=3,
        bathrooms=2.0,
        sqft=2000,
        property_type=PropertyType.SINGLE_FAMILY,
        year_built=2000,
        estimated_rent=2000.0,
        tax_annual=18000.0,
    )
