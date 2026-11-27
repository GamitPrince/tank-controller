import base64
import hashlib
import hmac
import json
import logging
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import access_tokens as tokens
import pytest
from cryptography.hazmat.primitives import serialization
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from tankapi import auth
from tankapi.main import app

# The token check runs before the endpoint opens a database session, so a
# refused request needs no database.
URL = "/v1/devices/SIM-0001/readings"
PARAMS = {"signal": 1, "from": 0, "to": 1}
SETTINGS_VARIABLES = (
    auth.ISSUER_VARIABLE,
    auth.CLIENT_ID_VARIABLE,
    auth.JWKS_FILE_VARIABLE,
    auth.JWKS_URL_VARIABLE,
)
PAST = -(auth.LEEWAY_S + tokens.LIFETIME_S)
FUTURE = auth.LEEWAY_S + tokens.LIFETIME_S
GROUPS = auth.GROUPS_CLAIM
CUSTOMER = auth.CUSTOMER_CLAIM


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def hand_made(alg: str, secret: bytes) -> str:
    """A token with this ``alg``, HMAC-signed with ``secret``, or unsigned when it is empty."""
    head = {"alg": alg, "kid": tokens.KID}
    signing_input = f"{b64(json.dumps(head).encode())}.{b64(json.dumps(tokens.claims()).encode())}"
    signature = hmac.new(secret, signing_input.encode(), hashlib.sha256).digest() if secret else b""
    return f"{signing_input}.{b64(signature)}"


def public_pem() -> bytes:
    public_key = tokens.private_key(tokens.KID).public_key()
    return public_key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def now() -> int:
    return int(time.time())


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.dependency_overrides[auth.get_settings] = tokens.settings
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def no_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in SETTINGS_VARIABLES:
        monkeypatch.delenv(name, raising=False)


def assert_unauthenticated(response) -> None:
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json() == {"detail": "not authenticated"}


def caller(**changes: object) -> auth.Caller:
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=tokens.token(**changes))
    return auth.require_caller(tokens.settings(), credentials)


def test_valid_access_token_names_its_caller() -> None:
    assert caller(sub="u-7") == auth.Caller("u-7", auth.Role.OPERATOR, 7)


@pytest.mark.parametrize(
    ("role", "customer_id"),
    [
        (auth.Role.OPERATOR, 7),
        (auth.Role.MAINTENANCE, 7),
        (auth.Role.ADMIN, 7),
        pytest.param(auth.Role.SERVICE, None, id="service-customer-ignored"),
    ],
)
def test_each_role_is_read_with_its_customer(role: auth.Role, customer_id: int | None) -> None:
    assert caller(**{GROUPS: [role.value]}) == auth.Caller("user-1", role, customer_id)


@pytest.mark.parametrize("customer", [None, "abc", "0"], ids=["none", "malformed", "zero"])
def test_service_caller_needs_no_customer(customer: str | None) -> None:
    assert caller(**{GROUPS: ["service"], CUSTOMER: customer}).customer_id is None


def test_group_names_that_are_not_roles_are_ignored() -> None:
    groups = ["plant-north", "operator", "us-east-1_pool_Google", 5]

    assert caller(**{GROUPS: groups, CUSTOMER: "123456789012345678"}) == auth.Caller(
        "user-1", auth.Role.OPERATOR, 123456789012345678
    )


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({GROUPS: None}, id="no-groups-claim"),
        pytest.param({GROUPS: []}, id="empty-groups"),
        pytest.param({GROUPS: "operator"}, id="groups-not-a-list"),
        pytest.param({GROUPS: ["operator", "admin"]}, id="two-roles"),
        pytest.param({GROUPS: ["supervisor"]}, id="unknown-group-only"),
        pytest.param({CUSTOMER: None}, id="no-customer"),
        pytest.param({CUSTOMER: ""}, id="empty-customer"),
        pytest.param({CUSTOMER: "abc"}, id="non-digit-customer"),
        pytest.param({CUSTOMER: "0"}, id="zero-customer"),
        pytest.param({CUSTOMER: "-1"}, id="negative-customer"),
        pytest.param({CUSTOMER: "07"}, id="zero-padded-customer"),
        pytest.param({CUSTOMER: " 7"}, id="space-padded-customer"),
        pytest.param({CUSTOMER: "7.0"}, id="float-like-customer"),
        pytest.param({CUSTOMER: 7}, id="number-not-string-customer"),
        pytest.param({CUSTOMER: "1" * 19}, id="too-long-customer"),
        pytest.param({CUSTOMER: "٧"}, id="arabic-indic-digit-customer"),
    ],
)
def test_valid_token_without_a_usable_role_or_customer_is_forbidden(
    client: TestClient, caplog: pytest.LogCaptureFixture, changes: dict[str, object]
) -> None:
    caplog.set_level(logging.INFO, logger=auth.__name__)
    token = tokens.token(**changes)

    response = client.get(URL, params=PARAMS, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert response.json() == {"detail": "not allowed"}
    assert "WWW-Authenticate" not in response.headers
    assert "caller user-1 refused" in caplog.text
    assert token not in caplog.text


@pytest.mark.parametrize(
    "make",
    [
        pytest.param(lambda: tokens.token(exp=now() + PAST, iat=now() + 2 * PAST), id="expired"),
        pytest.param(lambda: tokens.token(nbf=now() + FUTURE), id="not-yet-valid"),
        pytest.param(lambda: tokens.token(iss="https://other.invalid/pool"), id="wrong-issuer"),
        pytest.param(lambda: tokens.token(client_id="other-client"), id="other-app-client"),
        pytest.param(
            lambda: tokens.token(token_use="id", client_id=None, aud=tokens.CLIENT_ID),
            id="id-token",
        ),
        pytest.param(lambda: tokens.token(token_use="refresh"), id="wrong-token-use"),
        pytest.param(lambda: tokens.token(exp=None), id="no-expiry"),
        pytest.param(lambda: tokens.token(sub=None), id="no-subject"),
        pytest.param(lambda: tokens.token(sub=""), id="empty-subject"),
        pytest.param(lambda: tokens.token(key="stranger"), id="bad-signature"),
        pytest.param(
            lambda: tokens.token(key="stranger", **{GROUPS: None}), id="bad-signature-and-no-role"
        ),
        pytest.param(lambda: tokens.token(kid="other-key"), id="unknown-kid"),
        pytest.param(lambda: hand_made("none", b""), id="alg-none"),
        pytest.param(lambda: hand_made("HS256", public_pem()), id="hs256-with-public-key"),
        pytest.param(lambda: "not-a-jwt", id="malformed-token"),
    ],
)
def test_bad_token_is_refused_without_saying_why(
    client: TestClient, caplog: pytest.LogCaptureFixture, make: Callable[[], str]
) -> None:
    caplog.set_level(logging.INFO, logger=auth.__name__)
    token = make()

    assert_unauthenticated(
        client.get(URL, params=PARAMS, headers={"Authorization": f"Bearer {token}"})
    )
    assert "token refused" in caplog.text
    assert token not in caplog.text


@pytest.mark.parametrize("header", [None, "Basic dXNlcjpwYXNz", "Bearer", "Bearer  "])
def test_missing_or_malformed_header_is_refused(client: TestClient, header: str | None) -> None:
    headers = {} if header is None else {"Authorization": header}

    assert_unauthenticated(client.get(URL, params=PARAMS, headers=headers))


def test_unconfigured_app_refuses_every_v1_request_and_health_stays_open(no_settings: None) -> None:
    client = TestClient(app)

    assert client.get(URL, params=PARAMS, headers=tokens.bearer()).status_code == 503
    assert client.get("/health").status_code == 200


def test_symmetric_key_in_the_jwks_is_never_used() -> None:
    hmac_key = {"kty": "oct", "k": b64(b"k" * 32), "kid": "hmac", "alg": "HS256"}
    keys = auth.JwksKeys({"keys": [*tokens.jwks()["keys"], hmac_key]})

    assert keys.key_for(tokens.KID) is not None
    assert keys.key_for("hmac") is None


@pytest.mark.parametrize(
    "values",
    [
        {},
        {auth.ISSUER_VARIABLE: tokens.ISSUER, auth.CLIENT_ID_VARIABLE: tokens.CLIENT_ID},
        {auth.CLIENT_ID_VARIABLE: tokens.CLIENT_ID, auth.JWKS_URL_VARIABLE: "https://k.invalid"},
        {
            auth.ISSUER_VARIABLE: tokens.ISSUER,
            auth.CLIENT_ID_VARIABLE: tokens.CLIENT_ID,
            auth.JWKS_URL_VARIABLE: "http://keys.invalid/jwks.json",
        },
        {
            auth.ISSUER_VARIABLE: tokens.ISSUER,
            auth.CLIENT_ID_VARIABLE: tokens.CLIENT_ID,
            auth.JWKS_FILE_VARIABLE: "jwks.json",
            auth.JWKS_URL_VARIABLE: "https://keys.invalid/jwks.json",
        },
    ],
)
def test_incomplete_settings_leave_the_check_unconfigured(
    no_settings: None, monkeypatch: pytest.MonkeyPatch, values: dict[str, str]
) -> None:
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    assert auth.get_settings() is None


def test_settings_read_a_local_jwks_file(
    no_settings: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    jwks_file = tmp_path / "jwks.json"
    jwks_file.write_text(json.dumps(tokens.jwks()))
    monkeypatch.setenv(auth.ISSUER_VARIABLE, tokens.ISSUER)
    monkeypatch.setenv(auth.CLIENT_ID_VARIABLE, tokens.CLIENT_ID)
    monkeypatch.setenv(auth.JWKS_FILE_VARIABLE, str(jwks_file))

    settings = auth.get_settings()

    assert (settings.issuer, settings.client_id) == (tokens.ISSUER, tokens.CLIENT_ID)
    assert settings.keys.key_for(tokens.KID) is not None


def test_settings_with_a_jwks_url_fetch_nothing_until_a_key_is_needed(
    no_settings: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(auth.ISSUER_VARIABLE, tokens.ISSUER)
    monkeypatch.setenv(auth.CLIENT_ID_VARIABLE, tokens.CLIENT_ID)
    monkeypatch.setenv(auth.JWKS_URL_VARIABLE, "https://keys.invalid/jwks.json")

    assert isinstance(auth.get_settings().keys, auth.RemoteJwks)


def test_remote_jwks_finds_a_pool_key_and_refuses_an_unknown_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys = auth.RemoteJwks("https://keys.invalid/jwks.json")
    monkeypatch.setattr(keys._client, "fetch_data", tokens.jwks)

    assert keys.key_for(tokens.KID) is not None
    assert keys.key_for("other-key") is None


def test_openapi_declares_bearer_on_every_v1_operation_and_not_on_health(
    client: TestClient,
) -> None:
    # Only require_caller uses the bearer scheme, so it is on every /v1 operation.
    schema = client.get("/openapi.json").json()
    v1 = [ops for path, ops in schema["paths"].items() if path.startswith("/v1")]

    assert schema["components"]["securitySchemes"] == {
        "HTTPBearer": {"type": "http", "scheme": "bearer"}
    }
    assert v1 and all(op["security"] == [{"HTTPBearer": []}] for ops in v1 for op in ops.values())
    assert "security" not in schema["paths"]["/health"]["get"]
