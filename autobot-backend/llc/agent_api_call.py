# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One-purpose command a heartbeat agent uses to call the LLC Agent API (#20247).

``python agent_api_call.py METHOD PATH [JSON_BODY]``

A CLI agent that works from work-item text is untrusted input, so it is not given a general
``Bash`` or ``curl`` grant: it could send its bearer token anywhere. This command is the only
thing the adapter allows, and it can reach exactly one place -- ``AUTOBOT_LLC_API_BASE`` plus a
path under ``/llc/agent/``. It reads the base and ``AUTOBOT_LLC_API_KEY`` from the environment,
refuses an absolute URL or a path that leaves the prefix, does not follow redirects, and never
prints the key.

Standard library only, so the backend's own interpreter runs it with no project imports.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

AGENT_API_PREFIX = "/llc/agent/"
_METHODS = ("GET", "POST")
_PATH_RE = re.compile(r"^/llc/agent/[A-Za-z0-9._~/%-]*(\?[A-Za-z0-9._~%=&-]*)?$")
_TIMEOUT_SECONDS = 30


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect: a 3xx must not carry the bearer token elsewhere."""

    def redirect_request(self, *args, **kwargs):
        return None


def checked_agent_api_path(path: str) -> str:
    """*path* unchanged when it is a plain path under the Agent API prefix, else ``ValueError``."""
    decoded = urllib.parse.unquote(path.split("?", 1)[0])
    if not _PATH_RE.match(path) or ".." in decoded.split("/") or "//" in decoded or "\\" in decoded:
        raise ValueError(f"path must be under {AGENT_API_PREFIX} and contain no '..', got {path!r}")
    return path


def _build_request(method: str, path: str, body: str | None, env: dict) -> urllib.request.Request:
    base, key = env.get("AUTOBOT_LLC_API_BASE", ""), env.get("AUTOBOT_LLC_API_KEY", "")
    if not base.startswith(("http://", "https://")) or not key:
        raise ValueError("AUTOBOT_LLC_API_BASE and AUTOBOT_LLC_API_KEY must be set")
    data = None
    if body is not None:
        json.loads(body)  # reject a body the API would only 422
        data = body.encode("utf-8")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    return urllib.request.Request(
        base.rstrip("/") + checked_agent_api_path(path), data=data, method=method, headers=headers
    )


def run_agent_api_call(argv: list[str], env: dict, out, err) -> int:
    """Run one call; the response goes to *out*, a failure to *err*. Exit code 0 only on 2xx."""
    if len(argv) not in (2, 3) or argv[0].upper() not in _METHODS:
        err.write(f"usage: agent_api_call.py {'|'.join(_METHODS)} PATH [JSON_BODY]\n")
        return 2
    try:
        request = _build_request(argv[0].upper(), argv[1], argv[2] if len(argv) == 3 else None, env)
    except ValueError as exc:
        err.write(f"refused: {exc}\n")
        return 2
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=_TIMEOUT_SECONDS) as resp:
            out.write(resp.read().decode("utf-8", "replace").replace(env["AUTOBOT_LLC_API_KEY"], "[redacted]") + "\n")
        return 0
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace").replace(env["AUTOBOT_LLC_API_KEY"], "[redacted]")
        err.write(f"HTTP {exc.code}: {detail}\n")
        return 1
    except (urllib.error.URLError, OSError) as exc:
        err.write(f"request failed: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(run_agent_api_call(sys.argv[1:], dict(os.environ), sys.stdout, sys.stderr))
