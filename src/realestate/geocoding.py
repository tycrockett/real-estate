from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger(__name__)

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


def normalize_address(address: str, city: str, state: str, zip_code: str) -> str | None:
    """Use Google Geocoding API to normalize a property address.

    Returns a formatted_address consistent with what Google Places
    Autocomplete produces in the intake form.

    Returns the formatted_address from Google, or None if the lookup fails.
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        log.warning("GOOGLE_API_KEY not set — skipping address normalization")
        return None

    full_address = f"{address}, {city}, {state} {zip_code}"
    try:
        resp = requests.get(
            GEOCODE_URL,
            params={"address": full_address, "key": api_key},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        log.exception("Google Geocoding request failed for %s", full_address)
        return None

    if data.get("status") != "OK" or not data.get("results"):
        log.warning("Geocoding returned status=%s for %s", data.get("status"), full_address)
        return None

    return data["results"][0].get("formatted_address")
