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
