# Redfin Scout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a weekly automated pipeline that scrapes Redfin for stale WA residential listings (30+ DOM, 7 counties), scores them for mortgage opportunity, cross-references listing agents against HubSpot CRM, and writes results to a timestamped Excel file — scheduled every Monday at 7 AM via macOS launchd.

**Architecture:** Five focused Python modules in `redfin_scout/`: a Redfin GIS API client with pagination and retry, a HubSpot CRM contact checker with per-run cache, a pure scoring function, an openpyxl Excel writer, and an orchestrator that wires them together. launchd runs `run.sh` weekly and logs to `~/Library/Logs/redfin-scout.log`.

**Tech Stack:** Python 3.11, requests, openpyxl, python-dotenv, pytest, unittest.mock, macOS launchd

---

## File Map

| File | Responsibility |
|---|---|
| `redfin_scout/__init__.py` | Package marker |
| `redfin_scout/models.py` | Dataclasses: `Listing`, `ScoredListing` |
| `redfin_scout/scorer.py` | Pure scoring function + keyword lists |
| `redfin_scout/hubspot.py` | HubSpot contact search + in-run cache |
| `redfin_scout/redfin.py` | Redfin GIS API client + agent profile fetch + retry |
| `redfin_scout/exporter.py` | openpyxl Excel writer with color coding |
| `redfin_scout/main.py` | Orchestrator: all counties, dedup, HubSpot, score, export |
| `tests/__init__.py` | Package marker |
| `tests/test_scorer.py` | Unit tests for all 8 scoring rules |
| `tests/test_hubspot.py` | Unit tests for CRM lookup + cache behavior |
| `tests/test_exporter.py` | Unit tests for Excel output shape, content, color |
| `tests/test_redfin.py` | Unit tests for response parsing, DOM filter, retry, exclusions |
| `requirements.txt` | requests, openpyxl, python-dotenv, pytest |
| `.env.example` | Template for `HUBSPOT_API_KEY` |
| `run.sh` | Venv activation + `python -m redfin_scout.main` |
| `com.ccm.redfin-scout.plist` | launchd agent: Monday 7 AM, catch-up on wake |

---

### Task 1: Project Scaffold

**Files:**
- Create: `redfin_scout/__init__.py`
- Create: `tests/__init__.py`
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `output/.gitkeep`

- [ ] **Step 1: Create directories and empty init files**

```bash
mkdir -p redfin_scout tests output
touch redfin_scout/__init__.py tests/__init__.py output/.gitkeep
```

- [ ] **Step 2: Write `requirements.txt`**

```
requests==2.31.0
openpyxl==3.1.2
python-dotenv==1.0.0
pytest==7.4.3
```

- [ ] **Step 3: Write `.env.example`**

```
HUBSPOT_API_KEY=your_hubspot_private_app_token_here
```

- [ ] **Step 4: Create virtual environment and install dependencies**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Expected: No errors. `pip list` shows requests, openpyxl, python-dotenv, pytest.

- [ ] **Step 5: Verify pytest runs with zero tests**

```bash
pytest tests/ -v
```

Expected: `no tests ran` — no errors.

- [ ] **Step 6: Commit**

```bash
git add redfin_scout/__init__.py tests/__init__.py requirements.txt .env.example output/.gitkeep
git commit -m "chore: project scaffold — venv, packages, directories"
```

---

### Task 2: Data Models

**Files:**
- Create: `redfin_scout/models.py`

- [ ] **Step 1: Write `models.py`**

```python
from dataclasses import dataclass
from typing import Optional


@dataclass
class Listing:
    mls_id: str
    address: str
    property_type: str
    days_on_market: int
    current_price: Optional[int]
    original_price: Optional[int]
    price_history: list[dict]  # [{"date": "2024-01-01", "price": 500000}]
    remarks: str
    agent_name: str
    brokerage: str
    agent_id: Optional[str]
    agent_email: Optional[str]
    agent_phone: Optional[str]
    county: str


@dataclass
class ScoredListing:
    listing: Listing
    score: int
    reasons: list[str]

    @property
    def reasons_str(self) -> str:
        return " | ".join(self.reasons) if self.reasons else ""
```

- [ ] **Step 2: Verify clean import**

```bash
python -c "from redfin_scout.models import Listing, ScoredListing; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add redfin_scout/models.py
git commit -m "feat: Listing and ScoredListing dataclasses"
```

---

### Task 3: Scoring Engine (TDD)

**Files:**
- Create: `redfin_scout/scorer.py`
- Create: `tests/test_scorer.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_scorer.py`:

```python
import pytest
from redfin_scout.models import Listing
from redfin_scout.scorer import score_listing


def make_listing(**kwargs) -> Listing:
    defaults = dict(
        mls_id="TEST001",
        address="123 Main St, Seattle, WA 98101",
        property_type="Single Family",
        days_on_market=30,
        current_price=500000,
        original_price=500000,
        price_history=[{"date": "2024-01-01", "price": 500000}],
        remarks="",
        agent_name="Test Agent",
        brokerage="Test Brokerage",
        agent_id="agent1",
        agent_email="agent@test.com",
        agent_phone="555-1234",
        county="King",
    )
    defaults.update(kwargs)
    return Listing(**defaults)


def test_dom_45_adds_25():
    listing = make_listing(days_on_market=45)
    score, reasons = score_listing(listing, agent_in_crm=True)
    assert score == 25
    assert "45+ days on market" in reasons


def test_dom_60_stacks_to_45_total():
    listing = make_listing(days_on_market=60)
    score, reasons = score_listing(listing, agent_in_crm=True)
    assert score == 45
    assert "45+ days on market" in reasons
    assert "60+ days on market" in reasons


def test_dom_below_45_no_dom_points():
    listing = make_listing(days_on_market=30)
    score, _ = score_listing(listing, agent_in_crm=True)
    assert score == 0


def test_price_reduction_adds_15():
    listing = make_listing(
        price_history=[
            {"date": "2024-01-01", "price": 520000},
            {"date": "2024-02-01", "price": 500000},
        ]
    )
    score, reasons = score_listing(listing, agent_in_crm=True)
    assert score == 15
    assert "Price reduced" in reasons


def test_single_price_history_entry_no_reduction_points():
    listing = make_listing(price_history=[{"date": "2024-01-01", "price": 500000}])
    score, _ = score_listing(listing, agent_in_crm=True)
    assert score == 0


def test_price_cut_5pct_adds_10():
    listing = make_listing(original_price=530000, current_price=500000)
    score, reasons = score_listing(listing, agent_in_crm=True)
    assert score == 10
    assert "Price cut 5%+" in reasons


def test_price_cut_below_5pct_no_points():
    listing = make_listing(original_price=510000, current_price=500000)
    score, _ = score_listing(listing, agent_in_crm=True)
    assert score == 0


def test_vacant_keywords_add_10():
    for kw in ["vacant", "staged", "investor owned", "investor-owned"]:
        listing = make_listing(remarks=f"Property is {kw}.")
        score, reasons = score_listing(listing, agent_in_crm=True)
        assert score == 10, f"Expected 10 for keyword '{kw}', got {score}"
        assert "Vacant/staged/investor-owned" in reasons


def test_agent_not_in_crm_adds_10():
    listing = make_listing()
    score, reasons = score_listing(listing, agent_in_crm=False)
    assert score == 10
    assert "New agent relationship" in reasons


def test_agent_in_crm_no_points():
    listing = make_listing()
    score, _ = score_listing(listing, agent_in_crm=True)
    assert score == 0


def test_fha_friendly_adds_5():
    listing = make_listing(remarks="FHA approved building.")
    score, reasons = score_listing(listing, agent_in_crm=True)
    assert score == 5
    assert "FHA/VA/conv eligible" in reasons


def test_distressed_subtracts_50_clamped_to_zero():
    listing = make_listing(remarks="Cash only, sold as-is.")
    score, reasons = score_listing(listing, agent_in_crm=True)
    assert score == 0
    assert "⚠ Distressed/unfinanceable" in reasons


def test_distressed_with_dom_45_still_clamped_to_zero():
    # 25 (DOM) - 50 (distressed) = -25, clamped to 0
    listing = make_listing(days_on_market=45, remarks="Cash only.")
    score, _ = score_listing(listing, agent_in_crm=True)
    assert score == 0


def test_all_positive_rules_max_score():
    # DOM 60: +25+20=45, price reduced: +15, 5%+ cut: +10, vacant: +10, new agent: +10, FHA: +5 = 95
    listing = make_listing(
        days_on_market=60,
        current_price=500000,
        original_price=560000,
        price_history=[
            {"date": "2024-01-01", "price": 560000},
            {"date": "2024-02-01", "price": 500000},
        ],
        remarks="Vacant property, FHA eligible.",
    )
    score, reasons = score_listing(listing, agent_in_crm=False)
    assert score == 95
    assert len(reasons) == 7


def test_score_never_negative():
    listing = make_listing(remarks="cash only uninhabitable no fha")
    score, _ = score_listing(listing, agent_in_crm=True)
    assert score >= 0
```

- [ ] **Step 2: Run tests — verify all fail**

```bash
pytest tests/test_scorer.py -v
```

Expected: All fail with `ModuleNotFoundError: No module named 'redfin_scout.scorer'`

- [ ] **Step 3: Write `scorer.py`**

```python
from redfin_scout.models import Listing

DISTRESSED_KEYWORDS = ["cash only", "cash-only", "as-is", "no fha", "uninhabitable", "sold as is"]
VACANT_KEYWORDS = ["vacant", "staged", "investor owned", "investor-owned", "reo", "bank owned"]
FINANCEABLE_KEYWORDS = ["fha", "va loan", "va eligible", "conventional", "fannie mae", "freddie mac"]


def score_listing(listing: Listing, agent_in_crm: bool) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    remarks = (listing.remarks or "").lower()

    if any(kw in remarks for kw in DISTRESSED_KEYWORDS):
        score -= 50
        reasons.append("⚠ Distressed/unfinanceable")

    if listing.days_on_market >= 45:
        score += 25
        reasons.append("45+ days on market")

    if listing.days_on_market >= 60:
        score += 20
        reasons.append("60+ days on market")

    if listing.price_history and len(listing.price_history) > 1:
        score += 15
        reasons.append("Price reduced")

    if (
        listing.original_price
        and listing.current_price
        and listing.original_price > 0
        and (listing.original_price - listing.current_price) / listing.original_price >= 0.05
    ):
        score += 10
        reasons.append("Price cut 5%+")

    if any(kw in remarks for kw in VACANT_KEYWORDS):
        score += 10
        reasons.append("Vacant/staged/investor-owned")

    if not agent_in_crm:
        score += 10
        reasons.append("New agent relationship")

    if any(kw in remarks for kw in FINANCEABLE_KEYWORDS):
        score += 5
        reasons.append("FHA/VA/conv eligible")

    return max(0, score), reasons
```

- [ ] **Step 4: Run tests — verify all pass**

```bash
pytest tests/test_scorer.py -v
```

Expected: All 15 tests pass.

- [ ] **Step 5: Commit**

```bash
git add redfin_scout/scorer.py tests/test_scorer.py
git commit -m "feat: scoring engine — all 8 rules, DOM stacking, distressed clamping"
```

---

### Task 4: HubSpot Client (TDD)

**Files:**
- Create: `redfin_scout/hubspot.py`
- Create: `tests/test_hubspot.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_hubspot.py`:

```python
from unittest.mock import patch, MagicMock
from redfin_scout.hubspot import HubSpotClient


def make_hs_response(total: int) -> MagicMock:
    m = MagicMock()
    m.ok = True
    m.json.return_value = {"total": total, "results": []}
    return m


def test_agent_found_by_email():
    client = HubSpotClient("fake-token")
    with patch("redfin_scout.hubspot.requests.post", return_value=make_hs_response(1)) as mock_post:
        result = client.is_agent_in_crm("agent@test.com", None)
    assert result is True
    mock_post.assert_called_once()


def test_agent_not_found():
    client = HubSpotClient("fake-token")
    with patch("redfin_scout.hubspot.requests.post", return_value=make_hs_response(0)):
        result = client.is_agent_in_crm("nobody@test.com", None)
    assert result is False


def test_falls_back_to_phone_when_email_misses():
    client = HubSpotClient("fake-token")
    with patch("redfin_scout.hubspot.requests.post", side_effect=[make_hs_response(0), make_hs_response(1)]) as mock_post:
        result = client.is_agent_in_crm("agent@test.com", "555-1234")
    assert result is True
    assert mock_post.call_count == 2


def test_result_is_cached():
    client = HubSpotClient("fake-token")
    with patch("redfin_scout.hubspot.requests.post", return_value=make_hs_response(0)) as mock_post:
        client.is_agent_in_crm("a@b.com", "555-0000")
        client.is_agent_in_crm("a@b.com", "555-0000")
    assert mock_post.call_count == 1


def test_returns_false_on_network_error():
    client = HubSpotClient("fake-token")
    with patch("redfin_scout.hubspot.requests.post", side_effect=Exception("timeout")):
        result = client.is_agent_in_crm("agent@test.com", None)
    assert result is False


def test_none_email_and_phone_returns_false_without_calling_api():
    client = HubSpotClient("fake-token")
    with patch("redfin_scout.hubspot.requests.post") as mock_post:
        result = client.is_agent_in_crm(None, None)
    assert result is False
    mock_post.assert_not_called()
```

- [ ] **Step 2: Run tests — verify all fail**

```bash
pytest tests/test_hubspot.py -v
```

Expected: All fail with `ModuleNotFoundError: No module named 'redfin_scout.hubspot'`

- [ ] **Step 3: Write `hubspot.py`**

```python
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)
HUBSPOT_SEARCH_URL = "https://api.hubapi.com/crm/v3/objects/contacts/search"


class HubSpotClient:
    def __init__(self, api_key: str):
        self._api_key = api_key
        self._cache: dict[tuple[Optional[str], Optional[str]], bool] = {}

    def is_agent_in_crm(self, email: Optional[str], phone: Optional[str]) -> bool:
        key = (email, phone)
        if key in self._cache:
            return self._cache[key]
        result = self._lookup(email, phone)
        self._cache[key] = result
        return result

    def _lookup(self, email: Optional[str], phone: Optional[str]) -> bool:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if email:
            try:
                resp = requests.post(
                    HUBSPOT_SEARCH_URL,
                    headers=headers,
                    json={
                        "filterGroups": [
                            {"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}
                        ],
                        "limit": 1,
                    },
                    timeout=10,
                )
                if resp.ok and resp.json().get("total", 0) > 0:
                    return True
            except Exception as exc:
                logger.warning("HubSpot email lookup failed for %s: %s", email, exc)
                return False

        if phone:
            try:
                resp = requests.post(
                    HUBSPOT_SEARCH_URL,
                    headers=headers,
                    json={
                        "filterGroups": [
                            {"filters": [{"propertyName": "phone", "operator": "EQ", "value": phone}]}
                        ],
                        "limit": 1,
                    },
                    timeout=10,
                )
                if resp.ok and resp.json().get("total", 0) > 0:
                    return True
            except Exception as exc:
                logger.warning("HubSpot phone lookup failed for %s: %s", phone, exc)
                return False

        return False
```

- [ ] **Step 4: Run tests — verify all pass**

```bash
pytest tests/test_hubspot.py -v
```

Expected: All 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add redfin_scout/hubspot.py tests/test_hubspot.py
git commit -m "feat: HubSpot CRM client — email/phone lookup with per-run cache"
```

---

### Task 5: Redfin API Discovery

This task verifies the actual Redfin API response shape before building the full client. **The output of this task is a set of documented field names that replace the placeholders in Task 6.**

**Files:**
- Create: `scripts/discover_redfin_api.py` (deleted after Task 7)

- [ ] **Step 1: Create the discovery script**

```bash
mkdir -p scripts
```

`scripts/discover_redfin_api.py`:

```python
#!/usr/bin/env python3
"""One-shot script to inspect Redfin API response shape. Run, document, delete."""
import json
import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.redfin.com/",
}

params = {
    "al": 1,
    "region_id": 1346,   # King County
    "region_type": 5,
    "uipt": "1,2,3,5",
    "status": 9,
    "num_homes": 3,
    "start": 0,
    "v": 8,
}

resp = requests.get("https://www.redfin.com/stingray/api/gis", params=params, headers=HEADERS)
print("HTTP Status:", resp.status_code)

raw = resp.text
if raw.startswith("{}&&"):
    raw = raw[4:]

data = json.loads(raw)
print("resultCode:", data.get("resultCode"))
payload = data.get("payload", {})
print("totalCount:", payload.get("totalCount"))

homes = payload.get("homes", [])
print(f"\nReturned {len(homes)} homes. First home:")
if homes:
    print(json.dumps(homes[0], indent=2))
```

- [ ] **Step 2: Run the discovery script**

```bash
source .venv/bin/activate
python scripts/discover_redfin_api.py
```

- [ ] **Step 3: Document actual field names**

From the printed JSON, find and record the actual field paths for:

| Data Point | Expected field path | Actual (fill in) |
|---|---|---|
| MLS ID | `home["mlsId"]["value"]` or `home["mlsId"]` | |
| Street address | `home["streetLine"]["value"]` | |
| City/state/zip | `home["cityStateZip"]["value"]` | |
| Property type | `home["propertyType"]` (int) | |
| Days on market | `home["daysOnMarket"]["value"]` | |
| Current price | `home["price"]["value"]` | |
| Original price | `home["originalPrice"]` | |
| Price history | `home["priceHistory"]` | |
| Remarks | `home["remarks"]` or `home["listingRemarks"]` | |
| Agent name | `home["listingAgentName"]` | |
| Brokerage | `home["brokerageName"]` | |
| Agent ID | `home["listingAgentId"]` | |

- [ ] **Step 4: Verify status=9 returns active listings — if not, try status=1**

If `totalCount` is 0, change `status` to `1` in the script and re-run. Document which value returns active for-sale listings.

- [ ] **Step 5: Verify county region IDs**

If King County results look wrong (e.g. wrong city names in addresses), find the correct region ID:
1. Visit `https://www.redfin.com/county/176/WA/King-County` in a browser
2. Open DevTools → Network → filter by `stingray`
3. Find the `region_id` in the GIS request URL
4. Update the King County ID and similarly check each other county by visiting their Redfin county pages

- [ ] **Step 6: Check if `dom` parameter filters server-side**

Add `"dom": 30` to params, re-run, compare `totalCount` to the run without `dom`. If count drops, the server-side filter works. Document result — it affects how aggressively we paginate in Task 6.

- [ ] **Step 7: Check agent profile endpoint**

Replace `agent_abc` with a real `listingAgentId` from the response, then run:

```python
agent_id = "<real agent id from step 3>"
url = f"https://www.redfin.com/stingray/api/user/agent/{agent_id}"
resp = requests.get(url, headers=HEADERS)
raw = resp.text[4:] if resp.text.startswith("{}&&") else resp.text
print(json.dumps(json.loads(raw), indent=2))
```

Record the field paths for email and phone in the agent payload.

- [ ] **Step 8: Commit discovery notes**

Open `redfin_scout/redfin.py` (create empty if needed) and add a comment block at the top with your findings:

```python
# Redfin API notes (verified 2026-05-28):
# - Strip "{}&&" prefix before JSON parsing
# - status=? (fill in: 9 or 1) for active for-sale listings
# - dom param: supported/not-supported server-side (fill in)
# - MLS ID: home["..."]["..."] (fill in from discovery)
# - Address: home["..."]["..."] (fill in)
# - DOM: home["..."]["..."] (fill in)
# - Price: home["..."]["..."] (fill in)
# - Agent ID: home["..."] (fill in)
# - Agent email (profile endpoint): payload["..."] (fill in)
# - Agent phone (profile endpoint): payload["phones"][0]["..."] (fill in)
```

```bash
git add scripts/ redfin_scout/redfin.py
git commit -m "chore: Redfin API discovery — response shape documented"
```

---

### Task 6: Redfin Search Client (TDD)

**Files:**
- Modify: `redfin_scout/redfin.py`
- Create: `tests/test_redfin.py`

> **Before writing code:** replace every `home["fieldName"]["value"]` below with the actual field paths you documented in Task 5. The mock home object in the tests must match the actual response shape.

- [ ] **Step 1: Write the failing tests**

`tests/test_redfin.py`:

```python
import json
from unittest.mock import patch, MagicMock
from redfin_scout.redfin import RedfinClient
from redfin_scout.models import Listing

# Update these field names to match Task 5 discovery findings
MOCK_HOME = {
    "mlsId": {"value": "MLS123"},
    "streetLine": {"value": "456 Oak Ave"},
    "cityStateZip": {"value": "Bellevue, WA 98004"},
    "propertyType": 1,
    "daysOnMarket": {"value": 35},
    "price": {"value": 650000},
    "originalPrice": 680000,
    "priceHistory": [
        {"date": "2024-01-01", "price": 680000},
        {"date": "2024-02-01", "price": 650000},
    ],
    "remarks": "Beautiful home, FHA eligible.",
    "listingAgentName": "Jane Smith",
    "brokerageName": "Test Realty",
    "listingAgentId": "agent_abc",
}

MOCK_PAYLOAD = json.dumps({
    "errorMessage": "success",
    "resultCode": 0,
    "payload": {
        "homes": [MOCK_HOME],
        "totalCount": 1,
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
        listings = client.fetch_county_listings(region_id=1346, county="King")
    assert len(listings) == 1
    l = listings[0]
    assert l.mls_id == "MLS123"
    assert l.address == "456 Oak Ave, Bellevue, WA 98004"
    assert l.days_on_market == 35
    assert l.current_price == 650000
    assert l.county == "King"
    assert l.property_type == "Single Family"


def test_dom_filter_excludes_under_30():
    fresh_home = {**MOCK_HOME, "mlsId": {"value": "NEW1"}, "daysOnMarket": {"value": 10}}
    body = json.dumps({
        "errorMessage": "success", "resultCode": 0,
        "payload": {"homes": [MOCK_HOME, fresh_home], "totalCount": 2, "moreDataAvailable": False}
    })
    client = RedfinClient()
    with patch("redfin_scout.redfin.requests.get", return_value=make_resp(body)):
        listings = client.fetch_county_listings(region_id=1346, county="King")
    assert len(listings) == 1
    assert listings[0].mls_id == "MLS123"


def test_distressed_listing_excluded_at_parse():
    distressed = {**MOCK_HOME, "mlsId": {"value": "DIST1"}, "remarks": "Cash only. As-is sale."}
    body = json.dumps({
        "errorMessage": "success", "resultCode": 0,
        "payload": {"homes": [distressed], "totalCount": 1, "moreDataAvailable": False}
    })
    client = RedfinClient()
    with patch("redfin_scout.redfin.requests.get", return_value=make_resp(body)):
        listings = client.fetch_county_listings(region_id=1346, county="King")
    assert listings == []


def test_no_price_listing_excluded():
    no_price = {**MOCK_HOME, "mlsId": {"value": "AUC1"}, "price": {"value": None}}
    body = json.dumps({
        "errorMessage": "success", "resultCode": 0,
        "payload": {"homes": [no_price], "totalCount": 1, "moreDataAvailable": False}
    })
    client = RedfinClient()
    with patch("redfin_scout.redfin.requests.get", return_value=make_resp(body)):
        listings = client.fetch_county_listings(region_id=1346, county="King")
    assert listings == []


def test_retries_on_non_200_then_succeeds():
    fail = make_resp("{}", status=429)
    success = make_resp(MOCK_PAYLOAD)
    client = RedfinClient()
    with patch("redfin_scout.redfin.requests.get", side_effect=[fail, fail, success]):
        with patch("redfin_scout.redfin.time.sleep"):
            listings = client.fetch_county_listings(region_id=1346, county="King")
    assert len(listings) == 1


def test_returns_empty_after_max_retries():
    fail = make_resp("{}", status=429)
    client = RedfinClient()
    with patch("redfin_scout.redfin.requests.get", side_effect=[fail, fail, fail]):
        with patch("redfin_scout.redfin.time.sleep"):
            listings = client.fetch_county_listings(region_id=1346, county="King")
    assert listings == []
```

- [ ] **Step 2: Run tests — verify all fail**

```bash
pytest tests/test_redfin.py -v
```

- [ ] **Step 3: Write `redfin.py` (search client)**

```python
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
PROPERTY_TYPE_MAP = {1: "Single Family", 2: "Condo", 3: "Townhouse", 5: "Multi-family"}
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
            if not more or len(homes) == 0:
                break
            start += PAGE_SIZE
            time.sleep(1)
        return listings

    def _fetch_page(self, region_id: int, start: int) -> Optional[tuple[list, bool]]:
        params = {
            "al": 1,
            "region_id": region_id,
            "region_type": 5,
            "uipt": "1,2,3,5",
            "status": 9,          # update to 1 if discovery shows active=1
            "num_homes": PAGE_SIZE,
            "start": start,
            "v": 8,
        }
        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.get(REDFIN_GIS_URL, params=params, headers=HEADERS, timeout=30)
                if resp.status_code != 200:
                    logger.warning("Redfin returned %s (attempt %d)", resp.status_code, attempt + 1)
                    time.sleep(2 ** (attempt + 1))
                    continue
                raw = resp.text[4:] if resp.text.startswith("{}&&") else resp.text
                data = json.loads(raw)
                payload = data.get("payload", {})
                return payload.get("homes", []), payload.get("moreDataAvailable", False)
            except Exception as exc:
                logger.warning("Redfin request failed (attempt %d): %s", attempt + 1, exc)
                time.sleep(2 ** (attempt + 1))
        logger.error("Redfin: all retries exhausted for region_id=%d start=%d", region_id, start)
        return None

    def _parse_home(self, home: dict, county: str) -> Optional[Listing]:
        try:
            # --- Update field access paths from Task 5 discovery as needed ---
            mls_id = str(
                home.get("mlsId", {}).get("value")
                or home.get("listingId")
                or "UNKNOWN"
            )
            address_line = home.get("streetLine", {}).get("value", "")
            city_state_zip = home.get("cityStateZip", {}).get("value", "")
            address = f"{address_line}, {city_state_zip}".strip(", ")
            property_type = PROPERTY_TYPE_MAP.get(home.get("propertyType", 0), "Unknown")
            dom = int(home.get("daysOnMarket", {}).get("value") or 0)
            current_price = home.get("price", {}).get("value")
            remarks = home.get("remarks") or home.get("listingRemarks") or ""

            # Exclude unfinanceable listings at parse time
            if not current_price:
                return None
            if any(kw in remarks.lower() for kw in EXCLUSION_KEYWORDS):
                return None

            return Listing(
                mls_id=mls_id,
                address=address,
                property_type=property_type,
                days_on_market=dom,
                current_price=int(current_price),
                original_price=int(op) if (op := home.get("originalPrice")) else None,
                price_history=home.get("priceHistory") or [],
                remarks=remarks,
                agent_name=home.get("listingAgentName") or "",
                brokerage=home.get("brokerageName") or home.get("listingBrokerName") or "",
                agent_id=home.get("listingAgentId"),
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
```

- [ ] **Step 4: Run tests — verify all pass**

```bash
pytest tests/test_redfin.py -v
```

Expected: All 6 tests pass.

- [ ] **Step 5: Add agent cache test**

Add to `tests/test_redfin.py`:

```python
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
        listings = client.fetch_county_listings(region_id=1346, county="King")
    assert listings[0].agent_email == "jane@testrealty.com"
    assert listings[0].agent_phone == "206-555-9876"


def test_agent_profile_cached_across_listings():
    client = RedfinClient()
    home2 = {**MOCK_HOME, "mlsId": {"value": "MLS999"}}
    two_homes = json.dumps({
        "errorMessage": "success", "resultCode": 0,
        "payload": {"homes": [MOCK_HOME, home2], "totalCount": 2, "moreDataAvailable": False}
    })
    with patch("redfin_scout.redfin.requests.get", side_effect=[make_resp(two_homes), make_resp(MOCK_AGENT)]) as mock_get:
        listings = client.fetch_county_listings(region_id=1346, county="King")
    # 1 search call + 1 agent profile call (cached for second listing)
    assert mock_get.call_count == 2
    assert all(l.agent_email == "jane@testrealty.com" for l in listings)
```

- [ ] **Step 6: Run full redfin test suite**

```bash
pytest tests/test_redfin.py -v
```

Expected: All 8 tests pass.

- [ ] **Step 7: Delete discovery script**

```bash
rm -rf scripts/
```

- [ ] **Step 8: Commit**

```bash
git add redfin_scout/redfin.py tests/test_redfin.py
git rm -r --cached scripts/ 2>/dev/null; rm -rf scripts/
git commit -m "feat: Redfin client — search, pagination, DOM filter, distressed exclusion, agent profile cache"
```

---

### Task 7: Excel Exporter (TDD)

**Files:**
- Create: `redfin_scout/exporter.py`
- Create: `tests/test_exporter.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_exporter.py`:

```python
import os
import tempfile
from openpyxl import load_workbook
from redfin_scout.models import Listing, ScoredListing
from redfin_scout.exporter import write_excel


def make_scored(score=75, dom=45, agent_email="bob@test.com", original_price=320000) -> ScoredListing:
    listing = Listing(
        mls_id="MLS001",
        address="789 Pine Rd, Tacoma, WA 98401",
        property_type="Condo",
        days_on_market=dom,
        current_price=300000,
        original_price=original_price,
        price_history=[
            {"date": "2024-01-01", "price": 320000},
            {"date": "2024-02-01", "price": 300000},
        ],
        remarks="",
        agent_name="Bob Jones",
        brokerage="Tacoma Realty",
        agent_id="agent2",
        agent_email=agent_email,
        agent_phone="253-555-1111",
        county="Pierce",
    )
    return ScoredListing(listing=listing, score=score, reasons=["45+ days on market", "Price reduced"])


def test_creates_xlsx_file():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "out.xlsx")
        write_excel([make_scored()], path)
        assert os.path.exists(path)


def test_has_13_columns():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "out.xlsx")
        write_excel([make_scored()], path)
        ws = load_workbook(path).active
        assert ws.max_column == 13


def test_header_row():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "out.xlsx")
        write_excel([make_scored()], path)
        ws = load_workbook(path).active
        headers = [ws.cell(1, c).value for c in range(1, 14)]
        assert headers[0] == "Priority Score"
        assert headers[1] == "Opportunity Reasons"
        assert headers[4] == "Days on Market"
        assert headers[12] == "County"


def test_data_row_values():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "out.xlsx")
        write_excel([make_scored(score=75)], path)
        ws = load_workbook(path).active
        assert ws.cell(2, 1).value == 75
        assert ws.cell(2, 3).value == "789 Pine Rd, Tacoma, WA 98401"
        assert ws.cell(2, 13).value == "Pierce"


def test_missing_fields_show_marker():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "out.xlsx")
        sl = make_scored(agent_email=None, original_price=None)
        write_excel([sl], path)
        ws = load_workbook(path).active
        assert ws.cell(2, 7).value == "[MISSING]"   # Original Price col
        assert ws.cell(2, 11).value == "[MISSING]"  # Agent Email col


def test_green_fill_score_60_plus():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "out.xlsx")
        write_excel([make_scored(score=65)], path)
        ws = load_workbook(path).active
        assert ws.cell(2, 1).fill.fgColor.rgb == "FF92D050"


def test_yellow_fill_score_30_to_59():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "out.xlsx")
        write_excel([make_scored(score=45)], path)
        ws = load_workbook(path).active
        assert ws.cell(2, 1).fill.fgColor.rgb == "FFFFEB9C"


def test_red_fill_score_below_30():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "out.xlsx")
        write_excel([make_scored(score=10)], path)
        ws = load_workbook(path).active
        assert ws.cell(2, 1).fill.fgColor.rgb == "FFFFC7CE"


def test_rows_sorted_by_score_descending():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "out.xlsx")
        write_excel([make_scored(score=30), make_scored(score=90), make_scored(score=60)], path)
        ws = load_workbook(path).active
        scores = [ws.cell(r, 1).value for r in range(2, 5)]
        assert scores == [90, 60, 30]
```

- [ ] **Step 2: Run tests — verify all fail**

```bash
pytest tests/test_exporter.py -v
```

- [ ] **Step 3: Write `exporter.py`**

```python
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font
from openpyxl.utils import get_column_letter
from redfin_scout.models import ScoredListing

HEADERS = [
    "Priority Score", "Opportunity Reasons", "Property Address", "Property Type",
    "Days on Market", "Current Price", "Original Price", "Price Reduction History",
    "Listing Agent", "Brokerage", "Agent Email", "Agent Phone", "County",
]
GREEN  = PatternFill("solid", fgColor="FF92D050")
YELLOW = PatternFill("solid", fgColor="FFFFEB9C")
RED    = PatternFill("solid", fgColor="FFFFC7CE")
MISSING = "[MISSING]"


def _price_history_str(history: list[dict]) -> str:
    if not history or len(history) <= 1:
        return MISSING
    return "; ".join(f"{h.get('date', '?')}→${int(h.get('price', 0)):,}" for h in history)


def write_excel(listings: list[ScoredListing], output_path: str) -> None:
    sorted_listings = sorted(listings, key=lambda sl: sl.score, reverse=True)
    wb = Workbook()
    ws = wb.active

    for col, header in enumerate(HEADERS, start=1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(HEADERS))}1"

    for row_idx, sl in enumerate(sorted_listings, start=2):
        l = sl.listing
        row = [
            sl.score,
            sl.reasons_str,
            l.address or MISSING,
            l.property_type or MISSING,
            l.days_on_market,
            f"${l.current_price:,}" if l.current_price else MISSING,
            f"${l.original_price:,}" if l.original_price else MISSING,
            _price_history_str(l.price_history),
            l.agent_name or MISSING,
            l.brokerage or MISSING,
            l.agent_email or MISSING,
            l.agent_phone or MISSING,
            l.county or MISSING,
        ]
        for col_idx, value in enumerate(row, start=1):
            ws.cell(row=row_idx, column=col_idx, value=value)

        score_cell = ws.cell(row=row_idx, column=1)
        score_cell.fill = GREEN if sl.score >= 60 else (YELLOW if sl.score >= 30 else RED)

    col_widths = [10, 45, 40, 18, 8, 14, 14, 55, 25, 30, 28, 18, 14]
    for i, width in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width

    wb.save(output_path)
```

- [ ] **Step 4: Run tests — verify all pass**

```bash
pytest tests/test_exporter.py -v
```

Expected: All 9 tests pass.

- [ ] **Step 5: Commit**

```bash
git add redfin_scout/exporter.py tests/test_exporter.py
git commit -m "feat: Excel exporter — 13 columns, color-coded scores, frozen header, auto-filter"
```

---

### Task 8: Orchestrator

**Files:**
- Create: `redfin_scout/main.py`

- [ ] **Step 1: Write `main.py`**

```python
import logging
import os
import time
from datetime import date
from dotenv import load_dotenv
from redfin_scout.redfin import RedfinClient
from redfin_scout.hubspot import HubSpotClient
from redfin_scout.scorer import score_listing
from redfin_scout.exporter import write_excel
from redfin_scout.models import ScoredListing

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

COUNTIES = {
    "King": 1346,
    "Snohomish": 1360,
    "Pierce": 1355,
    "Skagit": 1358,
    "Kitsap": 1347,
    "Kittitas": 1348,
    "Chelan": 1338,
}

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")


def main() -> None:
    hubspot_key = os.environ.get("HUBSPOT_API_KEY")
    if not hubspot_key:
        raise RuntimeError("HUBSPOT_API_KEY not set — copy .env.example to .env and add your token")

    redfin = RedfinClient()
    hubspot = HubSpotClient(hubspot_key)
    seen: dict[str, ScoredListing] = {}  # mls_id → ScoredListing, for deduplication

    county_names = list(COUNTIES.keys())
    for i, (county, region_id) in enumerate(COUNTIES.items()):
        logger.info("Fetching %s County (region_id=%d)...", county, region_id)
        try:
            listings = redfin.fetch_county_listings(region_id=region_id, county=county)
            logger.info("  %d listings with 30+ DOM", len(listings))
        except Exception as exc:
            logger.error("Failed to fetch %s County: %s — skipping", county, exc)
            listings = []

        for listing in listings:
            if listing.mls_id in seen:
                continue
            agent_in_crm = hubspot.is_agent_in_crm(listing.agent_email, listing.agent_phone)
            score, reasons = score_listing(listing, agent_in_crm=agent_in_crm)
            seen[listing.mls_id] = ScoredListing(listing=listing, score=score, reasons=reasons)

        if i < len(county_names) - 1:
            time.sleep(1)

    logger.info("Total unique listings: %d", len(seen))
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, f"redfin_scout_{date.today()}.xlsx")
    write_excel(list(seen.values()), output_path)
    logger.info("Done — written to %s", output_path)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify clean import**

```bash
python -c "from redfin_scout.main import main; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add redfin_scout/main.py
git commit -m "feat: orchestrator — 7-county loop, deduplication, scoring pipeline, Excel export"
```

---

### Task 9: Shell Wrapper and launchd Plist

**Files:**
- Create: `run.sh`
- Create: `com.ccm.redfin-scout.plist`

- [ ] **Step 1: Write `run.sh`**

```bash
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
source .venv/bin/activate
python -m redfin_scout.main
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x run.sh
```

- [ ] **Step 3: Write the launchd plist**

`com.ccm.redfin-scout.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.ccm.redfin-scout</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/Users/ricecracker/Developer/ccm-stale-listings/run.sh</string>
  </array>

  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key>
    <integer>1</integer>
    <key>Hour</key>
    <integer>7</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>

  <key>StandardOutPath</key>
  <string>/Users/ricecracker/Library/Logs/redfin-scout.log</string>

  <key>StandardErrorPath</key>
  <string>/Users/ricecracker/Library/Logs/redfin-scout.log</string>

  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
```

- [ ] **Step 4: Commit**

```bash
git add run.sh com.ccm.redfin-scout.plist
git commit -m "feat: run.sh + launchd plist — Monday 7 AM weekly schedule"
```

---

### Task 10: End-to-End Smoke Test

- [ ] **Step 1: Run the full test suite**

```bash
pytest tests/ -v
```

Expected: All tests pass. Count should be 15 (scorer) + 6 (hubspot) + 8 (redfin) + 9 (exporter) = 38 tests.

- [ ] **Step 2: Add your HubSpot key to .env**

```bash
cp .env.example .env
# Open .env and set HUBSPOT_API_KEY=<your private app token>
```

- [ ] **Step 3: Run against King County only**

Temporarily set in `main.py`:

```python
COUNTIES = {"King": 1346}
```

Run:

```bash
python -m redfin_scout.main
```

Watch logs. Expected output:
```
... INFO redfin_scout.main — Fetching King County (region_id=1346)...
... INFO redfin_scout.main —   N listings with 30+ DOM
... INFO redfin_scout.main — Total unique listings: N
... INFO redfin_scout.main — Done — written to output/redfin_scout_2026-05-28.xlsx
```

- [ ] **Step 4: Open and inspect the Excel file**

```bash
open output/redfin_scout_$(date +%Y-%m-%d).xlsx
```

Verify:
- Addresses look like real WA properties (not empty/garbled)
- Priority Score column has green/yellow/red color coding
- Rows sorted highest score first
- `[MISSING]` appears only where data was genuinely unavailable — not for every row

- [ ] **Step 5: If most fields show `[MISSING]` — fix field paths**

Re-run the discovery script from Task 5 (`scripts/discover_redfin_api.py`) with `num_homes=1`. Compare the actual JSON field names against what's in `redfin.py`'s `_parse_home`. Update any mismatched paths. Re-run smoke test.

- [ ] **Step 6: Restore all 7 counties**

```python
COUNTIES = {
    "King": 1346,
    "Snohomish": 1360,
    "Pierce": 1355,
    "Skagit": 1358,
    "Kitsap": 1347,
    "Kittitas": 1348,
    "Chelan": 1338,
}
```

- [ ] **Step 7: Register the launchd agent**

```bash
cp com.ccm.redfin-scout.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.ccm.redfin-scout.plist
launchctl list | grep redfin
```

Expected: `com.ccm.redfin-scout` appears with `-` in the PID column (scheduled, not currently running).

- [ ] **Step 8: Final commit and push**

```bash
git add -A
git commit -m "chore: smoke test complete — all counties verified, launchd registered"
git push origin main
```
