"""OAuth 2.1 endpoints (RFC 8414, 9728, 7591, 7636) for OAuth-strict clients.

Stateless — every artifact (client_id, authorization code, access token) is a
self-contained sealed envelope. Restarting the gateway does not invalidate
already-issued artifacts (as long as GATEWAY_SECRET stays stable) and does
not require any database.

Issued artifact kinds:
  - "client": dynamic-registration result. Holds the registered redirect_uris.
  - "code"  : authorization code. Holds the encrypted Lexis JWT, the PKCE
              code_challenge, the redirect_uri, the client_id, exp = now+60s.
  - "access": access token. Holds the encrypted Lexis JWT, exp = lexis_exp.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from urllib.parse import urlencode, urlparse

from . import auth

CODE_TTL_SECONDS = 60


def build_resource_metadata(issuer: str) -> dict:
    """RFC 9728 protected resource metadata."""
    return {
        "resource": issuer,
        "authorization_servers": [issuer],
        "bearer_methods_supported": ["header"],
        "resource_documentation": f"{issuer}/",
    }


def build_authorization_server_metadata(issuer: str) -> dict:
    """RFC 8414 authorization server metadata."""
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/token",
        "registration_endpoint": f"{issuer}/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["mcp"],
    }


def register_client(metadata: dict, secret: str) -> dict:
    """RFC 7591 dynamic client registration.

    We accept any submission and mint a self-contained client_id that
    encodes the registered redirect_uris. No DB.
    """
    redirect_uris = metadata.get("redirect_uris") or []
    if not isinstance(redirect_uris, list) or not redirect_uris:
        raise ValueError("redirect_uris is required")
    for uri in redirect_uris:
        if not isinstance(uri, str):
            raise ValueError("redirect_uri must be a string")
        parsed = urlparse(uri)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"invalid redirect_uri: {uri}")

    client_id = auth.seal(
        {
            "kind": "client",
            "redirect_uris": redirect_uris,
            "iat": int(time.time()),
        },
        secret,
    )
    return {
        "client_id": client_id,
        "client_id_issued_at": int(time.time()),
        "redirect_uris": redirect_uris,
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
    }


def validate_authorize_request(
    client_id: str,
    redirect_uri: str,
    response_type: str,
    code_challenge: str,
    code_challenge_method: str,
    secret: str,
) -> None:
    """Reject malformed /authorize requests before showing the HTML form.

    Called from the GET /authorize handler. Raises ValueError on failure;
    the caller turns that into a 400 with a human-readable error page.
    """
    if response_type != "code":
        raise ValueError("response_type must be 'code'")
    if code_challenge_method != "S256":
        raise ValueError("code_challenge_method must be 'S256'")
    if not code_challenge:
        raise ValueError("code_challenge is required")

    try:
        client = auth.unseal(client_id, secret)
    except auth.AuthError as e:
        raise ValueError(f"invalid client_id: {e}") from e
    if client.get("kind") != "client":
        raise ValueError("client_id is not a registered client")
    if redirect_uri not in client.get("redirect_uris", []):
        raise ValueError("redirect_uri is not registered for this client")


def issue_authorization_code(
    lexis_jwt: str,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    secret: str,
) -> str:
    auth.validate_lexis_jwt(lexis_jwt)
    return auth.seal(
        {
            "kind": "code",
            "jwt": lexis_jwt,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "exp": int(time.time()) + CODE_TTL_SECONDS,
        },
        secret,
    )


def _verify_pkce(code_verifier: str, code_challenge: str) -> bool:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return secrets.compare_digest(expected, code_challenge)


def exchange_code_for_access_token(
    code: str,
    code_verifier: str,
    client_id: str,
    redirect_uri: str,
    secret: str,
) -> dict:
    """RFC 6749 §4.1.3 + RFC 7636 token endpoint.

    Returns a dict shaped for the `/token` JSON response. No refresh token
    by design: the access token expires at the same instant as the
    underlying Lexis JWT, so re-paste is required when it expires.
    """
    try:
        unsealed = auth.unseal(code, secret)
    except auth.AuthError as e:
        raise ValueError(f"invalid_grant: {e}") from e

    if unsealed.get("kind") != "code":
        raise ValueError("invalid_grant: not an authorization code")
    if unsealed.get("client_id") != client_id:
        raise ValueError("invalid_grant: client_id mismatch")
    if unsealed.get("redirect_uri") != redirect_uri:
        raise ValueError("invalid_grant: redirect_uri mismatch")
    if not _verify_pkce(code_verifier, unsealed.get("code_challenge", "")):
        raise ValueError("invalid_grant: PKCE verification failed")

    lexis_jwt = unsealed["jwt"]
    payload = auth.validate_lexis_jwt(lexis_jwt)
    lexis_exp = int(payload["exp"])
    now = int(time.time())

    access_token = auth.seal(
        {"kind": "access", "jwt": lexis_jwt, "exp": lexis_exp},
        secret,
    )
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": max(1, lexis_exp - now),
        "scope": "mcp",
    }


def build_redirect(redirect_uri: str, code: str, state: str | None) -> str:
    params = {"code": code}
    if state:
        params["state"] = state
    sep = "&" if "?" in redirect_uri else "?"
    return f"{redirect_uri}{sep}{urlencode(params)}"
