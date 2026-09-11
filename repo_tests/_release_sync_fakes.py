# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared fakes for the release-sync tests (#16246): one recorded API and one script loader.

Not a test module. ``release_sync_main_test.py`` and ``release_sync_tracking_issue_test.py``
both drive ``pipeline-scripts/release_sync_main.py`` through these, so a change to the
API the script speaks is made once, here.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
from typing import Any, Dict, List, Optional, Tuple

from repo_tests._paths import repo_root

SCRIPT = repo_root() / "pipeline-scripts" / "release_sync_main.py"

REPO = "mrveiss/AutoBot-AI"
HEAD = "release-sync-main"
SOURCE = "Dev_new_gui"
BASE = "main"
REFUSAL = {"message": "GitHub Actions is not permitted to create or approve pull requests."}

Route = Tuple[str, str, Tuple[int, Any]]


def load_script():
    spec = importlib.util.spec_from_file_location("release_sync_main", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pull(number: int, *, head: str = HEAD, base: str = BASE, repo: str = REPO, body: str = ""):
    return {
        "number": number,
        "head": {"ref": head, "repo": {"full_name": repo}},
        "base": {"ref": base},
        "body": body,
    }


def _blob(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _content(text: str) -> Dict[str, str]:
    return {"encoding": "base64", "content": base64.b64encode(text.encode("utf-8")).decode("ascii")}


class _FakeApi:
    """Routes by (method, path fragment) and records every request made."""

    def __init__(self, routes: List[Route]):
        self.routes = routes
        self.repository = REPO
        self.calls: List[Tuple[str, str, Optional[Dict[str, Any]]]] = []

    def request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None):
        self.calls.append((method, path, payload))
        for route_method, fragment, response in self.routes:
            if route_method == method and fragment in path:
                return response
        return 404, {"message": "no route"}

    def writes(self, method: str) -> List[Tuple[str, Optional[Dict[str, Any]]]]:
        return [(path, payload) for verb, path, payload in self.calls if verb == method]


def _listing_routes(ref: str, files: Dict[str, str]) -> List[Route]:
    listing = [
        {"type": "file", "name": path.rsplit("/", 1)[-1], "path": path, "sha": _blob(text)}
        for path, text in files.items()
    ]
    routes = [("GET", f"contents/.github/workflows?ref={ref}", (200, listing))]
    routes += [("GET", f"contents/{path}?ref={ref}", (200, _content(text))) for path, text in files.items()]
    return routes


def _api(pulls, ahead: int, head_files=None, base_files=None, issues=None) -> _FakeApi:
    """Routes 0-3: PR listing, compare, PR create, PR update. Routes 4-6: issue listing, create, update.

    The compare and the workflow listing read the trunk (SOURCE), not the release branch,
    which is deleted when the sync PR merges.
    """
    routes = [
        ("GET", "/pulls?", (200, pulls)),
        ("GET", f"compare/{BASE}...{SOURCE}", (200, {"ahead_by": ahead, "behind_by": 1})),
        ("POST", f"/repos/{REPO}/pulls", (201, {"number": 900})),
        ("PATCH", "/pulls/", (200, {})),
        ("GET", "/issues?", (200, issues or [])),
        ("POST", f"/repos/{REPO}/issues", (201, {"number": 700})),
        ("PATCH", "/issues/", (200, {})),
    ]
    routes += _listing_routes(SOURCE, head_files or {})
    routes += _listing_routes(BASE, base_files or {})
    return _FakeApi(routes)


def _run(rs, api: _FakeApi, dry_run: bool = False) -> int:
    return rs.run_sync(api, HEAD, BASE, dry_run, SOURCE)
