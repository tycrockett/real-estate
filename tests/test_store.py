from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from realestate.models import Property, PropertyType
from realestate.store import PropertyStore


@pytest.fixture
def store(tmp_path: Path):
    return PropertyStore(db_path=tmp_path / "test.db")


@pytest.fixture
def prop_a():
    return Property(
        source="test",
        source_id="A-001",
        address="100 Main St",
        city="Testville",
        state="UT",
        zip_code="84101",
        price=250_000,
        bedrooms=3,
        sqft=1500,
        property_type=PropertyType.SINGLE_FAMILY,
    )


@pytest.fixture
def prop_b():
    return Property(
        source="test",
        source_id="B-001",
        address="200 Oak Ave",
        city="Testville",
        state="UT",
        zip_code="84102",
        price=350_000,
        bedrooms=4,
        sqft=2000,
        property_type=PropertyType.SINGLE_FAMILY,
    )


class TestUpsert:
    def test_insert_new(self, store, prop_a):
        result = store.upsert([prop_a])
        assert result.new == 1
        assert result.updated == 0
        assert result.unchanged == 0
        assert store.count() == 1

    def test_insert_multiple(self, store, prop_a, prop_b):
        result = store.upsert([prop_a, prop_b])
        assert result.new == 2
        assert store.count() == 2

    def test_unchanged_on_second_insert(self, store, prop_a):
        store.upsert([prop_a])
        result = store.upsert([prop_a])
        assert result.new == 0
        assert result.unchanged == 1
        assert store.count() == 1

    def test_updated_on_price_change(self, store, prop_a):
        store.upsert([prop_a])
        modified = prop_a.model_copy(update={"price": 200_000})
        result = store.upsert([modified])
        assert result.updated == 1
        assert result.unchanged == 0

    def test_updated_on_any_field_change(self, store, prop_a):
        store.upsert([prop_a])
        modified = prop_a.model_copy(update={"bedrooms": 4})
        result = store.upsert([modified])
        assert result.updated == 1


class TestDedup:
    def test_same_source_id_deduped(self, store, prop_a):
        store.upsert([prop_a])
        store.upsert([prop_a])
        store.upsert([prop_a])
        assert store.count() == 1

    def test_different_source_ids_not_deduped(self, store):
        p1 = Property(
            source="test", source_id="X-1",
            address="100 Main St", city="Testville", state="UT",
            zip_code="84101", price=250_000,
        )
        p2 = Property(
            source="test", source_id="X-2",
            address="100 Main St", city="Testville", state="UT",
            zip_code="84101", price=250_000,
        )
        store.upsert([p1, p2])
        assert store.count() == 2

    def test_different_sources_not_deduped(self, store):
        p1 = Property(
            source="source_a", source_id="SAME-ID",
            address="100 Main St", city="Testville", state="UT",
            zip_code="84101", price=250_000,
        )
        p2 = Property(
            source="source_b", source_id="SAME-ID",
            address="100 Main St", city="Testville", state="UT",
            zip_code="84101", price=250_000,
        )
        store.upsert([p1, p2])
        assert store.count() == 2


class TestGetNew:
    def test_get_new_returns_recent(self, store, prop_a, prop_b):
        before = datetime.now(UTC)
        store.upsert([prop_a])
        after_first = datetime.now(UTC)
        store.upsert([prop_b])

        new_since_before = store.get_new(since=before)
        assert len(new_since_before) == 2

        new_since_first = store.get_new(since=after_first)
        assert len(new_since_first) == 1
        assert new_since_first[0].source_id == "B-001"

    def test_get_new_excludes_old(self, store, prop_a):
        store.upsert([prop_a])
        future = datetime.now(UTC) + timedelta(hours=1)
        new = store.get_new(since=future)
        assert len(new) == 0

    def test_repeated_upsert_doesnt_change_first_seen(self, store, prop_a):
        before = datetime.now(UTC)
        store.upsert([prop_a])
        after = datetime.now(UTC)
        # Second upsert should not change first_seen
        store.upsert([prop_a])
        new = store.get_new(since=before)
        assert len(new) == 1

        future = datetime.now(UTC) + timedelta(hours=1)
        new_future = store.get_new(since=future)
        assert len(new_future) == 0


class TestGetAll:
    def test_get_all(self, store, prop_a, prop_b):
        store.upsert([prop_a, prop_b])
        all_props = store.get_all()
        assert len(all_props) == 2

    def test_filter_by_source(self, store):
        p1 = Property(
            source="src_a", source_id="1",
            address="1 A St", city="X", state="UT", zip_code="84101", price=100,
        )
        p2 = Property(
            source="src_b", source_id="2",
            address="2 B St", city="X", state="UT", zip_code="84101", price=200,
        )
        store.upsert([p1, p2])
        assert len(store.get_all(source="src_a")) == 1
        assert len(store.get_all(source="src_b")) == 1

    def test_filter_by_city(self, store, prop_a, prop_b):
        store.upsert([prop_a, prop_b])
        assert len(store.get_all(city="Testville")) == 2
        assert len(store.get_all(city="Nowhere")) == 0


class TestMarkRemoved:
    def test_mark_removed(self, store, prop_a, prop_b):
        store.upsert([prop_a, prop_b])
        assert store.count() == 2

        # Only prop_a still in source
        removed = store.mark_removed("test", {"A-001"})
        assert removed == 1
        assert store.count(status="active") == 1
        assert store.count(status="removed") == 1

    def test_removed_not_in_get_all(self, store, prop_a, prop_b):
        store.upsert([prop_a, prop_b])
        store.mark_removed("test", {"A-001"})
        active = store.get_all()
        assert len(active) == 1
        assert active[0].source_id == "A-001"

    def test_reappearing_property_becomes_active(self, store, prop_a):
        store.upsert([prop_a])
        store.mark_removed("test", set())
        assert store.count(status="active") == 0

        # Property reappears in next fetch
        result = store.upsert([prop_a])
        assert result.unchanged == 1
        assert store.count(status="active") == 1


class TestCount:
    def test_empty_store(self, store):
        assert store.count() == 0

    def test_count_after_inserts(self, store, prop_a, prop_b):
        store.upsert([prop_a, prop_b])
        assert store.count() == 2
