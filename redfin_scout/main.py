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
    "King": 118,
    "Snohomish": 2,
    "Pierce": 3096,
    "Skagit": 3098,
    "Kitsap": 3087,
    "Kittitas": 3088,
    "Chelan": 3074,
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
