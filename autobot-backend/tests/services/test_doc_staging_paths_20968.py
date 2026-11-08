# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The docs sync's `.~tmp~` staging paths are not documentation and are never enqueued (#20968)."""

import pytest

from autobot_shared.kb_doc_set import in_doc_set
from services import documentation_watcher as dw


class _Watcher:
    def __init__(self) -> None:
        self.dispatched: list[tuple[str, str]] = []

    def dispatch_change(self, path, change_type):
        self.dispatched.append((str(path), change_type))
        return object()


@pytest.mark.parametrize(
    "path",
    [
        "docs/adr/.~tmp~/template.md",
        "docs/.~tmp~/_index.md",
        "docs/a/.hidden/b.md",
        ".github/README.md",
        "docs/.draft.md",
    ],
)
def test_hidden_and_staging_paths_are_not_in_the_set(path: str) -> None:
    assert not in_doc_set(path)


@pytest.mark.parametrize("path", ["docs/adr/0001.md", "docs/v1.2/guide.md", "README.md"])
def test_ordinary_docs_stay_in_the_set(path: str) -> None:
    assert in_doc_set(path)


@pytest.mark.parametrize("change", ["created", "modified"])
def test_a_staging_event_enqueues_nothing_and_a_real_one_does(change: str) -> None:
    watcher = _Watcher()
    handler = dw.DocumentationChangeHandler(watcher)
    handler._handle_change(str(dw.PROJECT_ROOT / "docs/adr/.~tmp~/template.md"), change)
    assert watcher.dispatched == []
    handler._handle_change(str(dw.PROJECT_ROOT / "docs/adr/0001-real.md"), change)
    assert len(watcher.dispatched) == 1
