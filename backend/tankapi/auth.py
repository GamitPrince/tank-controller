"""Checking the caller's token on every ``/v1`` request (S-075).

ADR-0008 decision 2 puts login in Amazon Cognito and decision 3 has the backend
check every request. The browser sends Cognito's **access token** as
``Authorization: Bearer <token>`` ``[Confirm]``; :func:`require_caller` accepts
it only when it is signed with RS256 by a key in the pool's JWKS, comes from
the configured issuer, is within its ``exp`` and ``nbf``, was issued to the
configured app client (``client_id``) and has ``token_use`` ``access``. Any
other token, or none, gets 401 with ``WWW-Authenticate: Bearer`` and a detail
that does not say why; the reason is logged, never the token.

The issuer, the app client ID and where the keys come from (a local JWKS file
or the pool's JWKS URL) are environment settings, so no pool ID is written in
the repository. With any of them missing every ``/v1`` request gets 503: the
app fails closed rather than open.

The caller's identity is the token's ``sub``. Role and customer are read in the
next story; until per-customer scoping lands, any valid token reads any device.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Protocol

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

ISSUER_VARIABLE = "TANKAPI_AUTH_ISSUER"
CLIENT_ID_VARIABLE = "TANKAPI_AUTH_CLIENT_ID"
JWKS_FILE_VARIABLE = "TANKAPI_AUTH_JWKS_FILE"
JWKS_URL_VARIABLE = "TANKAPI_AUTH_JWKS_URL"

ALGORITHM = "RS256"
TOKEN_USE = "access"
REQUIRED_CLAIMS = ["exp", "iat", "iss", "sub", "client_id", "token_use"]
# Clock difference allowed on exp and nbf between Cognito and this server.
LEEWAY_S = 30
# How long fetched pool keys are kept before the JWKS is read again.
JWKS_LIFESPAN_S = 3600
HTTPS_PREFIX = "https://"

HTTP_UNAUTHORIZED = 401
HTTP_UNAVAILABLE = 503

log = logging.getLogger(__name__)


class KeySource(Protocol):
    """Where the pool's public signing keys come from."""

    def key_for(self, kid: str) -> Any | None:
        """The public key with this ``kid``, or ``None`` when there is none."""


class JwksKeys:
    """The RSA keys of a JWKS document already in memory: a local file, or a test's."""

    def __init__(self, jwks: dict[str, Any]) -> None:
        keys = jwt.PyJWKSet.from_dict(jwks).keys
        self._keys = {key.key_id: key.key for key in keys if key.key_type == "RSA"}

    def key_for(self, kid: str) -> Any | None:
        return self._keys.get(kid)


class RemoteJwks:
    """A Cognito pool's JWKS, fetched over HTTPS when first needed and cached."""

    def __init__(self, url: str) -> None:
        self._client = jwt.PyJWKClient(url, lifespan=JWKS_LIFESPAN_S)

    def key_for(self, kid: str) -> Any | None:
        try:
            return self._client.get_signing_key(kid).key
        except jwt.PyJWKClientError as error:
            log.warning("no pool key for this token: %s", error)
            return None


@dataclass(frozen=True)
class AuthSettings:
    """What a token is checked against."""

    issuer: str
    client_id: str
    keys: KeySource


@dataclass(frozen=True)
class Caller:
    """Who sent a request whose token passed."""

    subject: str


def get_settings() -> AuthSettings | None:
    """The settings from the environment, or ``None`` when they are incomplete."""
    variables = (ISSUER_VARIABLE, CLIENT_ID_VARIABLE, JWKS_FILE_VARIABLE, JWKS_URL_VARIABLE)
    return _settings_for(*(os.environ.get(name) or None for name in variables))


@lru_cache(maxsize=1)
def _settings_for(
    issuer: str | None, client_id: str | None, jwks_file: str | None, jwks_url: str | None
) -> AuthSettings | None:
    # Exactly one key source; a JWKS URL is fetched over HTTPS only.
    if not (issuer and client_id) or bool(jwks_file) == bool(jwks_url):
        return None
    if jwks_file:
        jwks = json.loads(Path(jwks_file).read_text(encoding="utf-8"))
        return AuthSettings(issuer, client_id, JwksKeys(jwks))
    if not jwks_url.startswith(HTTPS_PREFIX):
        return None
    return AuthSettings(issuer, client_id, RemoteJwks(jwks_url))


# auto_error off, so a missing header gets the same 401 as a bad token.
bearer = HTTPBearer(auto_error=False)


def require_caller(
    settings: Annotated[AuthSettings | None, Depends(get_settings)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Caller:
    """The caller of a ``/v1`` request; 401 without a valid token, 503 unconfigured."""
    if settings is None:
        log.error("token check is not configured; refusing every /v1 request")
        raise HTTPException(HTTP_UNAVAILABLE, "not available")
    if credentials is None:
        raise _unauthenticated()
    try:
        claims = _verified_claims(settings, credentials.credentials)
    except jwt.PyJWTError as error:
        log.info("token refused: %s", error)
        raise _unauthenticated() from None
    return Caller(subject=claims["sub"])


def _verified_claims(settings: AuthSettings, token: str) -> dict[str, Any]:
    header = jwt.get_unverified_header(token)
    # The algorithm is fixed here, never taken from the token: no none, no HS256.
    key = settings.keys.key_for(header.get("kid")) if header.get("alg") == ALGORITHM else None
    if key is None:
        raise jwt.InvalidTokenError("algorithm or key id not accepted")
    claims = jwt.decode(
        token,
        key,
        algorithms=[ALGORITHM],
        issuer=settings.issuer,
        leeway=LEEWAY_S,
        options={"require": REQUIRED_CLAIMS},
    )
    if claims["token_use"] != TOKEN_USE or claims["client_id"] != settings.client_id:
        raise jwt.InvalidTokenError("not an access token for this app client")
    if not isinstance(claims["sub"], str) or not claims["sub"]:
        raise jwt.InvalidTokenError("no subject")
    return claims


def _unauthenticated() -> HTTPException:
    return HTTPException(HTTP_UNAUTHORIZED, "not authenticated", {"WWW-Authenticate": "Bearer"})
