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
