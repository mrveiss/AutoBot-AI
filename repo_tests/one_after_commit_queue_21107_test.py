# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One after-commit queue: ``defer_until_commit`` owns the hook pair (#21107).

Event wakes and activity publish each carried a copy of the queue in ``llc/services/after_commit.py``
(queue on ``session.info``, ``after_commit`` runs it, a rollback drops it). Two copies disagree about
SAVEPOINTs and rollbacks, so the hook has one home. The guard fails on an ``event.listen`` /
``listens_for`` of ``"after_commit"`` in non-test backend code outside that home.

``FROZEN`` names the sites that were not migrated, each with the reason; the set only shrinks.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

HOME = "autobot-backend/llc/services/after_commit.py"
#: A listener registration that names the after_commit event, on one line or the next two.
_LISTENER = re.compile(r"""(?:event\.listen|listens_for)\(\s*[^)]*?["']after_commit["']""", re.S)
_TEST_MARKERS = ("_test.py", "/tests/", "/test_", "conftest.py")
#: Floor on files examined: a pathspec that stops matching must not read as a clean tree.
_MIN_EXAMINED = 500

FROZEN: dict[str, str] = {
    "autobot-backend/llc/services/goal.py": "once=True post-commit KB indexing hook with no rollback handling (#21107 follow-up)",
    "autobot-backend/user_management/services/person_copy_sync.py": "process-wide listener on the Session class, not a per-session queue",
}


def _is_test(path: str) -> bool:
    return any(marker in path or path.startswith(marker.lstrip("/")) for marker in _TEST_MARKERS)


def listeners_in(text: str) -> int:
    return len(_LISTENER.findall(text))


def sweep(root: Path, paths: list[str]) -> dict[str, int]:
    found: dict[str, int] = {}
    for rel in paths:
        count = listeners_in((root / rel).read_text(encoding="utf-8", errors="replace"))
        if count:
            found[rel] = count
    return found


def _backend_sources() -> list[str]:
    paths = tracked_paths(repo_root(), "autobot-backend/*.py")
    return [p for p in paths if not _is_test(p)]


def test_control_string_is_caught() -> None:
    assert listeners_in('event.listen(sync, "after_commit", cb)') == 1
    assert listeners_in('@event.listens_for(sess, "after_commit", once=True)') == 1
    assert listeners_in('event.listen(sync, "after_soft_rollback", cb)') == 0


def test_control_planted_site_fails(tmp_path: Path) -> None:
    (tmp_path / "planted.py").write_text('event.listen(s, "after_commit", cb)\n', encoding="utf-8")
    assert sweep(tmp_path, ["planted.py"]) == {"planted.py": 1}


def test_sweep_examined_the_backend() -> None:
    assert len(_backend_sources()) >= _MIN_EXAMINED


def test_home_registers_the_hook() -> None:
    assert HOME in sweep(repo_root(), [HOME])


def test_no_second_after_commit_queue() -> None:
    found = set(sweep(repo_root(), _backend_sources())) - {HOME}
    assert found == set(FROZEN), f"after_commit listeners outside {HOME}: {sorted(found ^ set(FROZEN))}"
