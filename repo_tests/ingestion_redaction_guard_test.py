# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard: every KB ingestion entry point redacts credentials before content
reaches the indexer/embedder (#13708 review).

A prior review of #13708 found the redactor wired into `content_extraction.py`
(used by the DOCX branch of the gdrive/onedrive connectors) but NOT into the
PDF and .md/.txt branches of those same connectors, nor into
`api/knowledge.py`'s separate manual-upload extraction path -- three real
ingestion entry points a credential in a synced or uploaded document could
reach the KB unmasked through.

This is a fixed, hand-enumerated allowlist rather than a tree-scanning guard:
"extracts external content and returns it for indexing" is not a discoverable
syntactic pattern the way a route decorator or an import statement is, so
`repo_tests._reach`'s tree-scanning machinery (built for guards that walk many
files and need a floor proving they didn't silently stop reaching the tree)
doesn't fit here -- see PR #16939's review, where a guard that DID need it was
shipped without one. Each entry point is named explicitly instead; adding a
new one silently is exactly what this guard cannot catch, which is why the
negative control below proves the detection logic itself, not just this list.
"""

from __future__ import annotations

import importlib
import inspect

import pytest

_ENTRY_POINTS = [
    ("knowledge.connectors.gdrive", "GoogleDriveConnector.fetch_content"),
    ("knowledge.connectors.onedrive", "OneDriveConnector.fetch_content"),
    ("api.knowledge", "upload_file_to_knowledge"),
]


def _calls_redact_content(source: str) -> bool:
    """True if *source* contains an actual call to redact_content(...).

    Checked against the function's own source, not the module's imports, so an
    entry point that imports the redactor but never calls it still fails.
    """
    return "redact_content(" in source


def _resolve(module_path: str, qualname: str):
    obj = importlib.import_module(module_path)
    for part in qualname.split("."):
        obj = getattr(obj, part)
    return obj


@pytest.mark.parametrize("module_path,qualname", _ENTRY_POINTS, ids=[f"{m}.{q}" for m, q in _ENTRY_POINTS])
def test_ingestion_entry_point_redacts_credentials(module_path: str, qualname: str) -> None:
    func = _resolve(module_path, qualname)
    source = inspect.getsource(func)
    assert _calls_redact_content(source), (
        f"{module_path}.{qualname} extracts external content but its source has no "
        "redact_content(...) call -- a credential in this content would reach the "
        "indexer/embedder unmasked (#13708)."
    )


def test_negative_control_a_function_that_skips_redaction_is_caught() -> None:
    """Proves the assertion above can fail, not just always pass.

    Without this, a guard whose detection helper is broken (e.g. checking the
    wrong string, or matching the import instead of a call) would report green
    against every real entry point without ever having demonstrated it can see
    a violation -- the exact "did not look" failure MEASUREMENT_DISCIPLINE.md
    warns about.
    """

    def _fake_entry_point_that_forgets_to_redact(content_bytes: bytes) -> str:
        text = content_bytes.decode("utf-8")
        return text

    source = inspect.getsource(_fake_entry_point_that_forgets_to_redact)
    assert not _calls_redact_content(source), "negative control itself contains a redact_content(...) call"
