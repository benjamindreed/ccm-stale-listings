# Redfin Scout — Design Spec
**Date:** 2026-05-28
**Repo:** CCM
**Status:** Approved

## Overview

A weekly automated pipeline that queries Redfin's internal JSON API for stale residential real estate listings across 7 Washington state counties, scores each listing for acquisition opportunity, cross-references listing agents against HubSpot CRM, and writes results to a timestamped Excel file on iCloud Drive.

Runs every Monday at 7:00 AM via macOS launchd. No cloud infrastructure required.

---

## Project Structure

```
CCM/
├── redfin_scout/
│   ├── redfin.py       # Redfin API client — fetches & paginates listings per county
│   ├── hubspot.py      # HubSpot client — checks if agent is a known CRM contact
│   ├── scorer.py       # Scoring engine — pure function, listing → score + reason string
│   ├── exporter.py     # Excel writer — openpyxl, one row per listing
│   └── main.py         # Orchestrator — runs the full pipeline end-to-end
├── output/             # Weekly .xlsx files (gitignored, iCloud-synced)
├── .env                # HUBSPOT_API_KEY (gitignored)
├── requirements.txt
├── run.sh              # Shell wrapper: activates venv, calls main.py
└── com.ccm.redfin-scout.plist  # launchd agent config
```

---

## Data Flow

1. `main.py` iterates over all 7 counties
2. For each county, `redfin.py` hits Redfin's internal GIS search API with active/30+ DOM/property-type filters, paginating until all results are collected
3. Each listing's agent is looked up via Redfin's agent profile endpoint (cached per unique agent ID)
4. `hubspot.py` checks HubSpot Contacts Search API for each agent by email then phone (cached per run)
5. `scorer.py` applies all scoring rules and builds the opportunity reason string
6. All listings across all counties are deduplicated by MLS ID, sorted by score descending
7. `exporter.py` writes `output/redfin_scout_YYYY-MM-DD.xlsx`

---

## Redfin API Access

**Base endpoint:** `https://www.redfin.com/stingray/api/gis`

Requests use a browser-like `User-Agent` header. 1-second delay between county requests to avoid rate limiting.

**County → Redfin Region ID mapping:**

| County | Region ID |
|---|---|
| King | 1346 |
| Snohomish | 1360 |
| Pierce | 1355 |
| Skagit | 1358 |
| Kitsap | 1347 |
| Kittitas | 1348 |
| Chelan | 1338 |

> **Note:** Region IDs must be verified against Redfin's live API during implementation. The implementation step should confirm each ID returns expected county-level results before the first production run.

**Key query parameters:**
- `region_id` + `region_type=5` (county-level)
- `sf=1,2,3,5` — Single Family, Condo, Townhouse, Multi-family
- `status=1` — active listings only
- `dom=30` — 30+ days on market minimum
- `num_homes=350` per page, paginated via `start` offset

**Agent details:** List API returns agent name + brokerage. Email/phone fetched from `/stingray/api/user/agent/{agentId}`, cached in-memory per unique agent ID to minimize requests.

**Financeable filter:** Listings are excluded if their remarks contain keywords: `cash only`, `as-is`, `no FHA`, `uninhabitable`. Listings with no price (auction) are also excluded. Listings that pass keyword exclusion are considered financeable. The `-50` distressed penalty applies to any listing that contains distressed keywords in the detail payload but wasn't caught at the filter stage.

---

## HubSpot Integration

**Endpoint:** `POST /crm/v3/objects/contacts/search`

Lookup order: email first, phone if no email match. A contact hit means the agent is already in the relationship database — the `+10` new-agent bonus is not applied.

Auth: private app token stored in `.env` as `HUBSPOT_API_KEY`.

Results cached by `(email, phone)` pair for the duration of the run.

---

## Scoring Engine

`score_listing(listing, agent_in_crm: bool) → (score: int, reasons: list[str])`

| Rule | Points | Reason String |
|---|---|---|
| DOM ≥ 45 | +25 | `"45+ days on market"` |
| DOM ≥ 60 | +20 (stacks with above, +45 total at 60+) | `"60+ days on market"` |
| Any price reduction detected | +15 | `"Price reduced"` |
| Original price 5%+ above current | +10 | `"Price cut 5%+"` |
| Vacant/staged/investor-owned (keyword match) | +10 | `"Vacant/staged/investor-owned"` |
| Agent not in HubSpot CRM | +10 | `"New agent relationship"` |
| FHA/VA/conventional friendly (keyword match) | +5 | `"FHA/VA/conv eligible"` |
| Distressed/cash-only/unfinanceable (keyword match) | -50 | `"⚠ Distressed/unfinanceable"` |

**Notes:**
- DOM 45–59: +25. DOM 60+: +25 + +20 = +45 total for DOM alone
- Score is clamped to a minimum of 0
- Maximum possible score is 135 (all positive rules, no negatives)
- Missing fields: written as `[MISSING]` in output, never left blank

---

## Excel Output

**File:** `output/redfin_scout_YYYY-MM-DD.xlsx`
One file per run, never overwritten. Sheet named `Redfin Scout YYYY-MM-DD`.

**Column order:**

| # | Column | Format |
|---|---|---|
| 1 | Priority Score | Integer; green ≥60, yellow 30–59, red <30 |
| 2 | Opportunity Reasons | Pipe-delimited string |
| 3 | Property Address | Text |
| 4 | Property Type | Text |
| 5 | Days on Market | Integer |
| 6 | Current Price | Currency |
| 7 | Original Price | Currency or `[MISSING]` |
| 8 | Price Reduction History | Semicolon-delimited `date→price` pairs, or `[MISSING]` |
| 9 | Listing Agent | Text |
| 10 | Brokerage | Text |
| 11 | Agent Email | Text or `[MISSING]` |
| 12 | Agent Phone | Text or `[MISSING]` |
| 13 | County | Text |

Header row frozen. Auto-filter enabled on all columns.

---

## Scheduling

**Mechanism:** macOS `launchd` via a plist at `~/Library/LaunchAgents/com.ccm.redfin-scout.plist`

**Schedule:** Every Monday at 7:00 AM (`StartCalendarInterval`)

**Catch-up behavior:** launchd fires the job as soon as the Mac wakes if it was asleep at the scheduled time.

**Logging:** stdout/stderr → `~/Library/Logs/redfin-scout.log`

**Setup (one-time):**
```bash
launchctl load ~/Library/LaunchAgents/com.ccm.redfin-scout.plist
```

---

## Error Handling

- If Redfin returns a non-200 or rate-limit response, the county is retried up to 3 times with exponential backoff (2s, 4s, 8s). On final failure, the county is skipped and logged.
- If HubSpot is unreachable, agent is treated as not-in-CRM (optimistic — avoids blocking the run) and a warning is logged.
- If the output directory doesn't exist, it's created at runtime.
- Any unhandled exception is logged with full traceback to the log file; the process exits with code 1 so launchd can detect failure.

---

## Dependencies

```
requests
openpyxl
python-dotenv
```

Python 3.11+. No external frameworks needed.
