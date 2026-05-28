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
        if not email and not phone:
            return False

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
