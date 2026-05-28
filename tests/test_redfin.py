import json
from unittest.mock import patch, MagicMock
from redfin_scout.redfin import RedfinClient
from redfin_scout.models import Listing

# Mock home using VERIFIED field paths from API discovery
MOCK_HOME = {
    "mlsId": {"value": "MLS123"},
    "streetLine": {"value": "456 Oak Ave"},
    "city": "Bellevue",
    "state": "WA",
    "zip": "98004",
    "uiPropertyType": 1,
    "dom": {"value": 35},
    "price": {"value": 650000},
    "listingRemarks": "Beautiful home, FHA eligible.",
    "listingAgent": {"name": "Jane Smith", "redfinAgentId": "agent_abc"},
    "listingBroker": {"name": "Test Realty"},
}

MOCK_PAYLOAD = json.dumps({
    "errorMessage": "success",
    "resultCode": 0,
    "payload": {
        "homes": [MOCK_HOME],
        "moreDataAvailable": False,
    }
})


def make_resp(body: str, status: int = 200) -> MagicMock:
    m = MagicMock()
    m.status_code = status
    m.text = "{}&&" + body
    return m


def test_parses_listing_fields():
    client = RedfinClient()
    with patch("redfin_scout.redfin.requests.get", return_value=make_resp(MOCK_PAYLOAD)):
        listings = client.fetch_county_listings(region_id=118, county="King")
    assert len(listings) == 1
    l = listings[0]
    assert l.mls_id == "MLS123"
    assert l.address == "456 Oak Ave, Bellevue, WA 98004"
    assert l.days_on_market == 35
    assert l.current_price == 650000
    assert l.county == "King"
    assert l.property_type == "Single Family"


def test_dom_filter_excludes_under_30():
    fresh_home = {**MOCK_HOME, "mlsId": {"value": "NEW1"}, "dom": {"value": 10}}
    body = json.dumps({
        "errorMessage": "success", "resultCode": 0,
        "payload": {"homes": [MOCK_HOME, fresh_home], "moreDataAvailable": False}
    })
    client = RedfinClient()
    with patch("redfin_scout.redfin.requests.get", return_value=make_resp(body)):
        listings = client.fetch_county_listings(region_id=118, county="King")
    assert len(listings) == 1
    assert listings[0].mls_id == "MLS123"


def test_distressed_listing_excluded_at_parse():
    distressed = {**MOCK_HOME, "mlsId": {"value": "DIST1"}, "listingRemarks": "Cash only. As-is sale."}
    body = json.dumps({
        "errorMessage": "success", "resultCode": 0,
        "payload": {"homes": [distressed], "moreDataAvailable": False}
    })
    client = RedfinClient()
    with patch("redfin_scout.redfin.requests.get", return_value=make_resp(body)):
        listings = client.fetch_county_listings(region_id=118, county="King")
    assert listings == []


def test_no_price_listing_excluded():
    no_price = {**MOCK_HOME, "mlsId": {"value": "AUC1"}, "price": {"value": None}}
    body = json.dumps({
        "errorMessage": "success", "resultCode": 0,
        "payload": {"homes": [no_price], "moreDataAvailable": False}
    })
    client = RedfinClient()
    with patch("redfin_scout.redfin.requests.get", return_value=make_resp(body)):
        listings = client.fetch_county_listings(region_id=118, county="King")
    assert listings == []


def test_retries_on_non_200_then_succeeds():
    fail = make_resp("{}", status=429)
    success = make_resp(MOCK_PAYLOAD)
    client = RedfinClient()
    with patch("redfin_scout.redfin.requests.get", side_effect=[fail, fail, success]):
        with patch("redfin_scout.redfin.time.sleep"):
            listings = client.fetch_county_listings(region_id=118, county="King")
    assert len(listings) == 1


def test_returns_empty_after_max_retries():
    fail = make_resp("{}", status=429)
    client = RedfinClient()
    with patch("redfin_scout.redfin.requests.get", side_effect=[fail, fail, fail]):
        with patch("redfin_scout.redfin.time.sleep"):
            listings = client.fetch_county_listings(region_id=118, county="King")
    assert listings == []


MOCK_AGENT = json.dumps({
    "errorMessage": "success", "resultCode": 0,
    "payload": {
        "emailAddress": "jane@testrealty.com",
        "phones": [{"phoneNumber": "206-555-9876", "type": "CELL"}],
    }
})


def test_agent_profile_enriches_email_and_phone():
    client = RedfinClient()
    with patch("redfin_scout.redfin.requests.get", side_effect=[make_resp(MOCK_PAYLOAD), make_resp(MOCK_AGENT)]):
        listings = client.fetch_county_listings(region_id=118, county="King")
    assert listings[0].agent_email == "jane@testrealty.com"
    assert listings[0].agent_phone == "206-555-9876"


def test_agent_profile_cached_across_listings():
    client = RedfinClient()
    home2 = {**MOCK_HOME, "mlsId": {"value": "MLS999"}}
    two_homes = json.dumps({
        "errorMessage": "success", "resultCode": 0,
        "payload": {"homes": [MOCK_HOME, home2], "moreDataAvailable": False}
    })
    with patch("redfin_scout.redfin.requests.get", side_effect=[make_resp(two_homes), make_resp(MOCK_AGENT)]) as mock_get:
        listings = client.fetch_county_listings(region_id=118, county="King")
    # 1 search call + 1 agent profile call (cached for second listing)
    assert mock_get.call_count == 2
    assert all(l.agent_email == "jane@testrealty.com" for l in listings)
