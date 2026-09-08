import os
from functools import lru_cache
from urllib.parse import urlparse

import jwt
from fastapi import HTTPException
from jwt import PyJWKClient


def neon_auth_url() -> str:
    url = os.environ.get("NEON_AUTH_URL", "").strip().rstrip("/")
    if not url:
        raise RuntimeError("NEON_AUTH_URL is not set")
    return url


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    return PyJWKClient(f"{neon_auth_url()}/.well-known/jwks.json", cache_jwk_set=True)


def _issuers() -> list[str]:
    base = neon_auth_url()
    origin = f"{urlparse(base).scheme}://{urlparse(base).netloc}"
    return [origin, base]


def verify_access_token(token: str) -> dict:
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        last_error: Exception | None = None
        for issuer in _issuers():
            try:
                return jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256", "ES256", "EdDSA"],
                    issuer=issuer,
                    options={"verify_aud": False},
                )
            except jwt.InvalidIssuerError as exc:
                last_error = exc
        if last_error:
            raise last_error
        raise jwt.InvalidTokenError("Unable to verify token issuer")
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
