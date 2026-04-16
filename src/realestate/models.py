from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, computed_field


class PropertyType(str, Enum):
    SINGLE_FAMILY = "single_family"
    MULTI_FAMILY = "multi_family"
    CONDO = "condo"
    TOWNHOUSE = "townhouse"
    LAND = "land"
    COMMERCIAL = "commercial"


class Property(BaseModel):
    source: str
    source_id: str
    address: str
    city: str
    state: str
    zip_code: str
    price: float
    bedrooms: int | None = None
    bathrooms: float | None = None
    sqft: int | None = None
    lot_sqft: int | None = None
    property_type: PropertyType | None = None
    year_built: int | None = None
    list_date: date | None = None
    estimated_rent: float | None = None
    hoa: float | None = None
    tax_annual: float | None = None
    url: str | None = None
    normalized_address: str | None = None
    raw: dict | None = None

    @computed_field
    @property
    def price_per_sqft(self) -> float | None:
        if self.sqft and self.sqft > 0:
            return round(self.price / self.sqft, 2)
        return None


class Score(BaseModel):
    name: str
    value: float
    detail: str


class ScoredProperty(BaseModel):
    property: Property
    scores: list[Score]
    total_score: float
