"""
Integration tests for the SnapTrade MCP server.

Requires real credentials set as environment variables:
  SNAPTRADE_CLIENT_ID
  SNAPTRADE_CONSUMER_KEY
  SNAPTRADE_USER_ID
  SNAPTRADE_USER_SECRET

Use a paper trading account (e.g. Alpaca paper) — never real credentials.
These tests are read-only and will not modify any account data.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import pytest

from snaptrade_mcp.server import (
    snaptrade_check_status,
    snaptrade_get_option_positions,
    snaptrade_get_option_strategy_quote,
    snaptrade_get_options_chain,
    snaptrade_list_accounts,
    snaptrade_list_brokerages,
    snaptrade_portfolio_summary,
    snaptrade_search_symbols,
    snaptrade_setup,
)

_REQUIRED_ENV_VARS = [
    "SNAPTRADE_CLIENT_ID",
    "SNAPTRADE_CONSUMER_KEY",
    "SNAPTRADE_USER_ID",
    "SNAPTRADE_USER_SECRET",
]


@pytest.fixture(autouse=True, scope="session")
def require_credentials():
    """Fail the test session if any required credential env vars are missing.

    Writes credentials to a temp file and patches CONFIG_PATH in server.py so
    tests never touch ~/.snaptrade/config.json — keeping test credentials
    isolated from the config used to run the live server.

    autouse=True means this fixture runs automatically for every test in this
    file without needing to be explicitly requested. scope="session" means it
    runs once at the start of the test session rather than before each test.
    """
    missing = [k for k in _REQUIRED_ENV_VARS if not os.environ.get(k)]
    if missing:
        pytest.fail(f"Missing required environment variables: {', '.join(missing)}")

    # Write credentials to a temp file — never touches ~/.snaptrade/config.json.
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump({
        "user_id": os.environ["SNAPTRADE_USER_ID"],
        "user_secret": os.environ["SNAPTRADE_USER_SECRET"],
    }, tmp)
    tmp.close()
    os.chmod(tmp.name, 0o600)

    # Pytest fixtures treat code before `yield` as setup and code after it as
    # teardown. Staying inside this `with` keeps CONFIG_PATH patched for the
    # entire test, then restores the original value when the test finishes.
    with patch("snaptrade_mcp.server.CONFIG_PATH", Path(tmp.name)):
        yield

    # Remove the temporary config file after the patch has been undone.
    os.unlink(tmp.name)


def test_check_status_returns_valid() -> None:
    result = json.loads(snaptrade_check_status())
    assert result["credentials"] == "valid"
    assert result["user"] == "configured"


def test_list_brokerages_returns_list() -> None:
    result = json.loads(snaptrade_list_brokerages())
    assert "brokerages" in result
    assert isinstance(result["brokerages"], list)
    assert result["count"] > 0


def test_get_accounts_returns_list() -> None:
    result = json.loads(snaptrade_list_accounts())
    assert "accounts" in result
    assert isinstance(result["accounts"], list)


def test_portfolio_summary_structure() -> None:
    result = json.loads(snaptrade_portfolio_summary())
    # Either returns a portfolio list or a no-accounts message
    assert "portfolio" in result or "message" in result


def test_setup_returns_status() -> None:
    """snaptrade_setup opens a browser locally and returns a status field."""
    result = json.loads(snaptrade_setup())
    assert "status" in result


def _first_account_id() -> str:
    accounts = json.loads(snaptrade_list_accounts()).get("accounts", [])
    if not accounts:
        pytest.skip("No connected brokerage accounts available.")
    acct_id = accounts[0].get("id") or accounts[0].get("brokerage_account_id")
    if not acct_id:
        pytest.skip("First account has no usable ID.")
    return acct_id


def test_get_option_positions_returns_valid() -> None:
    """Options holdings endpoint returns a list (empty is fine for paper accounts)."""
    acct_id = _first_account_id()
    result = json.loads(snaptrade_get_option_positions(account_id=acct_id))
    assert result["account_id"] == acct_id
    assert "option_positions" in result
    # Some brokerages return a list directly; others may return an error dict
    # if options are not supported. Accept either shape.
    assert isinstance(result["option_positions"], (list, dict))


def test_portfolio_summary_includes_option_positions_key() -> None:
    """portfolio_summary surfaces option_positions for each account."""
    result = json.loads(snaptrade_portfolio_summary())
    portfolio = result.get("portfolio")
    if not portfolio:
        pytest.skip("No accounts in portfolio summary.")
    for entry in portfolio:
        assert "option_positions" in entry


def test_get_options_chain_returns_valid() -> None:
    """options chain endpoint returns chain data for a known symbol, or errors cleanly."""
    acct_id = _first_account_id()

    search = json.loads(snaptrade_search_symbols(query="AAPL"))
    results = cast(list[dict[str, Any]], search.get("results") or [])
    if not results:
        pytest.skip("Symbol search returned no results for AAPL.")

    symbol_id: str | None = None
    for r in results:
        nested = cast(dict[str, Any], r.get("symbol") or {})
        symbol_id = r.get("id") or nested.get("id")
        if symbol_id:
            break
    if not symbol_id:
        pytest.skip("Could not find a usable symbol ID from search results.")

    try:
        result = json.loads(snaptrade_get_options_chain(account_id=acct_id, symbol=symbol_id))
    except Exception as e:
        pytest.skip(f"Brokerage does not expose options chain: {e}")

    assert result["account_id"] == acct_id
    assert result["symbol"] == symbol_id
    assert "chain" in result


def test_get_option_strategy_quote_returns_valid() -> None:
    """strategy quote endpoint returns Greeks + pricing, or skips if unsupported."""
    acct_id = _first_account_id()

    search = json.loads(snaptrade_search_symbols(query="AAPL"))
    results = cast(list[dict[str, Any]], search.get("results") or [])
    if not results:
        pytest.skip("Symbol search returned no results.")

    underlying_id: str | None = None
    for r in results:
        nested = cast(dict[str, Any], r.get("symbol") or {})
        underlying_id = r.get("id") or nested.get("id")
        if underlying_id:
            break
    if not underlying_id:
        pytest.skip("Could not resolve an underlying symbol ID.")

    try:
        chain = json.loads(snaptrade_get_options_chain(account_id=acct_id, symbol=underlying_id))
    except Exception as e:
        pytest.skip(f"Chain not available: {e}")

    # Walk the chain to find any callSymbolId we can use as a single leg.
    call_symbol_id: str | None = None

    def _walk(obj: Any) -> None:
        nonlocal call_symbol_id
        if call_symbol_id is not None:
            return
        if isinstance(obj, dict):
            d = cast(dict[str, Any], obj)
            if d.get("callSymbolId"):
                call_symbol_id = cast(str, d["callSymbolId"])
                return
            for v in d.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in cast(list[Any], obj):
                _walk(v)

    _walk(chain.get("chain"))
    if not call_symbol_id:
        pytest.skip("No callSymbolId found in options chain.")

    try:
        result = json.loads(snaptrade_get_option_strategy_quote(
            account_id=acct_id,
            legs=[{"action": "BUY", "option_symbol_id": str(call_symbol_id), "quantity": 1}],
            strategy_type="SINGLE",
            underlying_symbol_id=underlying_id,
        ))
    except Exception as e:
        pytest.skip(f"Strategy quote endpoint not supported: {e}")

    assert "strategy" in result
    assert "quote" in result or "error" in result
