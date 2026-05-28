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
