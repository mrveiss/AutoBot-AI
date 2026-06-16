# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""JWKS (JSON Web Key Set) endpoint for public-key distribution (#10196).

The identity authority (autobot-backend) exposes its RSA public key here so
consumer services (SLM, browser workers, any future service) can verify RS256
JWTs using only the public key — never the private key.

Two canonical paths are registered:
  GET /.well-known/jwks.json  — RFC 8414 discovery path
  GET /api/auth/jwks           — convenience path alongside other /api/auth routes

Both are unauthenticated (JWKS is intentionally public, like any OAuth server's
discovery endpoint).

JWK format
----------
The response carries the RSA public key as a JWK Set with the following fields:

  kty  : "RSA"
  use  : "sig"           (key is used for signature verification)
  alg  : "RS256"
  kid  : key ID matching the ``kid`` header in issued JWTs
  n    : base64url-encoded RSA modulus
  e    : base64url-encoded RSA public exponent

Consumers can reconstruct the public key from ``n`` / ``e`` using any standard
JWK library (PyJWT's ``RSAAlgorithm.from_jwk``, jose, etc.) and then call
``jwt.decode(token, pub_key, algorithms=["RS256"])``.
"""

import json
from typing import Any, Dict

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from jwt.algorithms import RSAAlgorithm

from auth_middleware import get_auth_middleware
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Two routers: one for /.well-known/ (mounted without /api prefix in app_factory)
# and one for /auth (mounted under /api/auth).
well_known_router = APIRouter(tags=["jwks"])
auth_router = APIRouter(tags=["auth", "jwks"])


def _build_jwks() -> Dict[str, Any]:
    """Build the JWK Set from the current RS256 public key.

    Returns a dict with a ``keys`` list containing one RSA public JWK.
    PyJWT's ``RSAAlgorithm.to_jwk`` produces the base64url-encoded ``n``/``e``
    values; we add ``use``, ``alg``, and ``kid`` fields per RFC 7517.
    """
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization

    mw = get_auth_middleware()
    pem_public = mw.jwt_public_key
    kid = mw.jwt_kid

    # Load the public key object so PyJWT can serialise it to JWK
    public_key = serialization.load_pem_public_key(
        pem_public.encode("utf-8"),
        backend=default_backend(),
    )

    # PyJWT produces {"kty","key_ops","n","e"} — we augment with RFC 7517 fields
    base_jwk: Dict[str, Any] = json.loads(RSAAlgorithm.to_jwk(public_key))
    base_jwk.pop("key_ops", None)  # replace with "use" (more standard)
    base_jwk.update(
        {
            "use": "sig",
            "alg": "RS256",
            "kid": kid,
        }
    )

    return {"keys": [base_jwk]}


@well_known_router.get("/jwks.json", include_in_schema=True)
async def get_jwks_well_known() -> JSONResponse:
    """Return the JWKS at the RFC 8414 well-known discovery path.

    This endpoint is **unauthenticated** — the public key is intentionally
    readable by any client that needs to verify JWTs.
    """
    try:
        jwks = _build_jwks()
    except Exception as exc:
        logger.error("Failed to build JWKS response: %s", exc)
        return JSONResponse(status_code=503, content={"detail": "JWKS temporarily unavailable"})
    return JSONResponse(
        content=jwks,
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@auth_router.get("/jwks", include_in_schema=True)
async def get_jwks_auth() -> JSONResponse:
    """Return the JWKS at the /api/auth/jwks convenience path.

    Alias of the well-known endpoint — same response, same cache headers.
    Unauthenticated (public key distribution, RFC 7517).
    """
    return await get_jwks_well_known()
