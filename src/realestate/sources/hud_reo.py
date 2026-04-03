from __future__ import annotations

import requests

from realestate.models import Property, PropertyType
from realestate.sources import register

API_URL = "https://egis.hud.gov/arcgis/rest/services/gotit/REOProperties/MapServer/0/query"


PROPERTY_TYPE_MAP = {
    "Single Family": PropertyType.SINGLE_FAMILY,
    "Condominium": PropertyType.CONDO,
    "Townhouse": PropertyType.TOWNHOUSE,
}


@register("hud")
class HudReoSource:
    name = "hud"

    def __init__(self, state: str = "UT"):
        self.state = state

    def fetch(self, **filters) -> list[Property]:
        state = filters.get("state", self.state)

        params = {
            "where": f"STATE_CODE='{state}'",
            "outFields": "*",
            "f": "json",
            "resultRecordCount": 1000,
        }

        resp = requests.get(API_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        properties = []
        for feature in data.get("features", []):
            attrs = feature.get("attributes", {})

            street_parts = [
                attrs.get("STREET_NUM", ""),
                attrs.get("DIRECTION_PREFIX", ""),
                attrs.get("STREET_NAME", ""),
                attrs.get("STREET_SUFFIX", ""),
            ]
            address = " ".join(p for p in street_parts if p).strip()

            city = attrs.get("CITY", "")
            zip_code = attrs.get("DISPLAY_ZIP_CODE", "")

            if not address or not city:
                continue

            prop = Property(
                source="hud",
                source_id=attrs.get("CASE_NUM", f"HUD-{attrs.get('OBJECTID', '')}"),
                address=address,
                city=city,
                state=attrs.get("STATE_CODE", state),
                zip_code=str(zip_code),
                price=0.0,
                bedrooms=_safe_int(attrs.get("BEDROOM_COUNT")),
                bathrooms=_safe_float(attrs.get("BATHROOM_COUNT")),
                sqft=_safe_int(attrs.get("SQFT_LIVING")),
                property_type=PROPERTY_TYPE_MAP.get(attrs.get("REVITE_NAME")),
                url=f"https://www.hudhomestore.gov/Listing/PropertyDetails.aspx?caseNumber={attrs.get('CASE_NUM', '')}",
                raw=attrs,
            )

            min_price = filters.get("min_price")
            max_price = filters.get("max_price")
            if min_price is not None and prop.price < min_price:
                continue
            if max_price is not None and prop.price > max_price:
                continue

            properties.append(prop)

        return properties


def _safe_int(val) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
