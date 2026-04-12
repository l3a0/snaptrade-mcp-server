"""Focused unit tests for server-side behavior."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

import snaptrade_mcp.server as server
from snaptrade_mcp.server import (
    snaptrade_get_option_positions,
    snaptrade_portfolio_summary,
    snaptrade_setup,
)


def test_snaptrade_setup_opens_browser_locally(tmp_path: Path) -> None:
    """snaptrade_setup opens the returned login URL in a local browser."""
    config_path = tmp_path / "config.json"

    fake_client = Mock()
    fake_client.authentication.register_snap_trade_user.return_value = {
        "userId": "user-123",
        "userSecret": "secret-456",
    }
    fake_client.authentication.login_snap_trade_user.return_value = {
        "redirectURI": "https://example.com/connect",
    }

    with patch("snaptrade_mcp.server.CONFIG_PATH", config_path):
        with patch("snaptrade_mcp.server._get_client", return_value=(fake_client, "app-id")):
            with patch("snaptrade_mcp.server.webbrowser.open") as open_browser:
                result = json.loads(snaptrade_setup())

    open_browser.assert_called_once_with("https://example.com/connect")
    assert result["status"] == "opened"


# ---------------------------------------------------------------------------
# _get_client error paths
# ---------------------------------------------------------------------------


def test_get_client_raises_on_missing_client_id() -> None:
    """_get_client raises ValueError when SNAPTRADE_CLIENT_ID is unset."""
    with patch.dict("os.environ", {"SNAPTRADE_CONSUMER_KEY": "key"}, clear=True):
        with pytest.raises(ValueError, match="SNAPTRADE_CLIENT_ID"):
            getattr(server, "_get_client")()


def test_get_client_raises_on_missing_consumer_key() -> None:
    """_get_client raises ValueError when SNAPTRADE_CONSUMER_KEY is unset."""
    with patch.dict("os.environ", {"SNAPTRADE_CLIENT_ID": "id"}, clear=True):
        with pytest.raises(ValueError, match="SNAPTRADE_CONSUMER_KEY"):
            getattr(server, "_get_client")()


# ---------------------------------------------------------------------------
# _get_user error paths
# ---------------------------------------------------------------------------


def test_get_user_raises_on_missing_config(tmp_path: Path) -> None:
    """_get_user raises ValueError when the config file doesn't exist."""
    missing = tmp_path / "nonexistent" / "config.json"
    with patch("snaptrade_mcp.server.CONFIG_PATH", missing):
        with pytest.raises(ValueError, match="No config found"):
            getattr(server, "_get_user")()


def test_get_user_raises_on_missing_user_id(tmp_path: Path) -> None:
    """_get_user raises ValueError when config has no user_id."""
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"user_secret": "secret"}))
    with patch("snaptrade_mcp.server.CONFIG_PATH", config):
        with pytest.raises(ValueError, match="user_id"):
            getattr(server, "_get_user")()


def test_get_user_raises_on_missing_user_secret(tmp_path: Path) -> None:
    """_get_user raises ValueError when config has no user_secret."""
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"user_id": "user"}))
    with patch("snaptrade_mcp.server.CONFIG_PATH", config):
        with pytest.raises(ValueError, match="user_secret"):
            getattr(server, "_get_user")()


def test_snaptrade_setup_returns_error_when_no_redirect_url(tmp_path: Path) -> None:
    """snaptrade_setup reports an error when SnapTrade returns no login URL."""
    config_path = tmp_path / "config.json"

    fake_client = Mock()
    fake_client.authentication.register_snap_trade_user.return_value = {
        "userId": "user-123",
        "userSecret": "secret-456",
    }
    fake_client.authentication.login_snap_trade_user.return_value = {}

    with patch("snaptrade_mcp.server.CONFIG_PATH", config_path):
        with patch("snaptrade_mcp.server._get_client", return_value=(fake_client, "app-id")):
            with patch("snaptrade_mcp.server.webbrowser.open") as open_browser:
                result = json.loads(snaptrade_setup())

    open_browser.assert_not_called()
    assert result["status"] == "error"


def test_snaptrade_setup_reuses_existing_config(tmp_path: Path) -> None:
    """snaptrade_setup reuses saved user credentials instead of re-registering."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "user_id": "existing-user",
        "user_secret": "existing-secret",
    }))

    fake_client = Mock()
    fake_client.authentication.login_snap_trade_user.return_value = {
        "loginRedirectURI": "https://example.com/connect",
    }

    with patch("snaptrade_mcp.server.CONFIG_PATH", config_path):
        with patch("snaptrade_mcp.server._get_client", return_value=(fake_client, "app-id")):
            with patch("snaptrade_mcp.server.webbrowser.open") as open_browser:
                result = json.loads(snaptrade_setup())

    fake_client.authentication.register_snap_trade_user.assert_not_called()
    fake_client.authentication.login_snap_trade_user.assert_called_once_with(
        user_id="existing-user",
        user_secret="existing-secret",
    )
    open_browser.assert_called_once_with("https://example.com/connect")
    assert result["status"] == "opened"


# ---------------------------------------------------------------------------
# Options tools
# ---------------------------------------------------------------------------


def _patch_creds(fake_client: Mock):
    """Patch _get_client and _get_user with a fake client and static creds."""
    return (
        patch("snaptrade_mcp.server._get_client", return_value=(fake_client, "app-id")),
        patch("snaptrade_mcp.server._get_user", return_value=("uid", "usecret")),
    )


def test_snaptrade_get_option_positions_calls_sdk() -> None:
    fake_client = Mock()
    fake_client.options.list_option_holdings.return_value = [
        {"symbol": {"option_symbol": {"ticker": "AAPL240119C00150000"}}, "units": 2},
    ]

    client_patch, user_patch = _patch_creds(fake_client)
    with client_patch, user_patch:
        result = json.loads(snaptrade_get_option_positions(account_id="acct-1"))

    fake_client.options.list_option_holdings.assert_called_once_with(
        user_id="uid", user_secret="usecret", account_id="acct-1",
    )
    assert result["account_id"] == "acct-1"
    assert isinstance(result["option_positions"], list)
    assert result["option_positions"][0]["units"] == 2


def test_portfolio_summary_includes_option_positions() -> None:
    fake_client = Mock()
    fake_client.account_information.list_user_accounts.return_value = [
        {"id": "acct-1", "name": "Paper", "institution_name": "Alpaca", "type": "margin"},
    ]
    fake_client.account_information.get_user_account_balance.return_value = {"cash": 1000}
    fake_client.account_information.get_user_account_positions.return_value = []
    fake_client.options.list_option_holdings.return_value = [
        {"symbol": {"option_symbol": {"ticker": "AAPL240119C00150000"}}, "units": 1},
    ]

    client_patch, user_patch = _patch_creds(fake_client)
    with client_patch, user_patch:
        result = json.loads(snaptrade_portfolio_summary())

    entry = result["portfolio"][0]
    assert "option_positions" in entry
    assert isinstance(entry["option_positions"], list)
    assert entry["option_positions"][0]["units"] == 1


def test_portfolio_summary_handles_options_error() -> None:
    fake_client = Mock()
    fake_client.account_information.list_user_accounts.return_value = [
        {"id": "acct-1", "name": "Paper", "institution_name": "Alpaca", "type": "margin"},
    ]
    fake_client.account_information.get_user_account_balance.return_value = {"cash": 1000}
    fake_client.account_information.get_user_account_positions.return_value = []
    fake_client.options.list_option_holdings.side_effect = RuntimeError("brokerage not supported")

    client_patch, user_patch = _patch_creds(fake_client)
    with client_patch, user_patch:
        result = json.loads(snaptrade_portfolio_summary())

    entry = result["portfolio"][0]
    assert "error" in entry["option_positions"]
    assert entry["balances"] == {"cash": 1000}
