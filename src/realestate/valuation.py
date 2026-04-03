from __future__ import annotations

import math
import re
from datetime import date

import requests

# Average 30-year fixed mortgage rates by year (Freddie Mac PMMS annual averages)
HISTORICAL_RATES = {
    1995: 7.93, 1996: 7.81, 1997: 7.60, 1998: 6.94, 1999: 7.44,
    2000: 8.05, 2001: 6.97, 2002: 6.54, 2003: 5.83, 2004: 5.84,
    2005: 5.87, 2006: 6.41, 2007: 6.34, 2008: 6.03, 2009: 5.04,
    2010: 4.69, 2011: 4.45, 2012: 3.66, 2013: 3.98, 2014: 4.17,
    2015: 3.85, 2016: 3.65, 2017: 3.99, 2018: 4.54, 2019: 3.94,
    2020: 3.11, 2021: 2.96, 2022: 5.34, 2023: 6.81, 2024: 6.72,
    2025: 6.65, 2026: 6.50,
}


def _get_rate(year: int) -> float:
    """Get estimated mortgage rate for origination year."""
    if year in HISTORICAL_RATES:
        return HISTORICAL_RATES[year]
    if year < min(HISTORICAL_RATES):
        return 8.0
    return HISTORICAL_RATES[max(HISTORICAL_RATES)]


def estimate_remaining_balance(
    original_amount: float,
    origination_date: date,
    as_of: date | None = None,
    rate: float | None = None,
    term_years: int = 30,
) -> dict:
    """Estimate remaining mortgage balance using standard amortization.

    Returns dict with: remaining_balance, monthly_payment, rate_used,
    months_paid, months_remaining, total_paid, principal_paid, interest_paid
    """
    if as_of is None:
        as_of = date.today()

    if rate is None:
        rate = _get_rate(origination_date.year)

    monthly_rate = rate / 100 / 12
    total_months = term_years * 12

    # Monthly payment (standard amortization formula)
    if monthly_rate > 0:
        payment = original_amount * (monthly_rate * (1 + monthly_rate) ** total_months) / (
            (1 + monthly_rate) ** total_months - 1
        )
    else:
        payment = original_amount / total_months

    # Months elapsed
    months_elapsed = (as_of.year - origination_date.year) * 12 + (as_of.month - origination_date.month)
    months_elapsed = max(0, min(months_elapsed, total_months))

    # Remaining balance after N payments
    if monthly_rate > 0:
        remaining = original_amount * (
            (1 + monthly_rate) ** total_months - (1 + monthly_rate) ** months_elapsed
        ) / ((1 + monthly_rate) ** total_months - 1)
    else:
        remaining = original_amount - (payment * months_elapsed)

    remaining = max(0.0, remaining)
    total_paid = payment * months_elapsed
    principal_paid = original_amount - remaining
    interest_paid = total_paid - principal_paid

    return {
        "remaining_balance": round(remaining, 2),
        "monthly_payment": round(payment, 2),
        "rate_used": rate,
        "months_paid": months_elapsed,
        "months_remaining": total_months - months_elapsed,
        "total_paid": round(total_paid, 2),
        "principal_paid": round(principal_paid, 2),
        "interest_paid": round(interest_paid, 2),
    }


# --- UGRC Assessed Value Lookup ---

UGRC_BASE = "https://services1.arcgis.com/99lidPhWCzftIe9K/ArcGIS/rest/services"

COUNTY_SERVICE_NAMES = {
    "SALT LAKE": "SaltLake",
    "UTAH": "Utah",
    "DAVIS": "Davis",
    "WEBER": "Weber",
    "WASHINGTON": "Washington",
    "CACHE": "Cache",
    "TOOELE": "Tooele",
    "SUMMIT": "Summit",
    "IRON": "Iron",
    "BOX ELDER": "BoxElder",
    "WASATCH": "Wasatch",
    "SANPETE": "Sanpete",
    "SEVIER": "Sevier",
    "MILLARD": "Millard",
    "MORGAN": "Morgan",
    "RICH": "Rich",
    "JUAB": "Juab",
    "CARBON": "Carbon",
    "EMERY": "Emery",
    "GRAND": "Grand",
    "SAN JUAN": "SanJuan",
    "KANE": "Kane",
    "GARFIELD": "Garfield",
    "PIUTE": "Piute",
    "WAYNE": "Wayne",
    "BEAVER": "Beaver",
    "DAGGETT": "Daggett",
    "DUCHESNE": "Duchesne",
    "UINTAH": "Uintah",
}

UGRC_OUT_FIELDS = (
    "PARCEL_ID,PARCEL_ADD,PARCEL_CITY,TOTAL_MKT_VALUE,LAND_MKT_VALUE,"
    "BLDG_SQFT,BUILT_YR,FLOORS_CNT,PARCEL_ACRES"
)


def _normalize_address_for_search(address: str) -> str:
    """Normalize address for UGRC LIKE query."""
    addr = address.upper().strip()
    # Remove unit/apt suffixes for broader matching
    addr = re.sub(r'\s+(UNIT|APT|STE|#)\s*\S*$', '', addr)
    return addr


def lookup_ugrc_value(
    address: str,
    county: str,
    city: str = "",
) -> dict:
    """Look up property assessed value from UGRC ArcGIS FeatureServer.

    Returns dict with: total_mkt_value, land_mkt_value, bldg_sqft, built_yr, etc.
    """
    service_name = COUNTY_SERVICE_NAMES.get(county.upper())
    if not service_name:
        return {"error": f"Unknown county: {county}"}

    url = f"{UGRC_BASE}/Parcels_{service_name}_LIR/FeatureServer/0/query"
    search_addr = _normalize_address_for_search(address)

    # Try exact match first, then LIKE
    for where_clause in [
        f"PARCEL_ADD = '{search_addr}'",
        f"PARCEL_ADD LIKE '{search_addr}%'",
    ]:
        try:
            resp = requests.get(
                url,
                params={
                    "where": where_clause,
                    "outFields": UGRC_OUT_FIELDS,
                    "f": "json",
                    "resultRecordCount": 5,
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            return {"error": f"UGRC request failed: {e}"}

        features = data.get("features", [])
        if features:
            break
    else:
        return {"error": None, "total_mkt_value": None, "message": "No matching parcel found"}

    # Pick best match (prefer one with value data)
    best = None
    for f in features:
        attrs = f["attributes"]
        if attrs.get("TOTAL_MKT_VALUE") and attrs["TOTAL_MKT_VALUE"] > 0:
            best = attrs
            break
    if best is None:
        best = features[0]["attributes"]

    return {
        "error": None,
        "total_mkt_value": best.get("TOTAL_MKT_VALUE"),
        "land_mkt_value": best.get("LAND_MKT_VALUE"),
        "bldg_sqft": best.get("BLDG_SQFT"),
        "built_yr": best.get("BUILT_YR"),
        "floors_cnt": best.get("FLOORS_CNT"),
        "parcel_acres": best.get("PARCEL_ACRES"),
        "parcel_id_ugrc": best.get("PARCEL_ID"),
        "parcel_add_ugrc": best.get("PARCEL_ADD"),
        "source": "ugrc",
    }
