"""Focused unit tests for server-side behavior."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

import snaptrade_mcp.server as server
from snaptrade_mcp.server import snaptrade_setup


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
