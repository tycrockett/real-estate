from realestate.sources import available
from realestate.sources.meridian_nod import (
    _parse_record,
    _match_utah_county,
    _parse_money,
    _parse_date,
    COUNTY_TO_REGION,
    TARGET_COUNTIES,
)


def test_new_sources_registered():
    avail = available()
    assert "hud" in avail
    assert "meridian_nod" in avail


class TestMeridianNodParser:
    SAMPLE_RECORD = """Owner Information
Property Address 925 S 880 E GORDON L BIRCH
NEW HARMONY, UT 84757-7757 925 S 880 E
County : WASHINGTON NEW HARMONY UT 84757 - 7757
Parcel ID : HH-2-36-NS
Owner Occupied : Y Property Type : SFR
Foreclosure Information :
Recent Added Date 03/21/2026 Fore Effective 03/12/2026 CLTV Ratio :
Doc Type : NOTICE OF DEFAULT Lien position : 1 Current Value :
Recording Date : 03/12/2026 Orig Rec. Date 07/25/2023
Doc # : 9545 Original Doc# : 22042
Lender Name : UNIVERSITY FIRST FCU Orig Lender :
Lender Address : Orig Mtg Amt : $235,247
Lender Phone : Default Amt :
Attorney Name : Unpaid Balance
Attorney Phone Trustee Sale# : 92069429F Case# :
Trustee Name : SCALLEY READING BATES HANSEN & Trustee Phone : Plaintiff :
Trustee Address : 15 W SOUTH TEMPLE STE 600 SALT LAKE CITY UT 84101-1536"""

    def test_parse_address(self):
        parsed = _parse_record(self.SAMPLE_RECORD)
        assert parsed is not None
        assert parsed["address"] == "925 S 880 E"

    def test_parse_city_state_zip(self):
        parsed = _parse_record(self.SAMPLE_RECORD)
        assert parsed["city"] == "NEW HARMONY"
        assert parsed["state"] == "UT"
        assert parsed["zip_code"] == "84757-7757"

    def test_parse_county(self):
        parsed = _parse_record(self.SAMPLE_RECORD)
        assert parsed["county"] == "WASHINGTON"

    def test_parse_parcel_id(self):
        parsed = _parse_record(self.SAMPLE_RECORD)
        assert parsed["parcel_id"] == "HH-2-36-NS"

    def test_parse_doc_type(self):
        parsed = _parse_record(self.SAMPLE_RECORD)
        assert parsed["doc_type"] == "NOTICE OF DEFAULT"

    def test_parse_recording_date(self):
        parsed = _parse_record(self.SAMPLE_RECORD)
        assert parsed["recording_date"] == "03/12/2026"

    def test_parse_orig_mtg_amt(self):
        parsed = _parse_record(self.SAMPLE_RECORD)
        assert parsed["orig_mtg_amt"] == "235,247"

    def test_parse_owner_occupied(self):
        parsed = _parse_record(self.SAMPLE_RECORD)
        assert parsed["owner_occupied"] == "Y"

    def test_parse_property_type(self):
        parsed = _parse_record(self.SAMPLE_RECORD)
        assert "SFR" in parsed["property_type_raw"]

    def test_parse_trustee_sale(self):
        parsed = _parse_record(self.SAMPLE_RECORD)
        assert parsed["trustee_sale"] == "92069429F"

    def test_parse_lender(self):
        parsed = _parse_record(self.SAMPLE_RECORD)
        assert "UNIVERSITY FIRST FCU" in parsed["lender"]

    def test_parse_trustee_sale_notice(self):
        record = """Owner Information
Property Address 1941 W 1700 N JESUS SOTO
SAINT GEORGE, UT 84770-4744 1941 W 1700 N
County : WASHINGTON SAINT GEORGE UT 84770 - 4744
Parcel ID : SG-RRE-4-19
Owner Occupied : Y Property Type : MOBILE HOME
Foreclosure Information :
Recent Added Date 02/13/2026 Fore Effective 02/05/2026 CLTV Ratio :
Doc Type : NOTICE OF TRUSTEE'S SALE Lien position : 1 Current Value :
Recording Date : 02/05/2026 Orig Rec. Date 04/30/2024
Doc # : 4564 Original Doc# : 13241
Lender Name : STG COMMUNITY 1 LLC Orig Lender : STG COMMUNITY 1 LLC
Lender Address : Orig Mtg Amt : $50,000
Lender Phone : Default Amt :
Attorney Name : Unpaid Balance
Attorney Phone Trustee Sale# : 7580 Case# :
Trustee Name : BRAD D BOYCE Trustee Phone : Plaintiff :
Trustee Address : 1771 S RANGE RD SARATOGA SPRINGS UT 84045-3947"""
        parsed = _parse_record(record)
        assert parsed["doc_type"] == "NOTICE OF TRUSTEE'S SALE"
        assert parsed["orig_mtg_amt"] == "50,000"

    def test_parse_short_record_returns_none(self):
        assert _parse_record("too short") is None

    def test_parse_no_city_returns_none(self):
        record = "Owner Information\nProperty Address 123 Main\nNO MATCH\nCounty : TEST"
        assert _parse_record(record) is None


class TestUtahCountyMatching:
    def test_match_salt_lake(self):
        assert _match_utah_county("SALT LAKE SALT LAKE CITY UT 84101") == "SALT LAKE"

    def test_match_washington(self):
        assert _match_utah_county("WASHINGTON NEW HARMONY UT 84757") == "WASHINGTON"

    def test_match_box_elder(self):
        assert _match_utah_county("BOX ELDER BRIGHAM CITY UT 84302") == "BOX ELDER"

    def test_match_san_juan(self):
        assert _match_utah_county("SAN JUAN BLANDING UT 84511") == "SAN JUAN"

    def test_all_target_counties_in_region_map(self):
        for county in TARGET_COUNTIES:
            assert county in COUNTY_TO_REGION


class TestHelpers:
    def test_parse_money(self):
        assert _parse_money("235,247") == 235247.0
        assert _parse_money("$1,332,800") == 1332800.0
        assert _parse_money("") is None
        assert _parse_money(None) is None

    def test_parse_date(self):
        d = _parse_date("03/12/2026")
        assert d is not None
        assert d.year == 2026
        assert d.month == 3
        assert d.day == 12
        assert _parse_date("") is None
        assert _parse_date("invalid") is None
