"""Tests for jquants_client package."""

from unittest.mock import MagicMock, patch

import pytest

from src.data.jquants_client._common import _symbol_to_code, is_available
from src.data.jquants_client.margin import EMPTY_MARGIN, _as_float, get_margin_ratio
from src.core.screening.contrarian import compute_margin_signal


# ---------------------------------------------------------------------------
# _symbol_to_code
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("symbol,expected", [
    ("7203.T", "72030"),
    ("9984.T", "99840"),
    ("6758.T", "67580"),
    ("1234.T", "12340"),
    ("12345.T", "12345"),
    ("AAPL", None),        # non-JP symbol
    ("7203.S", "72030"),   # .S suffix
    ("ABCD.T", None),      # non-numeric
])
def test_symbol_to_code(symbol, expected):
    assert _symbol_to_code(symbol) == expected


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------

def test_is_available_false(monkeypatch):
    monkeypatch.delenv("JQUANTS_REFRESH_TOKEN", raising=False)
    assert is_available() is False


def test_is_available_true(monkeypatch):
    monkeypatch.setenv("JQUANTS_REFRESH_TOKEN", "dummy_token")
    assert is_available() is True


# ---------------------------------------------------------------------------
# get_margin_ratio — no token
# ---------------------------------------------------------------------------

def test_get_margin_ratio_no_token(monkeypatch):
    monkeypatch.delenv("JQUANTS_REFRESH_TOKEN", raising=False)
    result = get_margin_ratio("7203.T")
    assert result == EMPTY_MARGIN


def test_get_margin_ratio_non_jp(monkeypatch):
    monkeypatch.setenv("JQUANTS_REFRESH_TOKEN", "dummy")
    result = get_margin_ratio("AAPL")
    assert result == EMPTY_MARGIN


# ---------------------------------------------------------------------------
# get_margin_ratio — mocked HTTP
# ---------------------------------------------------------------------------

def _make_mock_response(status_code: int, json_data: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    return resp


@pytest.fixture
def token_env(monkeypatch):
    monkeypatch.setenv("JQUANTS_REFRESH_TOKEN", "dummy_refresh")


def test_get_margin_ratio_success(token_env):
    id_resp = _make_mock_response(200, {"idToken": "test_id_token"})
    margin_resp = _make_mock_response(200, {
        "weekly_margin_interest": [
            {"Date": "2026-01-10", "Code": "72030", "MarginBuy": 2000.0, "MarginSell": 1000.0},
            {"Date": "2026-01-03", "Code": "72030", "MarginBuy": 1800.0, "MarginSell": 900.0},
        ]
    })

    with patch("src.data.jquants_client._common.requests.post", return_value=id_resp), \
         patch("src.data.jquants_client.margin.requests.get", return_value=margin_resp):
        result = get_margin_ratio("7203.T")

    assert result["margin_buy"] == 2000.0
    assert result["margin_sell"] == 1000.0
    assert result["margin_ratio"] == pytest.approx(2.0)


def test_get_margin_ratio_zero_sell(token_env):
    id_resp = _make_mock_response(200, {"idToken": "test_id_token"})
    margin_resp = _make_mock_response(200, {
        "weekly_margin_interest": [
            {"Date": "2026-01-10", "Code": "72030", "MarginBuy": 500.0, "MarginSell": 0.0},
        ]
    })

    with patch("src.data.jquants_client._common.requests.post", return_value=id_resp), \
         patch("src.data.jquants_client.margin.requests.get", return_value=margin_resp):
        result = get_margin_ratio("7203.T")

    assert result["margin_ratio"] is None  # division by zero avoided


def test_get_margin_ratio_empty_response(token_env):
    id_resp = _make_mock_response(200, {"idToken": "test_id_token"})
    margin_resp = _make_mock_response(200, {"weekly_margin_interest": []})

    with patch("src.data.jquants_client._common.requests.post", return_value=id_resp), \
         patch("src.data.jquants_client.margin.requests.get", return_value=margin_resp):
        result = get_margin_ratio("7203.T")

    assert result == EMPTY_MARGIN


def test_get_margin_ratio_api_error(token_env):
    id_resp = _make_mock_response(200, {"idToken": "test_id_token"})
    margin_resp = _make_mock_response(403, {})

    with patch("src.data.jquants_client._common.requests.post", return_value=id_resp), \
         patch("src.data.jquants_client.margin.requests.get", return_value=margin_resp):
        result = get_margin_ratio("7203.T")

    assert result == EMPTY_MARGIN


def test_get_margin_ratio_network_error(token_env):
    id_resp = _make_mock_response(200, {"idToken": "test_id_token"})

    with patch("src.data.jquants_client._common.requests.post", return_value=id_resp), \
         patch("src.data.jquants_client.margin.requests.get", side_effect=Exception("timeout")):
        result = get_margin_ratio("7203.T")

    assert result == EMPTY_MARGIN


def test_token_refresh_failure(token_env):
    id_resp = _make_mock_response(401, {})

    with patch("src.data.jquants_client._common.requests.post", return_value=id_resp):
        result = get_margin_ratio("7203.T")

    assert result == EMPTY_MARGIN


# ---------------------------------------------------------------------------
# _as_float
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    (1000.0, 1000.0),
    ("500", 500.0),
    (None, None),
    ("abc", None),
])
def test_as_float(value, expected):
    assert _as_float(value) == expected


# ---------------------------------------------------------------------------
# compute_margin_signal (in contrarian.py)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("margin_ratio,expected_score", [
    (0.3, 10.0),   # strongly net-short
    (0.8, 7.0),    # net-short
    (1.5, 3.0),    # balanced
    (3.0, 0.0),    # crowded long
    (None, 0.0),   # no data
])
def test_compute_margin_signal(margin_ratio, expected_score):
    data = {"margin_ratio": margin_ratio, "margin_buy": 1000.0, "margin_sell": 500.0}
    result = compute_margin_signal(data)
    assert result["score"] == expected_score


def test_compute_margin_signal_empty_dict():
    result = compute_margin_signal({})
    assert result["score"] == 0.0
    assert result["margin_ratio"] is None
