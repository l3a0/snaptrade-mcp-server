"""Tests for CLI argument parsing and OAuth authentication."""

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
# HTTP transport requires OAuth credentials
# ---------------------------------------------------------------------------


def test_http_transport_fails_without_oauth_credentials():
    """streamable-http refuses to start when OAuth env vars are unset."""
    env = {
        k: v for k, v in os.environ.items()
        if k not in ("SNAPTRADE_OAUTH_CLIENT_ID", "SNAPTRADE_OAUTH_CLIENT_SECRET")
    }
    result = subprocess.run(
        [sys.executable, "-m", "snaptrade_mcp", "--transport", "streamable-http"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode != 0
    assert "SNAPTRADE_OAUTH_CLIENT_ID" in result.stderr


# ---------------------------------------------------------------------------
# Auth configuration based on OAuth env vars
# ---------------------------------------------------------------------------


def test_auth_configured_when_oauth_credentials_set():
    """FastMCP auth settings are populated when OAuth env vars are present."""
    result = subprocess.run(
        [sys.executable, "-c", "\n".join([
            "import os",
            'os.environ["SNAPTRADE_OAUTH_CLIENT_ID"] = "test-client"',
            'os.environ["SNAPTRADE_OAUTH_CLIENT_SECRET"] = "test-secret"',
            "from snaptrade_mcp.server import mcp",
            "assert mcp.settings.auth is not None",
            'print("auth configured")',
        ])],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "auth configured" in result.stdout


def test_auth_disabled_when_oauth_credentials_unset():
    """FastMCP auth settings are None when OAuth env vars are absent."""
    result = subprocess.run(
        [sys.executable, "-c", "\n".join([
            "import os",
            'os.environ.pop("SNAPTRADE_OAUTH_CLIENT_ID", None)',
            'os.environ.pop("SNAPTRADE_OAUTH_CLIENT_SECRET", None)',
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
# HTTP transport requires SNAPTRADE_OAUTH_REDIRECT_URI
# ---------------------------------------------------------------------------


def test_http_transport_fails_without_redirect_uri():
    """streamable-http refuses to start when SNAPTRADE_OAUTH_REDIRECT_URI is unset."""
    env = {k: v for k, v in os.environ.items() if k != "SNAPTRADE_OAUTH_REDIRECT_URI"}
    env["SNAPTRADE_OAUTH_CLIENT_ID"] = "test-client"
    env["SNAPTRADE_OAUTH_CLIENT_SECRET"] = "test-secret"
    result = subprocess.run(
        [sys.executable, "-m", "snaptrade_mcp", "--transport", "streamable-http"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode != 0
    assert "SNAPTRADE_OAUTH_REDIRECT_URI" in result.stderr


# ---------------------------------------------------------------------------
# Public URL is reflected in OAuth metadata
# ---------------------------------------------------------------------------


def test_public_url_sets_issuer():
    """SNAPTRADE_PUBLIC_URL is reflected in mcp.settings.auth.issuer_url."""
    result = subprocess.run(
        [sys.executable, "-c", "\n".join([
            "import os",
            'os.environ["SNAPTRADE_OAUTH_CLIENT_ID"] = "test-client"',
            'os.environ["SNAPTRADE_OAUTH_CLIENT_SECRET"] = "test-secret"',
            'os.environ["SNAPTRADE_OAUTH_REDIRECT_URI"] = "https://example.com/cb"',
            'os.environ["SNAPTRADE_PUBLIC_URL"] = "https://my-tunnel.ngrok-free.app"',
            "from snaptrade_mcp.server import mcp",
            "print(str(mcp.settings.auth.issuer_url))",
        ])],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "my-tunnel.ngrok-free.app" in result.stdout


# ---------------------------------------------------------------------------
# OAuth provider logic
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_oauth_provider_accepts_valid_client():
    """SimpleOAuthProvider returns the pre-registered client for the correct client_id."""
    from snaptrade_mcp.oauth_provider import SimpleOAuthProvider

    provider = SimpleOAuthProvider(client_id="test-client", client_secret="test-secret", redirect_uri="https://example.com/cb")

    client = await provider.get_client("test-client")
    assert client is not None
    assert client.client_id == "test-client"

    missing = await provider.get_client("unknown")
    assert missing is None


@pytest.mark.anyio
async def test_oauth_provider_full_auth_code_flow():
    """Authorization code issued by authorize() can be exchanged for a token."""
    from pydantic import AnyUrl

    from snaptrade_mcp.oauth_provider import SimpleOAuthProvider

    provider = SimpleOAuthProvider(client_id="test-client", client_secret="test-secret", redirect_uri="https://chatgpt.com/callback")
    client = await provider.get_client("test-client")
    assert client is not None

    from mcp.server.auth.provider import AuthorizationParams

    params = AuthorizationParams(
        state="abc",
        scopes=["read"],
        code_challenge="challenge",
        redirect_uri=AnyUrl("https://chatgpt.com/callback"),
        redirect_uri_provided_explicitly=True,
    )

    redirect_url = await provider.authorize(client, params)
    assert "code=" in redirect_url
    assert "state=abc" in redirect_url

    code = redirect_url.split("code=")[1].split("&")[0]
    auth_code = await provider.load_authorization_code(client, code)
    assert auth_code is not None

    token = await provider.exchange_authorization_code(client, auth_code)
    assert token.access_token
    assert token.token_type == "Bearer"
    assert token.refresh_token

    # Code is single-use
    assert await provider.load_authorization_code(client, code) is None

    # Access token is valid
    at = await provider.load_access_token(token.access_token)
    assert at is not None
    assert at.client_id == "test-client"


@pytest.mark.anyio
async def test_oauth_provider_redirect_uri_registered():
    """SimpleOAuthProvider registers exactly the provided redirect URI."""
    from snaptrade_mcp.oauth_provider import SimpleOAuthProvider

    provider = SimpleOAuthProvider("client", "secret", "https://chatgpt.com/connector/oauth/abc")
    client = await provider.get_client("client")
    assert client is not None
    assert client.redirect_uris is not None
    assert len(client.redirect_uris) == 1
    assert str(client.redirect_uris[0]) == "https://chatgpt.com/connector/oauth/abc"


@pytest.mark.anyio
async def test_oauth_provider_uses_client_secret_post():
    """SimpleOAuthProvider registers with client_secret_post auth method."""
    from snaptrade_mcp.oauth_provider import SimpleOAuthProvider

    provider = SimpleOAuthProvider("client", "secret", "https://example.com/cb")
    client = await provider.get_client("client")
    assert client is not None
    assert client.token_endpoint_auth_method == "client_secret_post"


@pytest.mark.anyio
async def test_oauth_provider_refresh_token_rotation():
    """Refresh produces new tokens; old access token is revoked; old refresh is consumed."""
    from pydantic import AnyUrl

    from mcp.server.auth.provider import AuthorizationParams

    from snaptrade_mcp.oauth_provider import SimpleOAuthProvider

    provider = SimpleOAuthProvider("client", "secret", "https://example.com/cb")
    client = await provider.get_client("client")
    assert client is not None

    params = AuthorizationParams(
        state="s",
        scopes=["read"],
        code_challenge="c",
        redirect_uri=AnyUrl("https://example.com/cb"),
        redirect_uri_provided_explicitly=True,
    )
    redirect = await provider.authorize(client, params)
    code = redirect.split("code=")[1].split("&")[0]
    auth_code = await provider.load_authorization_code(client, code)
    assert auth_code is not None
    token = await provider.exchange_authorization_code(client, auth_code)

    old_access = token.access_token
    old_refresh = token.refresh_token
    assert old_refresh is not None

    rt = await provider.load_refresh_token(client, old_refresh)
    assert rt is not None
    new_token = await provider.exchange_refresh_token(client, rt, [])

    assert new_token.access_token != old_access
    assert new_token.refresh_token != old_refresh

    # Old tokens are gone
    assert await provider.load_access_token(old_access) is None
    assert await provider.load_refresh_token(client, old_refresh) is None

    # New tokens are valid
    assert await provider.load_access_token(new_token.access_token) is not None
    assert new_token.refresh_token is not None
    assert await provider.load_refresh_token(client, new_token.refresh_token) is not None
