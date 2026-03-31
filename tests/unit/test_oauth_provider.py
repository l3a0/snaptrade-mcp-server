"""Unit tests for SimpleOAuthProvider — edge cases and gaps not covered by test_cli.py."""

import time
from unittest.mock import patch

import pytest
from pydantic import AnyUrl

from mcp.server.auth.provider import AuthorizationParams
from mcp.server.auth.provider import AccessToken as ServerAccessToken
from snaptrade_mcp.oauth_provider import SimpleOAuthProvider


@pytest.fixture
def provider() -> SimpleOAuthProvider:
    return SimpleOAuthProvider(
        client_id="test-client",
        client_secret="test-secret",
        redirect_uri="https://example.com/cb",
    )


@pytest.fixture
def auth_params() -> AuthorizationParams:
    return AuthorizationParams(
        state="abc",
        scopes=["read"],
        code_challenge="challenge",
        redirect_uri=AnyUrl("https://example.com/cb"),
        redirect_uri_provided_explicitly=True,
    )


@pytest.fixture
def auth_params_no_state() -> AuthorizationParams:
    return AuthorizationParams(
        state=None,
        scopes=["read"],
        code_challenge="challenge",
        redirect_uri=AnyUrl("https://example.com/cb"),
        redirect_uri_provided_explicitly=True,
    )


# ---------------------------------------------------------------------------
# Client management
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_register_client_raises_not_implemented(provider: SimpleOAuthProvider) -> None:
    """Dynamic client registration is disabled and raises NotImplementedError."""
    from mcp.shared.auth import OAuthClientInformationFull

    dummy = OAuthClientInformationFull(
        client_id="new-client",
        redirect_uris=[AnyUrl("https://example.com/cb")],
    )
    with pytest.raises(NotImplementedError, match="not supported"):
        await provider.register_client(dummy)


@pytest.mark.anyio
async def test_get_client_returns_none_for_unknown_id(provider: SimpleOAuthProvider) -> None:
    """get_client returns None for a client_id that doesn't match."""
    result = await provider.get_client("unknown-id")
    assert result is None


# ---------------------------------------------------------------------------
# Authorization code edge cases
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_authorize_without_state_param(
    provider: SimpleOAuthProvider,
    auth_params_no_state: AuthorizationParams,
) -> None:
    """authorize() omits &state= from the redirect URL when state is None."""
    client = await provider.get_client("test-client")
    assert client is not None

    redirect_url = await provider.authorize(client, auth_params_no_state)
    assert "code=" in redirect_url
    assert "state=" not in redirect_url


@pytest.mark.anyio
async def test_auth_code_expires_after_5_minutes(
    provider: SimpleOAuthProvider,
    auth_params: AuthorizationParams,
) -> None:
    """load_authorization_code returns None after the 5-minute expiry."""
    client = await provider.get_client("test-client")
    assert client is not None

    redirect = await provider.authorize(client, auth_params)
    code = redirect.split("code=")[1].split("&")[0]

    # Code is valid now
    ac = await provider.load_authorization_code(client, code)
    assert ac is not None

    # Simulate time passing beyond the 5-minute expiry
    with patch("snaptrade_mcp.oauth_provider.time") as mock_time:
        mock_time.time.return_value = time.time() + 301
        ac_expired = await provider.load_authorization_code(client, code)
    assert ac_expired is None


@pytest.mark.anyio
async def test_auth_code_is_single_use(
    provider: SimpleOAuthProvider,
    auth_params: AuthorizationParams,
) -> None:
    """After exchange, the authorization code cannot be loaded again."""
    client = await provider.get_client("test-client")
    assert client is not None

    redirect = await provider.authorize(client, auth_params)
    code = redirect.split("code=")[1].split("&")[0]
    ac = await provider.load_authorization_code(client, code)
    assert ac is not None

    await provider.exchange_authorization_code(client, ac)

    # Code has been consumed
    assert await provider.load_authorization_code(client, code) is None


# ---------------------------------------------------------------------------
# Access token expiry and validation
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_access_token_expires_after_1_hour(
    provider: SimpleOAuthProvider,
    auth_params: AuthorizationParams,
) -> None:
    """load_access_token returns None after the 1-hour expiry."""
    client = await provider.get_client("test-client")
    assert client is not None

    redirect = await provider.authorize(client, auth_params)
    code = redirect.split("code=")[1].split("&")[0]
    ac = await provider.load_authorization_code(client, code)
    assert ac is not None
    token = await provider.exchange_authorization_code(client, ac)

    # Token is valid now
    at = await provider.load_access_token(token.access_token)
    assert at is not None

    # Simulate time passing beyond the 1-hour expiry
    with patch("snaptrade_mcp.oauth_provider.time") as mock_time:
        mock_time.time.return_value = time.time() + 3601
        at_expired = await provider.load_access_token(token.access_token)
    assert at_expired is None


@pytest.mark.anyio
async def test_access_token_rejected_when_no_expiry(
    provider: SimpleOAuthProvider,
) -> None:
    """Tokens with expires_at=None are rejected (treated as expired)."""
    # Manually insert a token with no expiry to test the guard
    provider._access_tokens["fake-token"] = ServerAccessToken(
        token="fake-token",
        client_id="test-client",
        scopes=["read"],
        expires_at=None,
    )
    result = await provider.load_access_token("fake-token")
    assert result is None


# ---------------------------------------------------------------------------
# Token revocation
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_revoke_access_token(
    provider: SimpleOAuthProvider,
    auth_params: AuthorizationParams,
) -> None:
    """revoke_token removes an access token from storage."""
    client = await provider.get_client("test-client")
    assert client is not None

    redirect = await provider.authorize(client, auth_params)
    code = redirect.split("code=")[1].split("&")[0]
    ac = await provider.load_authorization_code(client, code)
    assert ac is not None
    token = await provider.exchange_authorization_code(client, ac)

    at = await provider.load_access_token(token.access_token)
    assert at is not None

    await provider.revoke_token(at)
    assert await provider.load_access_token(token.access_token) is None


@pytest.mark.anyio
async def test_revoke_refresh_token(
    provider: SimpleOAuthProvider,
    auth_params: AuthorizationParams,
) -> None:
    """revoke_token removes a refresh token from storage."""
    client = await provider.get_client("test-client")
    assert client is not None

    redirect = await provider.authorize(client, auth_params)
    code = redirect.split("code=")[1].split("&")[0]
    ac = await provider.load_authorization_code(client, code)
    assert ac is not None
    token = await provider.exchange_authorization_code(client, ac)
    assert token.refresh_token is not None

    rt = await provider.load_refresh_token(client, token.refresh_token)
    assert rt is not None

    await provider.revoke_token(rt)
    assert await provider.load_refresh_token(client, token.refresh_token) is None
