"""Focused unit tests for server-side behavior."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

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
