"""Cognito-shaped access tokens for the tests (S-075).

Every key is generated at run time, so no private key or token is ever stored
in the repository (ADR-0005 rule 9), and nothing is fetched from the network.
"""

import time
from functools import cache
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from tankapi.auth import AuthSettings, JwksKeys

ISSUER = "https://issuer.invalid/test-pool"
CLIENT_ID = "test-client"
KID = "test-key"
LIFETIME_S = 600
RSA_EXPONENT = 65537
RSA_BITS = 2048


@cache
def private_key(name: str) -> rsa.RSAPrivateKey:
    """One key per name for the whole run; only ``KID``'s public half is in the JWKS."""
    return rsa.generate_private_key(public_exponent=RSA_EXPONENT, key_size=RSA_BITS)


def jwks() -> dict[str, Any]:
    jwk = RSAAlgorithm.to_jwk(private_key(KID).public_key(), as_dict=True)
    return {"keys": [jwk | {"kid": KID, "alg": "RS256", "use": "sig"}]}


def settings() -> AuthSettings:
    return AuthSettings(ISSUER, CLIENT_ID, JwksKeys(jwks()))


def claims(**changes: Any) -> dict[str, Any]:
    """A valid access token's claims; a change to ``None`` leaves that claim out."""
    now = int(time.time())
    valid = {
        "iss": ISSUER,
        "client_id": CLIENT_ID,
        "token_use": "access",
        "sub": "user-1",
        "iat": now,
        "exp": now + LIFETIME_S,
    }
    return {name: value for name, value in (valid | changes).items() if value is not None}


def token(key: str = KID, kid: str = KID, **changes: Any) -> str:
    return jwt.encode(claims(**changes), private_key(key), algorithm="RS256", headers={"kid": kid})


def bearer(**changes: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(**changes)}"}
