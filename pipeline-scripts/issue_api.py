# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one issue-side client for the pipeline scripts that read and write issue comments (#19522).

``landing_notes.py`` (#19520) and ``issue_structure.py`` (#19522) each grew the same pieces:
a loader for the shared comment helper, a client wrapping ``GitHubApi.request`` with the
helper's comment reader and upsert, and a create-if-absent label step. They live here once.

``.github/actions/upsert-pr-comment/upsert_pr_comment.py`` cannot be imported by name (its
directory has a hyphen), so ``load_upsert()`` loads it by path, once per process. Stdlib only.
"""

from __future__ import annotations

import functools
import importlib.util
import urllib.parse
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, List, Optional

UPSERT_PATH = Path(__file__).resolve().parent.parent / ".github/actions/upsert-pr-comment/upsert_pr_comment.py"
_MODULE_NAME = "_upsert_pr_comment_pipeline"


@functools.lru_cache(maxsize=1)
def load_upsert() -> ModuleType:
    """The one comment reader and bot-marker rule (#12984), shared by every caller."""
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, UPSERT_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {UPSERT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class IssueApiError(RuntimeError):
    """The API answered with something the calling script cannot act on."""


class IssueClient:
    """`GitHubApi.request` plus the one comment reader and upsert (#12984).

    A caller subclasses it to set ``error``, its own ``IssueApiError`` subclass. Tests pass a
    fake ``api`` and, for the comment helper, fake ``comments``/``upsert`` callables.
    """

    error = IssueApiError

    def __init__(
        self,
        api: Any,
        comments: Optional[Callable[[int], List[Dict[str, Any]]]] = None,
        upsert: Optional[Callable[[int, str, str], Any]] = None,
    ) -> None:
        self.api = api
        self.repo = api.repository
        self._comments = comments
        self._upsert = upsert

    def call(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None, ok=(200,)) -> Any:
        status, body = self.api.request(method, path, payload)
        if status not in ok:
            raise self.error(f"{method} {path}: HTTP {status}: {body}")
        return body

    def comments(self, number: int) -> List[Dict[str, Any]]:
        if self._comments is not None:
            return self._comments(number)
        return list(load_upsert().iter_comments(self.api.api_root, self.repo, number, self.api.token))

    def upsert(self, number: int, marker: str, body: str) -> Any:
        """Update our newest ``marker`` comment, else create one: the shared helper, never a copy."""
        if self._upsert is not None:
            return self._upsert(number, marker, body)
        return load_upsert().upsert(self.api.api_root, self.repo, number, self.api.token, marker, body)


def ensure_label(client: IssueClient, name: str, color: str, description: str) -> None:
    """Create the label when the repository lacks it; a concurrent create (422) is fine."""
    status, _ = client.api.request("GET", f"/repos/{client.repo}/labels/{urllib.parse.quote(name)}", None)
    if status == 404:
        payload = {"name": name, "color": color, "description": description}
        client.call("POST", f"/repos/{client.repo}/labels", payload, ok=(201, 422))
    elif status != 200:
        raise client.error(f"cannot read label {name}: HTTP {status}")
