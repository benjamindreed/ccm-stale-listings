# Redfin API notes (verified 2026-05-28):
#
# ── GIS (listing search) endpoint ──────────────────────────────────────────
# Base URL: https://www.redfin.com/stingray/api/gis
# Strip "{}&&" prefix before JSON parsing (present on all stingray responses)
#
# status=9 returns active for-sale listings (same results as status=1 for WA)
#   Both status=9 and status=1 return searchStatus=1 (Active) homes.
#   mlsStatus values seen: "Active", "Active Under Contract"
#
# King County WA: region_id=118, region_type=5
#   (Original task spec had region_id=1346 which maps to MA/Boston, not WA)
#
# Verified county region IDs (region_type=5 = county in Redfin):
# COUNTIES = {
#     "King":      (118,  5),   # /county/118/WA/King-County
#     "Snohomish": (2,    5),   # /county/2/WA/Snohomish-County
#     "Pierce":    (3096, 5),   # /county/3096/WA/Pierce-County
#     "Skagit":    (3098, 5),   # /county/3098/WA/Skagit-County
#     "Kitsap":    (3087, 5),   # /county/3087/WA/Kitsap-County
#     "Kittitas":  (3088, 5),   # /county/3088/WA/Kittitas-County
#     "Chelan":    (3074, 5),   # /county/3074/WA/Chelan-County
# }
# Each ID confirmed by: (1) matching Redfin /county/{id}/WA/{Name}-County URL,
# (2) GIS API returning 50 homes all in WA with correct county cities.
#
# dom param: NOT supported server-side
#   Sending dom=30 (or min_days_on_market, daysOnMarket, min_dom, market_time)
#   returns identical results — DOM must be filtered client-side.
#   The API sorts by newest first; older listings appear at higher start offsets.
#   DOM ~30 found around start=1000, DOM ~77 found around start=2000 (King County).
#
# Pagination: use start=0,50,100,... with num_homes=50 (max tested)
# totalCount is always None in response; pagination ends when homes=[]
#
# ── Request params (King County WA active for-sale) ────────────────────────
# al=1, region_id=118, region_type=5, uipt=1,2,3,4,5, status=9,
# num_homes=50, start=0, v=8 (uipt: 1=SFR, 2=Condo, 3=Townhouse, 4=Multi-family, 5=Other)
#
# ── Response field paths (homes array) ─────────────────────────────────────
# MLS ID:         homes[n]["mlsId"]["value"]          (string, e.g. "2528303")
# Street addr:    homes[n]["streetLine"]["value"]      (e.g. "5249 40th Ave NE #404")
# City:           homes[n]["city"]                    (plain string)
# State:          homes[n]["state"]                   (plain string)
# Zip:            homes[n]["zip"]                     (plain string)
#                 also: homes[n]["postalCode"]["value"]
# Property type:  homes[n]["propertyType"]            (int, Redfin internal)
#                 homes[n]["uiPropertyType"]           (int: 1=SFR, 2=Condo, 3=Townhouse, 4=Multi, 5=Other)
#                 uipt filter param uses same scale: uipt=1,2,3,5 in URL
#                 propertyType -> uiPropertyType observed mapping:
#                   6->1 (SFR), 3->2 (Condo), 13->3 (Townhouse), 4->4, 8->5
# Days on market: homes[n]["dom"]["value"]            (int, days)
# Current price:  homes[n]["price"]["value"]          (int, USD)
# Original price: NOT in GIS API response
#                 timeOnRedfin/originalTimeOnRedfin available (ms since epoch)
#                 but original list price requires a separate detail endpoint
#                 (belowTheFold/aboveTheFold — currently 403 blocked for scripts)
# Price history:  NOT in GIS API response
#                 Separate detail endpoint exists but returns 403 without session
# Remarks:        homes[n]["listingRemarks"]          (string, truncated ~500 chars)
# Agent name:     homes[n]["listingAgent"]["name"]    (string)
# Brokerage:      homes[n]["listingBroker"]["name"]   (string)
#                 homes[n]["listingBroker"]["isRedfin"] (bool)
# Agent ID:       homes[n]["listingAgent"]["redfinAgentId"]  (int)
#                 NOTE: only present for Redfin-listed properties
#                 Non-Redfin listings have only {"name": "Agent Name"} — no ID
# Listing ID:     homes[n]["listingId"]              (int)
# Property ID:    homes[n]["propertyId"]             (int)
# Listing URL:    homes[n]["url"]                    (relative path, e.g. "/WA/Seattle/...")
# searchStatus:   homes[n]["searchStatus"]           (1=Active for-sale)
# mlsStatus:      homes[n]["mlsStatus"]              (string: "Active", "Active Under Contract")
#
# ── Agent profile endpoints (Redfin agents only) ───────────────────────────
# Requires agent slug (from listingAgent URL or agent page, e.g. "bliss-ong")
# Slug is NOT in GIS API response — must be derived from redfinAgentId or
# by scraping https://www.redfin.com/agent/{redfinAgentId}
#
# Agent URL/profile data:
#   GET https://www.redfin.com/stingray/agents/data/agent-profile/{slug}/url/get
#   payload["agentEmail"]    -> e.g. "bliss.ong@redfin.com"
#   payload["agentId"]       -> int (same as redfinAgentId)
#   payload["firstName"], payload["lastName"]
#   payload["jobTitle"]      -> e.g. "Redfin Principal Agent"
#   payload["licenseNumber"]
#
# Agent phone:
#   GET https://www.redfin.com/stingray/agents/data/agent-profile/{slug}/phone/get
#   payload["phoneNumber"]   -> e.g. "(425) 549-4563"
#   payload["currentlyTakingCalls"] -> bool
#
# Agent stats:
#   GET https://www.redfin.com/stingray/agents/data/{slug}/agent-stats/get
#   payload["agentId"], payload["homeTransactionsLastYear"], etc.
#
# NOTE: Agent slug can be obtained from https://www.redfin.com/agent/{redfinAgentId}
#   (redirects or renders the agent page with slug in URL/JSON)
#   The agent page embeds JSON containing agentSlug field.
#
# ── Not available via GIS API (require auth/session or separate scrape) ────
# - Original list price (price at time of listing)
# - Price drop history / price change events
# - Full property history (tax records, prior sales)
# - Agent contact info for non-Redfin brokers (Windermere, Keller Williams, etc.)
#   Non-Redfin agent objects only contain {"name": "Agent Name"} — no ID, email, phone

import json
import logging
import time
import requests
from typing import Optional
from redfin_scout.models import Listing

logger = logging.getLogger(__name__)

REDFIN_GIS_URL = "https://www.redfin.com/stingray/api/gis"
REDFIN_AGENT_URL = "https://www.redfin.com/stingray/api/user/agent/{agent_id}"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.redfin.com/",
}
PROPERTY_TYPE_MAP = {1: "Single Family", 2: "Condo", 3: "Townhouse", 4: "Multi-family", 5: "Other"}
EXCLUSION_KEYWORDS = ["cash only", "cash-only", "as-is", "no fha", "uninhabitable"]
PAGE_SIZE = 350
MIN_DOM = 30
MAX_RETRIES = 3


class RedfinClient:
    def __init__(self):
        self._agent_cache: dict[str, dict] = {}

    def fetch_county_listings(self, region_id: int, county: str) -> list[Listing]:
        listings: list[Listing] = []
        start = 0
        while True:
            page = self._fetch_page(region_id, start)
            if page is None:
                break
            homes, more = page
            for home in homes:
                listing = self._parse_home(home, county)
                if listing and listing.days_on_market >= MIN_DOM:
                    if listing.agent_id:
                        agent = self._fetch_agent(listing.agent_id)
                        listing.agent_email = agent.get("email")
                        listing.agent_phone = agent.get("phone")
                    listings.append(listing)
            if len(homes) == 0:
                break
            start += len(homes)
            time.sleep(1)
        return listings

    def _fetch_page(self, region_id: int, start: int) -> Optional[tuple[list, bool]]:
        params = {
            "al": 1,
            "region_id": region_id,
            "region_type": 5,
            "uipt": "1,2,3,4,5",
            "status": 9,
            "num_homes": PAGE_SIZE,
            "start": start,
            "v": 8,
        }
        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.get(REDFIN_GIS_URL, params=params, headers=HEADERS, timeout=30)
                if resp.status_code != 200:
                    logger.warning("Redfin returned %s (attempt %d)", resp.status_code, attempt + 1)
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(2 ** (attempt + 1))
                    continue
                raw = resp.text[4:] if resp.text.startswith("{}&&") else resp.text
                data = json.loads(raw)
                payload = data.get("payload", {})
                return payload.get("homes", []), payload.get("moreDataAvailable", False)
            except Exception as exc:
                logger.warning("Redfin request failed (attempt %d): %s", attempt + 1, exc)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** (attempt + 1))
        logger.error("Redfin: all retries exhausted for region_id=%d start=%d", region_id, start)
        return None

    def _parse_home(self, home: dict, county: str) -> Optional[Listing]:
        try:
            mls_id = str(home.get("mlsId", {}).get("value") or home.get("listingId") or "UNKNOWN")
            street = home.get("streetLine", {}).get("value", "")
            city = home.get("city", "")
            state = home.get("state", "")
            zip_code = home.get("zip", "")
            address = f"{street}, {city}, {state} {zip_code}".strip(", ")
            property_type = PROPERTY_TYPE_MAP.get(home.get("uiPropertyType", 0), "Unknown")
            dom = int(home.get("dom", {}).get("value") or 0)
            current_price = home.get("price", {}).get("value")
            remarks = home.get("listingRemarks") or ""

            if not current_price:
                return None
            if any(kw in remarks.lower() for kw in EXCLUSION_KEYWORDS):
                return None

            agent_info = home.get("listingAgent") or {}
            broker_info = home.get("listingBroker") or {}

            return Listing(
                mls_id=mls_id,
                address=address,
                property_type=property_type,
                days_on_market=dom,
                current_price=int(current_price),
                original_price=None,
                price_history=[],
                remarks=remarks,
                agent_name=agent_info.get("name") or "",
                brokerage=broker_info.get("name") or "",
                agent_id=agent_info.get("redfinAgentId"),
                agent_email=None,
                agent_phone=None,
                county=county,
            )
        except Exception as exc:
            logger.warning("Failed to parse home %s: %s", home.get("mlsId"), exc)
            return None

    def _fetch_agent(self, agent_id: str) -> dict:
        if agent_id in self._agent_cache:
            return self._agent_cache[agent_id]
        url = REDFIN_AGENT_URL.format(agent_id=agent_id)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            raw = resp.text[4:] if resp.text.startswith("{}&&") else resp.text
            payload = json.loads(raw).get("payload", {})
            phones = payload.get("phones", [])
            result = {
                "email": payload.get("emailAddress"),
                "phone": phones[0].get("phoneNumber") if phones else None,
            }
        except Exception as exc:
            logger.warning("Agent profile fetch failed for %s: %s", agent_id, exc)
            result = {}
        self._agent_cache[agent_id] = result
        return result
