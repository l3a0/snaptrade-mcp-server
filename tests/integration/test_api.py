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
from unittest.mock import patch

import pytest

from snaptrade_mcp.server import (
    snaptrade_check_status,
    snaptrade_list_accounts,
    snaptrade_list_brokerages,
    snaptrade_portfolio_summary,
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

    with patch("snaptrade_mcp.server.CONFIG_PATH", Path(tmp.name)):
        yield

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
