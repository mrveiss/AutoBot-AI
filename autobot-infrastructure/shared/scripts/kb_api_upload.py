#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ONE uploader that adds documents to a running backend's knowledge base (#19339).

``simple_populate.py`` and ``search_index_utility.py`` each carried a copy of this -- the same
``add_text`` POST, thread pool and result type, one with a hardcoded backend port, one with
``ServiceURLs.BACKEND_LOCAL`` (also ``localhost``) -- and ``upload_docs.py`` was a third (multipart
``add_file``). All now post to the SSOT ``config.backend_url``. They now call :func:`upload_docs`; the in-process route (no
backend running) is ``populate_knowledge_base.py``.
"""

import asyncio
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Optional

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autobot_shared.http_egress_guard import assert_egress_policy  # noqa: E402
from autobot_shared.ssot_config import config  # noqa: E402

#: The SSOT backend URL -- the same one the egress allowlist trusts as an internal origin.
API_URL = config.backend_url
ADD_TEXT_TIMEOUT_S = 10


@dataclass
class UploadResult:
    """Result of adding one document."""

    rel_path: str
    success: bool
    error: Optional[str] = None


#: Builds the stored text from (relative path, file path, content).
Render = Callable[[str, str, str], str]


def _as_is(rel_path: str, file_path: str, content: str) -> str:
    return content


def upload_doc(file_path: str, root: str, title_prefix: str, render: Render = _as_is) -> UploadResult:
    """POST one file's text to the backend's ``add_text`` endpoint."""
    rel_path = os.path.relpath(file_path, root)
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        if not content.strip():
            return UploadResult(rel_path=rel_path, success=False, error="Empty file")
        data = {
            "text": render(rel_path, file_path, content),
            "title": f"{title_prefix}: {rel_path}",
            "source": "project-documentation",
        }
        url = f"{API_URL}/api/knowledge_base/add_text"
        asyncio.run(assert_egress_policy(url))  # rule 8: the backend is an internal origin, so this passes
        resp = requests.post(url, json=data, timeout=ADD_TEXT_TIMEOUT_S, allow_redirects=False)
        if resp.status_code == 200:
            return UploadResult(rel_path=rel_path, success=True)
        return UploadResult(rel_path=rel_path, success=False, error=resp.text)
    except Exception as e:
        return UploadResult(rel_path=rel_path, success=False, error=str(e))


def upload_docs(
    files: list, root: str, title_prefix: str, render: Render = _as_is, max_workers: int = 5
) -> list[UploadResult]:
    """Upload *files* concurrently; one :class:`UploadResult` per file."""
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(upload_doc, f, root, title_prefix, render) for f in files]
        return [future.result() for future in as_completed(futures)]
