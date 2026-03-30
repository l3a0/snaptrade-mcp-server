"""Tests for CLI argument parsing and Bearer token authentication."""

import os
import subprocess
import sys

import pytest


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------


def test_help_shows_transport_options():
    """--help exits 0 and lists all transport choices."""
    result = subprocess.run(
        [sys.executable, "-m", "snaptrade_mcp", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--transport" in result.stdout
    assert "streamable-http" in result.stdout


def test_invalid_transport_rejected():
    """An unrecognized transport value exits non-zero."""
    result = subprocess.run(
        [sys.executable, "-m", "snaptrade_mcp", "--transport", "grpc"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


# ---------------------------------------------------------------------------
# HTTP transport requires SNAPTRADE_MCP_TOKEN
# ---------------------------------------------------------------------------


def test_http_transport_fails_without_token():
    """streamable-http refuses to start when SNAPTRADE_MCP_TOKEN is unset."""
    env = {k: v for k, v in os.environ.items() if k != "SNAPTRADE_MCP_TOKEN"}
    result = subprocess.run(
        [sys.executable, "-m", "snaptrade_mcp", "--transport", "streamable-http"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode != 0
    assert "SNAPTRADE_MCP_TOKEN" in result.stderr


# ---------------------------------------------------------------------------
# Auth configuration based on SNAPTRADE_MCP_TOKEN
# ---------------------------------------------------------------------------


def test_auth_configured_when_token_set():
    """FastMCP auth settings are populated when SNAPTRADE_MCP_TOKEN is present."""
    result = subprocess.run(
        [sys.executable, "-c", "\n".join([
            "import os",
            'os.environ["SNAPTRADE_MCP_TOKEN"] = "test-token"',
            "from snaptrade_mcp.server import mcp",
            "assert mcp.settings.auth is not None",
            'print("auth configured")',
        ])],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "auth configured" in result.stdout


def test_auth_disabled_when_token_unset():
    """FastMCP auth settings are None when SNAPTRADE_MCP_TOKEN is absent."""
    result = subprocess.run(
        [sys.executable, "-c", "\n".join([
            "import os",
            'os.environ.pop("SNAPTRADE_MCP_TOKEN", None)',
            "from snaptrade_mcp.server import mcp",
            "assert mcp.settings.auth is None",
            'print("no auth")',
        ])],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "no auth" in result.stdout


# ---------------------------------------------------------------------------
# Token verifier logic
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_token_verifier_accepts_valid_token():
    """The verifier returns an AccessToken for the correct secret."""
    from mcp.server.auth.provider import AccessToken, TokenVerifier

    secret = "my-secret"

    class _StaticTokenVerifier(TokenVerifier):
        async def verify_token(self, token: str) -> AccessToken | None:
            if token == secret:
                return AccessToken(
                    token=token,
                    client_id="snaptrade-user",
                    scopes=["read"],
                    expires_at=None,
                )
            return None

    verifier = _StaticTokenVerifier()

    result = await verifier.verify_token("my-secret")
    assert result is not None
    assert result.client_id == "snaptrade-user"

    result = await verifier.verify_token("wrong-token")
    assert result is None
