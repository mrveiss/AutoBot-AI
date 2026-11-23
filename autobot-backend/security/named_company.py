# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The company a request or WebSocket names, parsed once for every caller (#21997).

One definition of "which company does this connection name": the ``X-Organization-Id`` header, then (where the
route is a company route) a ``company_id`` / ``id`` path parameter, then the ``company_id`` query parameter. The
query is how a browser WebSocket names its company, since it cannot set a header. A value that is not a UUID is not
a name: a malformed header falls through to the next source rather than failing. Naming is not authorising;
membership is checked by each caller (``get_tenant_context``, ``resolve_company_scope``).
"""

from __future__ import annotations

import uuid

from starlette.requests import HTTPConnection

ORGANIZATION_HEADER = "X-Organization-Id"
COMPANY_QUERY_PARAM = "company_id"


def parse_uuid(value) -> uuid.UUID | None:
    """*value* as a UUID, ``None`` when empty or malformed (never raises)."""
    try:
        return uuid.UUID(str(value)) if value else None
    except (ValueError, TypeError):
        return None


def named_company(conn: HTTPConnection, *, from_path: bool = False) -> uuid.UUID | None:
    """The first valid company id *conn* names: header, then path (only if *from_path*), then query."""
    named = parse_uuid(conn.headers.get(ORGANIZATION_HEADER))
    if named is None and from_path:
        named = parse_uuid(conn.path_params.get("company_id") or conn.path_params.get("id"))
    return named or parse_uuid(conn.query_params.get(COMPANY_QUERY_PARAM))
