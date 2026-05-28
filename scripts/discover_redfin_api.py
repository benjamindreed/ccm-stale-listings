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
    "region_id": 1346,   # King County — verify this is correct
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
