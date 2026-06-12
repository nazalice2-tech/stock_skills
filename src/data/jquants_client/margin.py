"""J-Quants weekly margin interest data (信用残・信用倍率)."""

from typing import Optional

import requests

from src.data.jquants_client._common import (
    _BASE_URL,
    _get_id_token,
    _symbol_to_code,
    is_available,
)

EMPTY_MARGIN: dict = {
    "margin_buy": None,
    "margin_sell": None,
    "margin_ratio": None,
}


def get_margin_ratio(symbol: str) -> dict:
    """Fetch latest weekly margin interest data for a JP stock.

    Calls the J-Quants ``/markets/weekly_margin_interest`` endpoint.
    Requires ``JQUANTS_REFRESH_TOKEN`` env var (free plan may not include
    this endpoint; gracefully returns EMPTY_MARGIN on 403).

    Parameters
    ----------
    symbol : str
        yfinance ticker, e.g. ``'7203.T'``.

    Returns
    -------
    dict with keys:
        margin_buy  : float | None  — 信用買残 (融資残高)
        margin_sell : float | None  — 信用売残 (貸株残高)
        margin_ratio: float | None  — 信用倍率 = margin_buy / margin_sell
    """
    if not is_available():
        return EMPTY_MARGIN

    code = _symbol_to_code(symbol)
    if code is None:
        return EMPTY_MARGIN

    id_token = _get_id_token()
    if not id_token:
        return EMPTY_MARGIN

    try:
        resp = requests.get(
            f"{_BASE_URL}/markets/weekly_margin_interest",
            params={"code": code},
            headers={"Authorization": id_token},
            timeout=10,
        )
        if resp.status_code != 200:
            return EMPTY_MARGIN

        records = resp.json().get("weekly_margin_interest", [])
        if not records:
            return EMPTY_MARGIN

        # Take the most recent record
        latest = max(records, key=lambda r: r.get("Date", ""))

        margin_buy: Optional[float] = _as_float(latest.get("MarginBuy"))
        margin_sell: Optional[float] = _as_float(latest.get("MarginSell"))

        margin_ratio: Optional[float] = None
        if margin_buy is not None and margin_sell is not None and margin_sell > 0:
            margin_ratio = margin_buy / margin_sell

        return {
            "margin_buy": margin_buy,
            "margin_sell": margin_sell,
            "margin_ratio": margin_ratio,
        }

    except Exception:
        return EMPTY_MARGIN


def _as_float(value) -> Optional[float]:
    """Convert a value to float, returning None on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
