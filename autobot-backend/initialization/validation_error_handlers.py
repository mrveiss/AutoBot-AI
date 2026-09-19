# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Strip the submitted payload out of every 422 response (#16428 security review).

FastAPI's default ``RequestValidationError`` handler echoes the full
submitted value in each error's ``input`` key, and Pydantic v2 attaches the
whole request body to a model-level (``@model_validator(mode="after")``)
failure rather than just the offending field. Neither ``SecretStr`` nor a
field-level constraint (``max_length``) prevents this: the raw value the
caller sent is already in ``ValidationError.errors()`` before any field type
gets a chance to redact it, and the default handler responds with that verbatim.

Concretely: ``SecretCreateRequest``'s connector-bridge validator raises on
``connector_id`` set without ``auth_type``, and the default handler's 422
then contains the real ``credentials`` dict (OAuth ``client_secret``,
``refresh_token``) submitted alongside it. The sibling case is a ``value``
over its ``max_length`` -- the oversized secret itself comes back in ``input``.

Fixed once, for every router, rather than per-endpoint: any current or future
request model with a secret-shaped field has the same exposure the moment its
validation fails, and a field-level workaround only ever covers the field
someone thought to guard.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def register_validation_error_handlers(app: FastAPI) -> None:
    """Replace FastAPI's default 422 body with one that never echoes input."""

    @app.exception_handler(RequestValidationError)
    async def _validation_error_without_input(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Pydantic v2's error dicts carry loc/msg/type plus input (the
        # submitted value, sometimes the whole request body) and ctx (which
        # can itself hold a value from the payload, e.g. an enum's rejected
        # member). Keep only what identifies WHERE and WHY it failed, never
        # WHAT was submitted.
        safe_errors = [
            {"loc": list(e.get("loc", [])), "msg": e.get("msg", ""), "type": e.get("type", "")} for e in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": safe_errors})
