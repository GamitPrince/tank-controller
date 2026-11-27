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

The caller is the token's ``sub``, with a role and a customer (S-076, ADR-0008
decision 3). The role is the one ADR-0008 role named in ``cognito:groups``;
other group names are ignored. The customer is ``custom:customer_id``, our
``customers.id`` as decimal digits, and a service caller (our staff) is never
tied to one. A token that passes but names no role, two roles, or no usable
customer gets 403 with a fixed detail; the reason is logged, never the token.
A handler takes the caller with ``Depends(require_caller)``; FastAPI runs the
check once per request. A customer's caller reads only that customer's share of
a device (S-078, ``tankapi.readings``); service reads every device and is not
audited yet.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from enum import Enum
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
GROUPS_CLAIM = "cognito:groups"
CUSTOMER_CLAIM = "custom:customer_id"
# A positive decimal integer without padding; 18 digits always fit a BIGINT, and
# [0-9] rather than \d refuses other scripts' digits.
CUSTOMER_ID_PATTERN = re.compile(r"[1-9][0-9]{0,17}")

HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
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


class Role(str, Enum):
    """The four ADR-0008 roles, named as the user pool's groups are."""

    OPERATOR = "operator"
    MAINTENANCE = "maintenance"
    ADMIN = "admin"
    SERVICE = "service"


ROLES_BY_GROUP = {role.value: role for role in Role}


class CallerRefused(Exception):
    """A valid token whose role or customer cannot be used; the message is the logged reason."""


@dataclass(frozen=True)
class Caller:
    """Who sent a request whose token passed: ``customer_id`` is ``None`` for service only."""

    subject: str
    role: Role
    customer_id: int | None


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
    """The caller of a ``/v1`` request; 401 without a valid token, 403 without a usable
    role or customer, 503 unconfigured."""
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
    try:
        return caller_from(claims)
    except CallerRefused as error:
        log.warning("caller %s refused: %s", claims["sub"], error)
        raise HTTPException(HTTP_FORBIDDEN, "not allowed") from None


def caller_from(claims: dict[str, Any]) -> Caller:
    """The caller named by a verified token's claims; raises :class:`CallerRefused`."""
    role = _role(claims.get(GROUPS_CLAIM))
    # Service is our staff, never one customer's: any customer value is ignored.
    customer_id = None if role is Role.SERVICE else _customer_id(claims.get(CUSTOMER_CLAIM))
    return Caller(subject=claims["sub"], role=role, customer_id=customer_id)


def _role(groups: Any) -> Role:
    if not isinstance(groups, list):
        raise CallerRefused("no group list")
    named = [group for group in groups if isinstance(group, str)]
    roles = {ROLES_BY_GROUP[group] for group in named if group in ROLES_BY_GROUP}
    if len(roles) != 1:
        raise CallerRefused(f"{len(roles)} roles in the groups, not one")
    return roles.pop()


def _customer_id(value: Any) -> int:
    if not isinstance(value, str) or not CUSTOMER_ID_PATTERN.fullmatch(value):
        raise CallerRefused("no customer, or not a positive decimal id")
    return int(value)


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
