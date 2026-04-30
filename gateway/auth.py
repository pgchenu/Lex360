"""JWT decode + sealed-token wrapping for the gateway.

Two kinds of tokens flow through the gateway:

1. Raw Lexis 360 JWTs — what the user copies from localStorage on
   lexis360intelligence.fr. Three-segment, signed by Lexis (we cannot
   verify the signature; we only check structure + `exp`).

2. Sealed gateway tokens — what we mint during the OAuth 2.1 flow so
   that OAuth-strict clients (ChatGPT, claude.ai web) can use them as
   bearer access tokens. A sealed token wraps a Lexis JWT inside an
   AES-GCM-encrypted, self-contained envelope. No server-side state.

The wire format for sealed tokens is `lxg_<base64url(nonce + ciphertext)>`.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

EXPIRY_BUFFER_SECONDS = 300
SEAL_PREFIX = "lxg_"


class AuthError(Exception):
    pass


def _b64url_decode(data: str) -> bytes:
    pad = (4 - len(data) % 4) % 4
    return base64.urlsafe_b64decode(data + "=" * pad)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def decode_jwt_payload(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthError("invalid JWT structure")
    try:
        return json.loads(_b64url_decode(parts[1]))
    except (ValueError, json.JSONDecodeError) as e:
        raise AuthError(f"unparseable JWT payload: {e}") from e


def validate_lexis_jwt(token: str) -> dict:
    """Return decoded payload if the JWT is structurally valid and not expired.

    Mirrors lex360/auth.py: no signature verification (we don't have Lexis's
    public key), exp checked with a 5-minute safety buffer.
    """
    payload = decode_jwt_payload(token)
    exp = payload.get("exp")
    if exp is None:
        raise AuthError("JWT has no exp claim")
    if time.time() > float(exp) - EXPIRY_BUFFER_SECONDS:
        raise AuthError("JWT is expired or about to expire")
    return payload


def _derive_key(secret: str) -> bytes:
    if not secret:
        raise AuthError("GATEWAY_SECRET is empty")
    return hashlib.sha256(secret.encode("utf-8")).digest()


def seal(payload: dict, secret: str) -> str:
    """Encrypt+authenticate a payload using AES-GCM.

    The payload SHOULD include a `kind` field ("access" / "code" / "client")
    and an `exp` field (unix timestamp). Callers verify these on unseal.
    """
    key = _derive_key(secret)
    nonce = os.urandom(12)
    plaintext = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    return SEAL_PREFIX + _b64url_encode(nonce + ciphertext)


def unseal(token: str, secret: str) -> dict:
    if not token.startswith(SEAL_PREFIX):
        raise AuthError("not a gateway-sealed token")
    raw = _b64url_decode(token[len(SEAL_PREFIX):])
    if len(raw) < 13:
        raise AuthError("sealed token too short")
    nonce, ciphertext = raw[:12], raw[12:]
    try:
        plaintext = AESGCM(_derive_key(secret)).decrypt(nonce, ciphertext, None)
    except Exception as e:
        raise AuthError("sealed token authentication failed") from e
    payload = json.loads(plaintext)
    exp = payload.get("exp")
    if exp is not None and time.time() > float(exp):
        raise AuthError("sealed token expired")
    return payload


def extract_bearer(authorization_header: str | None) -> str | None:
    if not authorization_header:
        return None
    parts = authorization_header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


def resolve_lexis_jwt(authorization_header: str | None, secret: str) -> str:
    """Given an Authorization header, return the underlying raw Lexis JWT.

    Accepts both surfaces:
      - Bearer <sealed gateway access token>   (OAuth path)
      - Bearer <raw Lexis JWT>                  (direct Bearer path)

    Raises AuthError on any failure.
    """
    token = extract_bearer(authorization_header)
    if not token:
        raise AuthError("missing or malformed Authorization header")

    if token.startswith(SEAL_PREFIX):
        payload = unseal(token, secret)
        if payload.get("kind") != "access":
            raise AuthError("sealed token is not an access token")
        jwt = payload.get("jwt")
        if not jwt:
            raise AuthError("sealed access token has no inner jwt")
        validate_lexis_jwt(jwt)
        return jwt

    validate_lexis_jwt(token)
    return token
