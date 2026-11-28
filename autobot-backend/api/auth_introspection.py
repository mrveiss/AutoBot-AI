# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pure helpers for the ``/auth/validate`` token introspection route (#10195), split out of api/auth.py."""

from typing import Dict

from fastapi import Request

from api.schemas_agent import AuthValidateClaims, AuthValidateRequest


def _extract_token_from_request(request: Request, body: AuthValidateRequest | None) -> str | None:
    """Return the token string from body or Bearer header (body takes priority)."""
    if body and body.token:
        return body.token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1]
    return None


def _build_validate_claims(payload: Dict) -> AuthValidateClaims:
    """Extract the public claim fields from a verified JWT payload."""
    exp_raw = payload.get("exp")
    exp_int: int | None = int(exp_raw) if exp_raw is not None else None
    return AuthValidateClaims(
        username=payload.get("username"),
        role=payload.get("role"),
        user_id=payload.get("user_id"),
        org_id=payload.get("org_id"),
        email=payload.get("email"),
        exp=exp_int,
    )
