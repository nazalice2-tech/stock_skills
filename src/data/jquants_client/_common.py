"""J-Quants API shared helpers: auth, token cache, HTTP utilities."""

import os
import sys
import time
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

_BASE_URL = "https://api.jquants.com/v1"

# ID token cache: renewed from refresh token (~24h TTL)
_id_token_cache: dict = {"token": None, "expires_at": 0.0}


def is_available() -> bool:
    """Return True if JQUANTS_REFRESH_TOKEN is set."""
    return bool(os.environ.get("JQUANTS_REFRESH_TOKEN"))


def clear_id_token_cache() -> None:
    """Invalidate the cached ID token (useful for tests)."""
    _id_token_cache["token"] = None
    _id_token_cache["expires_at"] = 0.0


def _get_id_token() -> Optional[str]:
    """Return a valid ID token, refreshing from the stored refresh token if needed."""
    refresh_token = os.environ.get("JQUANTS_REFRESH_TOKEN")
    if not refresh_token:
        return None

    now = time.time()
    if _id_token_cache["token"] and now < _id_token_cache["expires_at"]:
        return _id_token_cache["token"]

    try:
        resp = requests.post(
            f"{_BASE_URL}/token/auth_refresh",
            params={"refreshtoken": refresh_token},
            timeout=10,
        )
        if resp.status_code == 200:
            id_token = resp.json().get("idToken")
            if id_token:
                _id_token_cache["token"] = id_token
                # ID token TTL is 24h; cache for 23h to be safe
                _id_token_cache["expires_at"] = now + 23 * 3600
                return id_token
        print(
            f"⚠️  J-Quants トークン更新失敗 (HTTP {resp.status_code})\n"
            "    JQUANTS_REFRESH_TOKEN が正しいか確認してください",
            file=sys.stderr,
        )
    except Exception as e:
        print(
            f"⚠️  J-Quants への接続に失敗しました: {e}\n"
            "    → 信用比率データなしで実行します",
            file=sys.stderr,
        )
    return None


def _symbol_to_code(symbol: str) -> Optional[str]:
    """Convert yfinance symbol (e.g. '7203.T') to J-Quants 5-digit code ('72030').

    J-Quants uses 5-character codes where the 5th digit is typically '0'
    for common shares (e.g. 7203 -> 72030).
    Non-JP symbols (no .T/.S suffix) return None.
    """
    upper = symbol.upper()
    if not (upper.endswith(".T") or upper.endswith(".S")):
        return None
    code = upper.replace(".T", "").replace(".S", "").strip()
    if not code.isdigit():
        return None
    if len(code) == 4:
        return code + "0"
    if len(code) == 5:
        return code
    return None
