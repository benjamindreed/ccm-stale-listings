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
# al=1, region_id=118, region_type=5, uipt=1,2,3,5, status=9,
# num_homes=50, start=0, v=8
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
