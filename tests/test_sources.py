import csv
from pathlib import Path

import pytest

from realestate.sources import available, get_source
from realestate.sources.mock import MockSource


def test_mock_source_deterministic():
    s1 = MockSource(seed=42, count=10)
    s2 = MockSource(seed=42, count=10)
    props1 = s1.fetch()
    props2 = s2.fetch()
    assert len(props1) == len(props2)
    for p1, p2 in zip(props1, props2):
        assert p1.source_id == p2.source_id
        assert p1.price == p2.price


def test_mock_source_different_seeds():
    s1 = MockSource(seed=42, count=10)
    s2 = MockSource(seed=99, count=10)
    props1 = s1.fetch()
    props2 = s2.fetch()
    prices1 = [p.price for p in props1]
    prices2 = [p.price for p in props2]
    assert prices1 != prices2


def test_mock_source_filters():
    s = MockSource(seed=42, count=20)
    props = s.fetch(city="Austin", state="TX")
    assert all(p.city == "Austin" for p in props)
    assert all(p.state == "TX" for p in props)


def test_mock_source_price_filter():
    s = MockSource(seed=42, count=50)
    props = s.fetch(min_price=200_000, max_price=400_000)
    assert all(200_000 <= p.price <= 400_000 for p in props)
    assert len(props) > 0


def test_registry_mock_available():
    assert "mock" in available()
    assert "csv" in available()


def test_registry_get_source():
    src = get_source("mock", seed=1, count=5)
    props = src.fetch()
    assert len(props) == 5


def test_registry_unknown_source():
    with pytest.raises(KeyError, match="Unknown source"):
        get_source("nonexistent")


def test_csv_source(tmp_path: Path):
    csv_path = tmp_path / "test.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["address", "city", "state", "zip_code", "price", "sqft", "bedrooms"])
        writer.writeheader()
        writer.writerow({"address": "100 Oak St", "city": "Dallas", "state": "TX", "zip_code": "75201", "price": "350000", "sqft": "1800", "bedrooms": "3"})
        writer.writerow({"address": "200 Elm Ave", "city": "Dallas", "state": "TX", "zip_code": "75202", "price": "275000", "sqft": "1400", "bedrooms": "2"})

    src = get_source("csv", path=str(csv_path))
    props = src.fetch()
    assert len(props) == 2
    assert props[0].address == "100 Oak St"
    assert props[0].price == 350_000
    assert props[0].sqft == 1800


def test_csv_source_missing_file():
    src = get_source("csv", path="/nonexistent/file.csv")
    with pytest.raises(FileNotFoundError):
        src.fetch()
