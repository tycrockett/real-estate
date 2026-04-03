from __future__ import annotations

import re
import tempfile
from datetime import date
from pathlib import Path

import pdfplumber
import requests

from realestate.models import Property, PropertyType
from realestate.sources import register

PDF_URLS = {
    "salt_lake": "http://documents.mtcutah.com/nod/NOD-SL.pdf",
    "north": "http://documents.mtcutah.com/nod/NOD-SURRNORTH.pdf",
    "south_adjacent": "http://documents.mtcutah.com/nod/NOD-SURRSOUTH.pdf",
    "southern": "http://documents.mtcutah.com/nod/NOD-SOUTHERN.pdf",
}

# Which counties are in which PDF region
COUNTY_TO_REGION = {
    "SALT LAKE": "salt_lake",
    "WEBER": "north",
    "DAVIS": "north",
    "CACHE": "north",
    "SUMMIT": "north",
    "WASATCH": "north",
    "UINTAH": "north",
    "BOX ELDER": "north",
    "RICH": "north",
    "MORGAN": "north",
    "UTAH": "south_adjacent",
    "TOOELE": "south_adjacent",
    "SANPETE": "south_adjacent",
    "JUAB": "south_adjacent",
    "WASHINGTON": "southern",
    "IRON": "southern",
    "BEAVER": "southern",
    "GARFIELD": "southern",
    "EMERY": "southern",
    "GRAND": "southern",
    "SEVIER": "southern",
    "WAYNE": "southern",
    "MILLARD": "southern",
    "KANE": "southern",
    "PIUTE": "southern",
    "SAN JUAN": "southern",
    "DAGGETT": "north",
    "DUCHESNE": "north",
    "CARBON": "south_adjacent",
}

PROPERTY_TYPE_MAP = {
    "SFR": PropertyType.SINGLE_FAMILY,
    "SINGLE FAMILY": PropertyType.SINGLE_FAMILY,
    "CONDOMINIUM": PropertyType.CONDO,
    "CONDO": PropertyType.CONDO,
    "TOWNHOUSE": PropertyType.TOWNHOUSE,
    "MOBILE HOME": PropertyType.SINGLE_FAMILY,
    "RESIDENTIAL (NEC)": PropertyType.SINGLE_FAMILY,
    "RESIDENTIAL LOT": PropertyType.LAND,
    "COMMERCIAL": PropertyType.COMMERCIAL,
    "MULTI FAMILY": PropertyType.MULTI_FAMILY,
}

# Top 5 populated Utah counties
TARGET_COUNTIES = {"SALT LAKE", "UTAH", "DAVIS", "WEBER", "WASHINGTON"}


_UTAH_COUNTIES = sorted(COUNTY_TO_REGION.keys(), key=len, reverse=True)


def _match_utah_county(text: str) -> str:
    text_upper = text.upper().strip()
    for county in _UTAH_COUNTIES:
        if text_upper.startswith(county):
            return county
    return text_upper.split()[0] if text_upper else ""


def _extract_field(text: str, pattern: str) -> str:
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _parse_money(val: str) -> float | None:
    if not val:
        return None
    cleaned = val.replace(",", "").replace("$", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_date(val: str) -> date | None:
    if not val:
        return None
    try:
        month, day, year = val.split("/")
        return date(int(year), int(month), int(day))
    except (ValueError, IndexError):
        return None


_STREET_SUFFIXES = {
    "ST", "AVE", "DR", "LN", "BLVD", "WAY", "RD", "CIR", "CT", "PL",
    "TRL", "PKWY", "HWY", "LOOP",
}
_DIRECTIONS = {"N", "S", "E", "W", "NE", "NW", "SE", "SW"}


def _split_addr_name(text: str, known_addr: str) -> tuple[str, str]:
    """Split 'ADDRESS OWNER_NAME' into (address, name).

    If known_addr is found in text, use it as the split point.
    Otherwise, use heuristic boundary detection.
    """
    if known_addr and known_addr in text:
        idx = text.index(known_addr)
        return text[: idx + len(known_addr)].strip(), text[idx + len(known_addr) :].strip()

    # Fallback: consume address tokens greedily
    words = text.split()
    last_addr_idx = 0
    for i, w in enumerate(words):
        if re.match(r"^\d+$", w):
            last_addr_idx = i
        elif w in _DIRECTIONS:
            last_addr_idx = i
        elif w in _STREET_SUFFIXES:
            last_addr_idx = i
        elif i > 0 and last_addr_idx == i - 1:
            lookahead = words[i + 1 : i + 3]
            if any(la in _STREET_SUFFIXES for la in lookahead):
                last_addr_idx = i
                continue
            break
        else:
            break

    return " ".join(words[: last_addr_idx + 1]), " ".join(words[last_addr_idx + 1 :])


def _parse_record(rec_text: str) -> dict | None:
    lines = rec_text.split("\n")
    if len(lines) < 6:
        return None

    # Line 1: "Property Address [address] [owner name]"
    # Line 2: "[city], [state] [zip] [owner mailing address]"
    # Line 3: "County : [county] [owner city] [owner state] [owner zip]"
    city_match = re.match(
        r"^([A-Z][A-Z\s.]+?),\s*([A-Z]{2})\s+(\d{5}(?:-\d{0,4})?)",
        lines[2] if len(lines) > 2 else "",
    )
    if not city_match:
        return None

    city = city_match.group(1).strip()
    state = city_match.group(2)
    zip_code = city_match.group(3)

    # Owner mailing street address (after property city/zip on line 2)
    owner_mail_street = lines[2][city_match.end():].strip()

    # Property address + owner name from line 1
    prop_addr_raw = lines[1].replace("Property Address", "").strip() if len(lines) > 1 else ""

    # Split line 1 into property address and owner name
    address, owner_name = _split_addr_name(prop_addr_raw, owner_mail_street)

    # Use owner mailing addr as property address if it starts with a digit
    if owner_mail_street and re.match(r"\d", owner_mail_street):
        address = owner_mail_street

    # Owner mailing city/state/zip from line 3 (after county name)
    county_raw = _extract_field(rec_text, r"County\s*:\s*(.+?)(?:\n|$)")
    county = _match_utah_county(county_raw)

    # Extract owner city/state/zip: everything after the county name on line 3
    owner_mail_city_state_zip = ""
    if county and county_raw:
        remainder = county_raw[len(county):].strip()
        # Parse: "CITY_NAME STATE ZIP - PLUS4"
        csz_match = re.match(r"(.+?)\s+([A-Z]{2})\s+(\d{5}(?:\s*-\s*\d{0,4})?)", remainder)
        if csz_match:
            owner_mail_city_state_zip = (
                f"{csz_match.group(1).strip()}, {csz_match.group(2)} {csz_match.group(3).replace(' ', '')}"
            )

    parcel_id = _extract_field(rec_text, r"Parcel ID\s*:\s*(\S+)")
    owner_occupied = _extract_field(rec_text, r"Owner Occupied\s*:\s*([YN])")
    prop_type_raw = _extract_field(rec_text, r"Property Type\s*:\s*([A-Z\s()]+?)(?:\n|$)")
    doc_type = _extract_field(rec_text, r"Doc Type\s*:\s*(NOTICE OF (?:DEFAULT|TRUSTEE'?S? SALE|SALE)|LIS PENDENS)")
    recording_date = _extract_field(rec_text, r"Recording Date\s*:\s*(\d{2}/\d{2}/\d{4})")
    fore_effective = _extract_field(rec_text, r"Fore Effective\s*:?\s*(\d{2}/\d{2}/\d{4})")
    orig_mtg_amt = _extract_field(rec_text, r"Orig Mtg Amt\s*:\s*\$?([\d,]+)")
    default_amt = _extract_field(rec_text, r"Default Amt\s*:\s*\$?([\d,]+)")
    unpaid_balance = _extract_field(rec_text, r"Unpaid Balance\s*:?\s*\$?([\d,]+)")
    current_value = _extract_field(rec_text, r"Current Value\s*:\s*\$?([\d,]+)")
    cltv_ratio = _extract_field(rec_text, r"CLTV Ratio\s*:\s*([\d.]+)")
    lien_position = _extract_field(rec_text, r"Lien position\s*:\s*(\d+)")
    lender = _extract_field(rec_text, r"Lender Name\s*:\s*(.+?)(?:\s{2,}Orig Lender|\n)")
    orig_lender = _extract_field(rec_text, r"Orig Lender\s*:\s*([A-Z][A-Z\s&'/.,]+?)(?:\s{2,}|\n)")
    trustee = _extract_field(rec_text, r"Trustee Name\s*:\s*(.+?)(?:\s{2,}Trustee Phone|\n)")
    trustee_sale = _extract_field(rec_text, r"Trustee Sale#\s*:\s*(\S+?)(?:\s+Case|\s{2,}|\n)")
    doc_num = _extract_field(rec_text, r"Doc #\s*:\s*(\S+)")
    orig_rec_date = _extract_field(rec_text, r"Orig Rec\.\s*Date\s*:?\s*(\d{2}/\d{2}/\d{4})")

    return {
        "address": address,
        "city": city,
        "state": state,
        "zip_code": zip_code,
        "county": county,
        "parcel_id": parcel_id,
        "owner_occupied": owner_occupied,
        "property_type_raw": prop_type_raw.strip(),
        "doc_type": doc_type,
        "recording_date": recording_date,
        "fore_effective": fore_effective,
        "orig_mtg_amt": orig_mtg_amt,
        "default_amt": default_amt,
        "unpaid_balance": unpaid_balance,
        "current_value": current_value,
        "cltv_ratio": cltv_ratio,
        "lien_position": lien_position,
        "lender": lender,
        "orig_lender": orig_lender,
        "trustee": trustee,
        "trustee_sale": trustee_sale,
        "doc_num": doc_num,
        "orig_rec_date": orig_rec_date,
        "owner_name": owner_name,
        "owner_mail_street": owner_mail_street,
        "owner_mail_city_state_zip": owner_mail_city_state_zip,
    }


def _download_pdf(url: str, cache_dir: Path) -> Path:
    filename = url.rsplit("/", 1)[-1]
    cached = cache_dir / filename
    if cached.exists():
        return cached
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    cached.write_bytes(resp.content)
    return cached


def _extract_records_from_pdf(pdf_path: Path) -> list[str]:
    full_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"

    records = re.split(r"Rec # : \d+\)", full_text)
    return [r.strip() for r in records if r.strip() and "Owner Information" in r]


@register("meridian_nod")
class MeridianNodSource:
    name = "meridian_nod"

    def __init__(self, cache_dir: str | None = None, regions: list[str] | None = None):
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = Path(tempfile.gettempdir()) / "realestate_nod_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.regions = regions

    def fetch(self, **filters) -> list[Property]:
        county_filter = filters.get("county", "").upper()
        city_filter = filters.get("city", "").upper()
        doc_type_filter = filters.get("doc_type", "").upper()

        regions_to_fetch = self._resolve_regions(county_filter)

        properties = []
        for region, url in regions_to_fetch.items():
            pdf_path = _download_pdf(url, self.cache_dir)
            raw_records = _extract_records_from_pdf(pdf_path)

            for rec_text in raw_records:
                parsed = _parse_record(rec_text)
                if parsed is None:
                    continue

                # Apply county filter
                if county_filter and county_filter not in parsed["county"].upper():
                    continue

                # Apply city filter
                if city_filter and city_filter not in parsed["city"].upper():
                    continue

                # Apply doc type filter
                if doc_type_filter and doc_type_filter not in parsed.get("doc_type", "").upper():
                    continue

                # Map to Property model
                orig_mtg = _parse_money(parsed["orig_mtg_amt"])

                prop = Property(
                    source="meridian_nod",
                    source_id=f"NOD-{parsed['doc_num'] or parsed['parcel_id']}",
                    address=parsed["address"],
                    city=parsed["city"].title(),
                    state=parsed["state"],
                    zip_code=parsed["zip_code"].split("-")[0],
                    price=orig_mtg or 0.0,
                    property_type=PROPERTY_TYPE_MAP.get(parsed["property_type_raw"].upper()),
                    list_date=_parse_date(parsed["recording_date"]),
                    raw={
                        "county": parsed["county"],
                        "parcel_id": parsed["parcel_id"],
                        "owner_occupied": parsed["owner_occupied"],
                        "doc_type": parsed["doc_type"],
                        "recording_date": parsed["recording_date"],
                        "fore_effective": parsed["fore_effective"],
                        "orig_mtg_amt": orig_mtg,
                        "default_amt": _parse_money(parsed["default_amt"]),
                        "unpaid_balance": _parse_money(parsed["unpaid_balance"]),
                        "current_value": _parse_money(parsed["current_value"]),
                        "cltv_ratio": parsed["cltv_ratio"],
                        "lien_position": parsed["lien_position"],
                        "lender": parsed["lender"],
                        "orig_lender": parsed["orig_lender"],
                        "trustee": parsed["trustee"],
                        "trustee_sale": parsed["trustee_sale"],
                        "property_type_raw": parsed["property_type_raw"],
                        "orig_rec_date": parsed["orig_rec_date"],
                        "owner_name": parsed["owner_name"],
                        "owner_mail_street": parsed["owner_mail_street"],
                        "owner_mail_city_state_zip": parsed["owner_mail_city_state_zip"],
                    },
                )
                properties.append(prop)

        return properties

    def _resolve_regions(self, county_filter: str) -> dict[str, str]:
        if self.regions:
            return {r: PDF_URLS[r] for r in self.regions if r in PDF_URLS}

        if county_filter:
            region = COUNTY_TO_REGION.get(county_filter)
            if region:
                return {region: PDF_URLS[region]}

        # Default: fetch all regions covering the 5 target counties
        return PDF_URLS
