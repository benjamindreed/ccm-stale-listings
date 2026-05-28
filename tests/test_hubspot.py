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
    assert mock_post.call_count == 2


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
