# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The symbol-fork ratchet's recorded per-service exceptions (#18688).

A cluster whose every binding is the canonical site or a recorded exception is
not a fork; any other binding keeps it. Each rule has a contrast pair, and the
record shrinks with the tree: a site that no longer exists is reported stale.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

sys.path.insert(0, str(repo_root() / "tools" / "lint"))

import check_symbol_forks as detector  # noqa: E402

_ISSUE = "https://github.com/mrveiss/AutoBot-AI/issues/18688"


def _tree(tmp_path: Path, monkeypatch, files: dict[str, str]) -> dict:
    for rel, src in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(src, encoding="utf-8")
    monkeypatch.setattr(detector, "_REPO_ROOT", tmp_path)
    return detector.find_clusters([Path(r) for r in files])[0]


def _entry(**over) -> dict:
    base = {
        "symbol": "gate",
        "canonical": "a.py:gate",
        "sites": ["b.py:gate"],
        "reason": "separate service",
        "issue": _ISSUE,
    }
    return {**base, **over}


_TWO = {"a.py": "def gate():\n    pass\n", "b.py": "def gate():\n    return 1\n"}


def test_a_cluster_fully_covered_by_exceptions_is_not_reported(tmp_path, monkeypatch) -> None:
    clusters = _tree(tmp_path, monkeypatch, _TWO)
    assert "gate" in clusters, "contrast: with no record the same tree IS a fork"
    effective, problems = detector.apply_exceptions(clusters, [_entry()])
    assert "gate" not in effective and problems == []


def test_an_unrecorded_third_binding_is_still_reported(tmp_path, monkeypatch) -> None:
    clusters = _tree(tmp_path, monkeypatch, {**_TWO, "c.py": "def gate():\n    return 2\n"})
    effective, problems = detector.apply_exceptions(clusters, [_entry()])
    assert "gate" in effective and problems == []


@pytest.mark.parametrize("missing", ["reason", "issue"])
def test_an_exception_missing_its_reason_or_issue_is_rejected(tmp_path, monkeypatch, missing) -> None:
    clusters = _tree(tmp_path, monkeypatch, _TWO)
    effective, problems = detector.apply_exceptions(clusters, [_entry(**{missing: ""})])
    assert "gate" in effective, "a rejected entry must not exempt anything"
    assert any(missing in p for p in problems)


def test_an_issue_that_is_not_a_link_is_rejected() -> None:
    assert detector.validate_exception(_entry(issue="soon")), "free text is not an issue link"
    assert detector.validate_exception(_entry(issue="#18688")) == []
    assert detector.validate_exception(_entry()) == []


@pytest.mark.parametrize(
    "bad",
    [{"sites": 7}, {"sites": "b.py:gate"}, {"sites": [{"path": "b.py"}]}, {"canonical": {"path": "a.py"}}],
    ids=["int-sites", "string-sites", "dict-in-sites", "dict-canonical"],
)
def test_a_malformed_sites_or_canonical_is_a_schema_error_not_a_crash(tmp_path, monkeypatch, bad) -> None:
    clusters = _tree(tmp_path, monkeypatch, _TWO)
    effective, problems = detector.apply_exceptions(clusters, [_entry(**bad)])
    assert "gate" in effective, "a rejected entry must not exempt anything"
    assert any("must be a" in p for p in problems) and not any("is not path:qualname" in p for p in problems)
    assert detector.validate_exception(_entry()) == [], "contrast: the well-formed entry is accepted"


def test_an_exception_whose_site_no_longer_exists_is_stale(tmp_path, monkeypatch) -> None:
    clusters = _tree(tmp_path, monkeypatch, _TWO)
    _, ok = detector.apply_exceptions(clusters, [_entry()])
    assert ok == [], "contrast: live sites are not stale"
    _, stale = detector.apply_exceptions(clusters, [_entry(sites=["b.py:gate", "gone.py:gate"])])
    assert len(stale) == 1 and "gone.py:gate" in stale[0] and "STALE" in stale[0]


def test_the_recorded_get_current_user_exceptions_hold_on_the_real_tree() -> None:
    raw = detector.find_clusters(detector.fork_scan_files())[0]
    assert "get_current_user" in raw, "contrast: the raw tree still has the cluster"
    effective, problems = detector.apply_exceptions(raw, detector.load_exceptions())
    assert problems == [] and "get_current_user" not in effective
