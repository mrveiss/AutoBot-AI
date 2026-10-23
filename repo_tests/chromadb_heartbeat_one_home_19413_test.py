# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""ChromaDB's heartbeat path has one home: ``CHROMADB_HEARTBEAT_PATH`` (#19413).

The pinned server is chromadb 1.x, which serves ``/api/v2/heartbeat`` only: the v1 heartbeat
answers 410 and ``/health`` 404. Two shell probes still called v1 and the ansible health check
called ``/health``, so they failed against a healthy server.

Python probes import the constant. Files that cannot import Python keep a copy recorded in
:data:`PINNED`; each copy must equal the home (owner ruling on #19343: a copy pinned by a failing
guard counts as derived). The sweep fails on

* any versioned heartbeat path other than the home's, anywhere in the tree, docs included;
* the home's literal in a code file outside the record;
* a ChromaDB probe of ``/health``.
"""

from __future__ import annotations

import functools
import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

from autobot_shared.chromadb_endpoints import CHROMADB_HEARTBEAT_PATH
from tools.lint._scan_helpers import tracked_paths

_ROOT = repo_root()
HOME = "autobot_shared/chromadb_endpoints.py"
#: This guard spells the forbidden path in its own fixtures.
SELF = "repo_tests/chromadb_heartbeat_one_home_19413_test.py"

#: Non-Python copies of the path: file -> the pattern capturing its value.
PINNED: dict[str, str] = {
    "autobot-slm-backend/ansible/inventory/group_vars/all.yml": r'^chromadb_heartbeat_path: "([^"]+)"',
    "autobot-infrastructure/autobot-database/templates/db-start.sh": r'^CHROMADB_HEARTBEAT_PATH="([^"]+)"',
    "autobot-infrastructure/autobot-database/templates/db-status.sh": r'^CHROMADB_HEARTBEAT_PATH="([^"]+)"',
    # At its frozen shell-size ceiling (#17353), so the probe line carries the copy itself.
    "autobot-infrastructure/shared/scripts/install-bare-metal.sh": r'CHROMADB_PORT\}(/api/v\d+/heartbeat)" ',
    "autobot-infrastructure/autobot-database/manifest.yml": r'endpoint: "http://localhost:\d+(/api/v\d+/heartbeat)"',
    "docker-compose.yml": r"printf 'GET (/api/v\d+/heartbeat) HTTP",
}

_RESOLVED_BY_19414 = "fixed in #19414's train; remove on rebase"

#: Live defects the sweep tolerates, each stale-checked: an entry whose file no longer shows
#: that finding fails :func:`test_every_pending_defect_is_still_present`, forcing it out.
PENDING_DEFECTS: dict[str, tuple[str, str]] = {
    "autobot-backend/onboarding/doctor.py": ("foreign", _RESOLVED_BY_19414),
    "autobot-backend/api/service_monitor.py": ("health", _RESOLVED_BY_19414),
}

#: Python files still restating the home's literal instead of importing it; #19423 removes them.
#: Stale-checked the same way: a file that no longer holds the literal must leave the record.
PYTHON_LITERALS_PENDING_19423 = frozenset(
    {
        "autobot-backend/api/monitoring.py",
        "autobot-slm-backend/services/role_registry.py",
    }
)

_VERSIONED = re.compile(r"/api/v\d+/heartbeat(?![\w-])")
_CHROMA_HEALTH = re.compile(r"(?i)chroma\w*\W.*/health\b|\b8100/health\b")
_NON_CODE = re.compile(r"(^docs/|\.md$|(^|/)tests?/|(^|/)test_[^/]*$|_test\.py$|\.test\.|^\.test_durations)")


def _strip_comment(line: str) -> str:
    """The code part of *line*: full-line ``#``/``//`` comments and trailing `` # `` comments go."""
    if line.lstrip().startswith(("#", "//")):
        return ""
    return re.split(r"\s#\s", line, maxsplit=1)[0]


def foreign_versions(text: str) -> list[str]:
    """Versioned heartbeat paths in *text* that are not the home's (comments included)."""
    return [m for m in _VERSIONED.findall(text) if m != CHROMADB_HEARTBEAT_PATH]


def chroma_health_probes(text: str) -> list[str]:
    """Code lines that send a ChromaDB probe to ``/health``, which chromadb 1.x does not serve."""
    lines = (_strip_comment(line) for line in text.splitlines())
    return [line.strip() for line in lines if _CHROMA_HEALTH.search(line)]


def _read(root: Path, rel: str) -> str | None:
    try:
        return (root / rel).read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
        return None


def _has_literal(text: str) -> bool:
    return any(_strip_comment(line).count(CHROMADB_HEARTBEAT_PATH) for line in text.splitlines())


def _findings_of(rel: str, text: str, allowed: set[str]) -> dict[str, list[str]]:
    """Every finding kind *text* (at *rel*) shows, before any pending-defect tolerance."""
    out: dict[str, list[str]] = {}
    if bad := foreign_versions(text):
        out["foreign"] = [f"{rel}: {bad}"]
    if _NON_CODE.search(rel) or rel.startswith("repo_tests/"):
        return out
    if rel not in allowed and _has_literal(text):
        out["unrecorded"] = [rel]
    if hits := chroma_health_probes(text):
        out["health"] = [f"{rel}: {hits}"]
    return out


def sweep(root: Path, paths: list[str]) -> dict[str, list[str]]:
    """``{finding kind: ["path: detail", ...]}`` over *paths* under *root*."""
    found: dict[str, list[str]] = {"foreign": [], "unrecorded": [], "health": []}
    allowed = {HOME, *PINNED, *PYTHON_LITERALS_PENDING_19423}
    for rel in paths:
        text = _read(root, rel)
        if text is None or rel == SELF:
            continue
        tolerated = PENDING_DEFECTS.get(rel, ("", ""))[0]
        for kind, items in _findings_of(rel, text, allowed).items():
            if kind != tolerated:
                found[kind].extend(items)
    return found


@functools.lru_cache(maxsize=1)
def _tree_findings() -> dict[str, list[str]]:
    return sweep(_ROOT, tracked_paths(_ROOT))


def test_the_home_is_the_v2_heartbeat_the_pinned_server_serves() -> None:
    # chromadb 1.5.9 server: chromadb/server/fastapi/__init__.py add_api_route("/api/v2/heartbeat", ...)
    assert CHROMADB_HEARTBEAT_PATH == "/api/v2/heartbeat"


def test_every_pinned_copy_equals_the_home() -> None:
    for path, pattern in PINNED.items():
        values = re.findall(pattern, (_ROOT / path).read_text(encoding="utf-8"), re.M)
        assert values == [CHROMADB_HEARTBEAT_PATH], f"#19413: {path} states {values}, home is the v2 heartbeat"


def test_every_pending_defect_is_still_present() -> None:
    """A fixed defect must leave the record, or the tolerance would hide its return."""
    stale = []
    for rel, (kind, _reason) in PENDING_DEFECTS.items():
        text = _read(_ROOT, rel) or ""
        if kind not in _findings_of(rel, text, set()):
            stale.append(f"{rel}: no {kind} finding")
    stale += [rel for rel in PYTHON_LITERALS_PENDING_19423 if not _has_literal(_read(_ROOT, rel) or "")]
    assert stale == [], f"#19413: stale pending entries {stale}; remove them from the record"


@pytest.mark.parametrize("kind", ["foreign", "unrecorded", "health"])
def test_the_tree_has_no_second_heartbeat_definition(kind: str) -> None:
    assert _tree_findings()[kind] == [], f"#19413: {kind} heartbeat probes; use {HOME} or a PINNED copy"


def test_a_v1_probe_a_re_added_copy_and_a_health_probe_are_caught(tmp_path: Path) -> None:
    (tmp_path / "x.sh").write_text('curl -s "http://127.0.0.1:8100/api/v1/heartbeat"\n', encoding="utf-8")
    (tmp_path / "y.py").write_text('url = f"http://{h}:{p}/api/v2/heartbeat"\n', encoding="utf-8")
    (tmp_path / "z.yml").write_text('    url: "http://127.0.0.1:8100/health"\n', encoding="utf-8")
    (tmp_path / "w.py").write_text('chromadb_url = f"http://{h}:{p}/health"  # ChromaDB\n', encoding="utf-8")
    found = sweep(tmp_path, ["x.sh", "y.py", "z.yml", "w.py"])
    assert [f.split(":")[0] for f in found["foreign"]] == ["x.sh"]
    assert found["unrecorded"] == ["y.py"]
    assert [f.split(":")[0] for f in found["health"]] == ["z.yml", "w.py"]


def test_prose_and_neighbours_are_not_findings(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "# probes /api/v2/heartbeat on ChromaDB\nurl = '/api/v1/heartbeats'\nai_url = f'{a}/health'\n",
        encoding="utf-8",
    )
    assert sweep(tmp_path, ["a.py"]) == {"foreign": [], "unrecorded": [], "health": []}
