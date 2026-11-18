# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Rich-payload validation for chart and code cells.

Extracted from `api/canvas.py` (#17020). That module is grandfathered at 637
lines in a **shrink-only** ratchet, and adding the canvas event publisher's call
sites pushed it over. The rule is to split rather than raise a ceiling, and this
is the largest piece of `api/canvas.py` that is pure logic: no router, no
session, no request -- validation of a payload dict against a cell type.

Behaviour is unchanged. It still raises `HTTPException(422)` rather than a
domain error, because its callers are route handlers and the messages are
already written for a client; converting that to a domain exception and
translating at the boundary is a larger change than a size split should carry,
and would alter the response bodies.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from canvas.vega_validation import validate_vegalite_spec


def validate_and_sanitize_rich_payload(rich_payload: dict | None, cell_type: str) -> dict | None:
    """
    Validate and sanitize a rich payload.  Returns the sanitized payload or None.

    Rules (Phase 2):
    - chart cells: richPayload must have payloadType='vega-lite', specVersion='5',
      and spec that passes Vega-Lite v5 validation.
    - code cells: richPayload must have payloadType='code'; executable must be false.
    - executable: true is always rejected.
    """
    if rich_payload is None:
        return None
    if not isinstance(rich_payload, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="richPayload must be a JSON object or null.",
        )

    payload_type = rich_payload.get("payloadType")

    # executable: true is forbidden in Phase 2
    if rich_payload.get("executable") is True:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="executable: true is not supported until Phase 3.",
        )

    if cell_type == "chart":
        if payload_type != "vega-lite":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="chart cells require richPayload.payloadType='vega-lite'.",
            )
        if rich_payload.get("specVersion") != "5":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="chart cells require richPayload.specVersion='5' (Vega-Lite v5).",
            )
        try:
            sanitized_spec = validate_vegalite_spec(rich_payload.get("spec"))
        except ValueError as exc:
            # 422 = client-input validation error; the message is crafted by
            # validate_vegalite_spec and reflects only the caller's own spec,
            # so returning it leaks no internal state (unlike 500 paths).
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        return {**rich_payload, "spec": sanitized_spec, "executable": False}

    if cell_type == "code":
        if payload_type != "code":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="code cells require richPayload.payloadType='code'.",
            )
        # Force executable: false
        return {**rich_payload, "executable": False}

    # For text/image cells, richPayload is ignored (Phase 1 compatibility)
    return None
