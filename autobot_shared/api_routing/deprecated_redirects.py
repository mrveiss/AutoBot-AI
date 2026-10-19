# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One-release 308 shims for routes that moved to a new path (#18722).

Owner rule 2026-10-17: callers move to the one current path; the old path
answers a method-preserving ``308`` for one release, then is removed. This is
the single helper for that shim -- never hand-write a redirect handler.

The shim routes are added to the *same* router as the new route, so they are
mounted under the same prefix and the ``Location`` is the request's own path
with the old suffix swapped for the new one (query string kept). They carry no
auth dependency on purpose: a 308 reveals nothing, the redirected request is
authorised by the target route. They are hidden from the OpenAPI schema so
generated client types describe only the current path.
"""

from collections.abc import Mapping
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import Response

HTTP_PERMANENT_REDIRECT = 308


def _redirect_handler(old_path: str, new_path: str):
    """Build the handler that 308s ``old_path`` to ``new_path`` (same prefix)."""

    async def _redirect(request: Request) -> Response:
        params = request.path_params
        served_old = old_path.format(**params)
        prefix = request.url.path.removesuffix(served_old)
        target = quote(prefix + new_path.format(**params), safe="/")
        if request.url.query:
            target = f"{target}?{request.url.query}"
        return Response(
            status_code=HTTP_PERMANENT_REDIRECT,
            headers={
                "Location": target,
                "Deprecation": "true",
                "Link": f'<{target}>; rel="successor-version"',
            },
        )

    return _redirect


def add_deprecated_redirects(router: APIRouter, moves: Mapping[tuple[str, str], str]) -> None:
    """Add a 308 shim for every ``(method, old_path) -> new_path`` move.

    Paths are router-relative and may carry the same ``{param}`` names on
    both sides.
    """
    for (method, old_path), new_path in moves.items():
        router.add_api_route(
            old_path,
            _redirect_handler(old_path, new_path),
            methods=[method],
            status_code=HTTP_PERMANENT_REDIRECT,
            include_in_schema=False,
        )
