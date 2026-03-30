"""
Simple in-memory OAuth 2.0 provider for single-client personal use.

Implements OAuthAuthorizationServerProvider from the MCP SDK. Designed for
connecting ChatGPT (or any OAuth client) to the SnapTrade MCP server without
a third-party identity provider.

Design decisions:
- Single pre-registered client: no dynamic client registration.
- Auto-approve: the /authorize endpoint immediately redirects with a code.
  No user login form is shown — this is a personal server you control.
- In-memory storage: tokens are lost on restart; clients re-auth automatically.
- PKCE: required by the MCP SDK's TokenHandler before exchange_authorization_code
  is called, so we store code_challenge and let the SDK validate it.
"""

import secrets
import time

from mcp.server.auth.provider import (
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
)
from mcp.server.auth.provider import AccessToken as ServerAccessToken
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken


class SimpleOAuthProvider(OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, ServerAccessToken]):
    """Single-client in-memory OAuth 2.0 authorization server.

    Usage:
        provider = SimpleOAuthProvider(
            client_id=os.environ["SNAPTRADE_OAUTH_CLIENT_ID"],
            client_secret=os.environ["SNAPTRADE_OAUTH_CLIENT_SECRET"],
        )

    Pass this to FastMCP via the auth_server_provider parameter. FastMCP will
    automatically expose /authorize, /token, /revoke, and
    /.well-known/oauth-authorization-server endpoints backed by this provider.
    """

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client = OAuthClientInformationFull(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uris=None,  # accept any redirect_uri (validated per-request by AuthorizationHandler)
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            token_endpoint_auth_method="client_secret_basic",
        )
        self._auth_codes: dict[str, AuthorizationCode] = {}
        self._access_tokens: dict[str, ServerAccessToken] = {}
        self._refresh_tokens: dict[str, RefreshToken] = {}

    # ------------------------------------------------------------------
    # Client management
    # ------------------------------------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._client if client_id == self._client.client_id else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        # Dynamic client registration is disabled. Clients must be pre-registered
        # via the SNAPTRADE_OAUTH_CLIENT_ID / SNAPTRADE_OAUTH_CLIENT_SECRET env vars.
        raise NotImplementedError("Dynamic client registration is not supported.")

    # ------------------------------------------------------------------
    # Authorization code flow
    # ------------------------------------------------------------------

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        """Auto-approve and redirect immediately with an authorization code.

        No user interaction is required — this server is personal and trusted.
        The generated code is single-use and expires in 5 minutes.
        """
        code = secrets.token_urlsafe(32)
        assert client.client_id is not None, "client_id must not be None"
        self._auth_codes[code] = AuthorizationCode(
            code=code,
            scopes=params.scopes or ["read"],
            expires_at=time.time() + 300,  # 5 minutes
            client_id=client.client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
        )
        redirect = str(params.redirect_uri) + f"?code={code}"
        if params.state:
            redirect += f"&state={params.state}"
        return redirect

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        ac = self._auth_codes.get(authorization_code)
        if ac and ac.expires_at > time.time():
            return ac
        return None

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        """Exchange a code for access + refresh tokens. Codes are single-use."""
        assert client.client_id is not None, "client_id must not be None"
        del self._auth_codes[authorization_code.code]

        access_token = secrets.token_urlsafe(32)
        refresh_token_str = secrets.token_urlsafe(32)
        expires_at = int(time.time()) + 3600  # 1 hour

        self._access_tokens[access_token] = ServerAccessToken(
            token=access_token,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=expires_at,
        )
        self._refresh_tokens[refresh_token_str] = RefreshToken(
            token=refresh_token_str,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
        )
        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=3600,
            scope=" ".join(authorization_code.scopes),
            refresh_token=refresh_token_str,
        )

    # ------------------------------------------------------------------
    # Refresh token flow
    # ------------------------------------------------------------------

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        return self._refresh_tokens.get(refresh_token)

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        """Rotate both tokens on refresh."""
        assert client.client_id is not None, "client_id must not be None"
        del self._refresh_tokens[refresh_token.token]

        # Revoke existing access tokens for this client
        stale = [k for k, v in self._access_tokens.items() if v.client_id == client.client_id]
        for k in stale:
            del self._access_tokens[k]

        access_token = secrets.token_urlsafe(32)
        new_refresh = secrets.token_urlsafe(32)
        expires_at = int(time.time()) + 3600
        use_scopes = scopes or refresh_token.scopes

        self._access_tokens[access_token] = ServerAccessToken(
            token=access_token,
            client_id=client.client_id,
            scopes=use_scopes,
            expires_at=expires_at,
        )
        self._refresh_tokens[new_refresh] = RefreshToken(
            token=new_refresh,
            client_id=client.client_id,
            scopes=use_scopes,
        )
        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=3600,
            scope=" ".join(use_scopes),
            refresh_token=new_refresh,
        )

    # ------------------------------------------------------------------
    # Token validation and revocation
    # ------------------------------------------------------------------

    async def load_access_token(self, token: str) -> ServerAccessToken | None:
        at = self._access_tokens.get(token)
        if at and (at.expires_at is None or at.expires_at > time.time()):
            return at
        return None

    async def revoke_token(
        self, token: ServerAccessToken | RefreshToken
    ) -> None:
        if isinstance(token, ServerAccessToken):
            self._access_tokens.pop(token.token, None)
        else:
            self._refresh_tokens.pop(token.token, None)
