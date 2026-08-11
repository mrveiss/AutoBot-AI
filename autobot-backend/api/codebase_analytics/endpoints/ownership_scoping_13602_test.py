# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Ownership endpoints must scope to the source they were asked about (#13602).

Three sibling endpoints, three different ways of getting this wrong:

`/ownership/analysis` resolved the source's clone path correctly and then
validated against `_get_project_root()` instead — the root it had just replaced.
A clone path lives under `data/code-sources/<id>` while the project root
resolves to the checkout; sibling subtrees that never nest, so the containment
check rejected EVERY source-scoped request with 400 "Invalid path: must be
within project root". Deterministic, not layout-dependent.

`/ownership/expertise` and `/ownership/knowledge-gaps` accepted `source_id`
"for API consistency" and ignored it, silently analysing AutoBot's own tree for
every source — cross-project leakage rather than a visible 400, and the worse
failure of the two because it returns plausible data.

The rejection was also logged as `"Path traversal attempt blocked"`, so ordinary
use filled the security log with false attack alerts and echoed the internal
clone path while doing it.

This file is the endpoint's first test coverage.
"""

from __future__ import annotations

import logging

import pytest

import api.codebase_analytics.endpoints.ownership as own_mod


@pytest.fixture
def two_roots(tmp_path):
    """A source clone and an AutoBot root that are siblings — never nested,
    which is the real deployed relationship."""
    project_root = tmp_path / "code_source"
    clone = tmp_path / "data" / "code-sources" / "abc123"
    project_root.mkdir(parents=True)
    clone.mkdir(parents=True)
    return project_root, clone


class TestValidationUsesTheResolvedScanRoot:
    @pytest.mark.asyncio
    async def test_a_source_scoped_request_is_not_rejected_as_out_of_root(self, monkeypatch, two_roots):
        project_root, clone = two_roots
        captured: dict[str, str] = {}

        def _capture(path, root):
            captured["path"] = path
            captured["root"] = root
            return None

        async def _resolve(source_id, use_default=True):
            return clone

        monkeypatch.setattr(own_mod, "_get_project_root", lambda: str(project_root))
        monkeypatch.setattr(own_mod, "resolve_scan_root", _resolve)
        monkeypatch.setattr(own_mod, "_validate_path_security", _capture)
        monkeypatch.setattr(own_mod, "_check_ownership_cache", _none_cache)
        monkeypatch.setattr(own_mod, "_get_ownership_analyzer", lambda: None)

        await own_mod.get_ownership_analysis(
            path=None,
            refresh=False,
            patterns="**/*.py",
            days=90,
            source_id="abc123",
        )

        assert captured["root"] == str(clone), "containment must be checked against the source's own root"
        assert captured["root"] != str(project_root), "validating against AutoBot's root rejects every source"
        assert captured["path"] == str(clone)


class TestSiblingEndpointsAreScopedToo:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("endpoint", ["get_expertise_scores", "get_knowledge_gaps"])
    async def test_source_id_is_not_ignored(self, monkeypatch, two_roots, endpoint):
        """These returned AutoBot's own ownership data for every source — a
        wrong answer rather than an error, which is why it went unnoticed."""
        project_root, clone = two_roots
        captured: dict[str, str] = {}

        async def _resolve(source_id, use_default=True):
            assert source_id == "abc123", "the requested source must reach the resolver"
            return clone

        monkeypatch.setattr(own_mod, "_get_project_root", lambda: str(project_root))
        monkeypatch.setattr(own_mod, "resolve_scan_root", _resolve)
        monkeypatch.setattr(own_mod, "_validate_path_security", lambda p, r: captured.update(root=r))
        monkeypatch.setattr(own_mod, "_get_ownership_analyzer", lambda: None)
        monkeypatch.setattr(own_mod, "_check_ownership_cache", _none_cache)

        kwargs = {"path": None, "source_id": "abc123"}
        if endpoint == "get_knowledge_gaps":
            kwargs["risk_level"] = None
        await getattr(own_mod, endpoint)(**kwargs)

        assert captured["root"] == str(clone), f"{endpoint} analysed the wrong project"


class TestOrdinaryUseIsNotLoggedAsAnAttack:
    def test_a_scope_mismatch_is_not_a_traversal_attempt(self, caplog, two_roots):
        project_root, clone = two_roots
        with caplog.at_level(logging.INFO):
            response = own_mod._validate_path_security(str(clone), str(project_root))

        assert response is not None, "the path is still rejected"
        messages = " ".join(r.message for r in caplog.records)
        assert "traversal attempt" not in messages, "ordinary use must not read as an attack"

    def test_a_real_escape_is_still_logged_as_an_attack(self, caplog, two_roots):
        """The case that must stay caught. A test asserting only that the false
        alert is gone passes equally against a detector that says nothing."""
        project_root, _clone = two_roots
        escape = str(project_root / ".." / ".." / "etc" / "passwd")

        with caplog.at_level(logging.INFO):
            response = own_mod._validate_path_security(escape, str(project_root))

        assert response is not None
        messages = " ".join(r.message for r in caplog.records)
        assert "traversal attempt" in messages, "a genuine escape must still raise an attack-shaped warning"

    def test_the_internal_path_is_not_echoed(self, caplog, two_roots):
        """The warning printed the clone path into the log. Internal filesystem
        paths do not belong in outward-facing records."""
        project_root, clone = two_roots
        with caplog.at_level(logging.INFO):
            own_mod._validate_path_security(str(clone), str(project_root))

        assert str(clone) not in " ".join(r.message % r.args if r.args else r.message for r in caplog.records)


class TestEscapeDiscriminator:
    @pytest.mark.parametrize(
        "relative,escapes",
        [
            ("pkg/mod.py", False),
            (".", False),
            ("../../etc/passwd", True),
            ("../sibling/file.py", True),
        ],
    )
    def test_only_paths_that_climb_out_count_as_escapes(self, tmp_path, relative, escapes):
        root = tmp_path / "root"
        root.mkdir()
        assert own_mod._escapes_root(str(root / relative), str(root)) is escapes

    def test_a_different_absolute_root_is_a_mismatch_not_an_escape(self, two_roots):
        project_root, clone = two_roots
        assert own_mod._escapes_root(str(clone), str(project_root)) is False


async def _none_cache(*_args, **_kwargs):
    return None


class TestOwnershipAnalyzerIsBounded:
    """Fixing the 400 makes this panel reachable for the first time. Reachable
    and unbounded would trade a visible error for a silent hang, which is a
    worse outcome than the bug being fixed."""

    def test_worktrees_are_skipped(self, tmp_path):
        from code_analysis.src.ownership_analyzer import OwnershipAnalyzer

        analyzer = OwnershipAnalyzer.__new__(OwnershipAnalyzer)
        assert analyzer._should_skip_file(tmp_path / ".worktrees" / "wt" / "a.py")
        assert analyzer._should_skip_file(tmp_path / ".claude" / "worktrees" / "wt" / "a.py")
        assert not analyzer._should_skip_file(tmp_path / "pkg" / "a.py")

    @pytest.mark.asyncio
    async def test_blame_does_not_run_on_the_event_loop(self, monkeypatch, tmp_path):
        """A sync subprocess inside `async def` blocks every other request for
        its full duration — up to 30s, once per file."""
        import asyncio

        import code_analysis.src.ownership_analyzer as oa

        ran_in_thread: dict[str, bool] = {}
        loop_thread = __import__("threading").current_thread().ident

        def _fake_run(*_args, **_kwargs):
            ran_in_thread["off_loop"] = __import__("threading").current_thread().ident != loop_thread

            class _R:
                returncode = 1
                stdout = ""

            return _R()

        monkeypatch.setattr(oa.subprocess, "run", _fake_run)
        analyzer = oa.OwnershipAnalyzer.__new__(oa.OwnershipAnalyzer)
        target = tmp_path / "a.py"
        target.write_text("x = 1\n", encoding="utf-8")

        await asyncio.wait_for(analyzer._get_file_ownership(target, tmp_path), timeout=10)

        assert ran_in_thread.get("off_loop"), "git blame must not run on the event loop"

    @pytest.mark.asyncio
    async def test_the_file_cap_actually_stops_the_walk(self, monkeypatch, tmp_path):
        """The first version of this asserted `isinstance(int) and > 0`, which
        cannot fail for any positive integer — a guard that proves nothing about
        the line it names. Exercise the cap instead."""
        import code_analysis.src.ownership_analyzer as oa

        for i in range(12):
            (tmp_path / f"f{i}.py").write_text("x = 1\n", encoding="utf-8")

        blamed: list[str] = []

        async def _fake_ownership(self, file_path, root):
            blamed.append(file_path.name)
            return None

        monkeypatch.setattr(oa, "_MAX_FILES_TO_BLAME", 4)
        monkeypatch.setattr(oa.OwnershipAnalyzer, "_get_file_ownership", _fake_ownership)
        analyzer = oa.OwnershipAnalyzer.__new__(oa.OwnershipAnalyzer)

        await analyzer._analyze_file_ownership(str(tmp_path), ["**/*.py"])

        assert len(blamed) == 4, f"the cap did not stop the walk: blamed {len(blamed)} files"
        assert analyzer._truncated_reason, "truncation must be recorded"

    @pytest.mark.asyncio
    async def test_the_time_budget_stops_a_slow_walk(self, monkeypatch, tmp_path):
        """A file cap alone is the wrong bound: at the measured ~0.45s per
        `git blame`, 2000 files is a 15-minute request. Wall clock is what the
        caller experiences."""
        import code_analysis.src.ownership_analyzer as oa

        for i in range(30):
            (tmp_path / f"f{i}.py").write_text("x = 1\n", encoding="utf-8")

        blamed: list[str] = []
        clock = {"t": 0.0}

        async def _slow(self, file_path, root):
            blamed.append(file_path.name)
            clock["t"] += 1.0
            return None

        monkeypatch.setattr(oa.time, "monotonic", lambda: clock["t"])
        monkeypatch.setattr(oa, "_MAX_BLAME_SECONDS", 5.0)
        monkeypatch.setattr(oa, "_MAX_FILES_TO_BLAME", 10_000)
        monkeypatch.setattr(oa.OwnershipAnalyzer, "_get_file_ownership", _slow)
        analyzer = oa.OwnershipAnalyzer.__new__(oa.OwnershipAnalyzer)

        await analyzer._analyze_file_ownership(str(tmp_path), ["**/*.py"])

        assert len(blamed) <= 7, f"the time budget did not stop the walk: {len(blamed)} files"
        assert "time budget" in (analyzer._truncated_reason or "")

    @pytest.mark.asyncio
    async def test_one_budget_covers_all_patterns(self, monkeypatch, tmp_path):
        """Breaking only the inner loop would give every later pattern a fresh
        budget, which is not a budget."""
        import code_analysis.src.ownership_analyzer as oa

        for ext in ("py", "ts", "vue"):
            for i in range(6):
                (tmp_path / f"f{i}.{ext}").write_text("x = 1\n", encoding="utf-8")

        blamed: list[str] = []

        async def _fake(self, file_path, root):
            blamed.append(file_path.name)
            return None

        monkeypatch.setattr(oa, "_MAX_FILES_TO_BLAME", 3)
        monkeypatch.setattr(oa.OwnershipAnalyzer, "_get_file_ownership", _fake)
        analyzer = oa.OwnershipAnalyzer.__new__(oa.OwnershipAnalyzer)

        await analyzer._analyze_file_ownership(str(tmp_path), ["**/*.py", "**/*.ts", "**/*.vue"])

        assert len(blamed) == 3, f"each pattern got its own budget: {len(blamed)} files blamed"

    def test_a_truncated_result_says_so_to_the_caller(self, tmp_path):
        """Server-side logging is not enough — the caller is the one drawing
        conclusions from these numbers."""
        import code_analysis.src.ownership_analyzer as oa

        analyzer = oa.OwnershipAnalyzer.__new__(oa.OwnershipAnalyzer)
        analyzer._truncated_reason = "file cap (2000)"
        result = analyzer._build_ownership_results([], [], [], [], {}, 0.1)

        assert result["summary"]["truncated"] is True
        assert "2000" in result["summary"]["truncated_reason"]

    def test_a_complete_result_is_not_flagged(self, tmp_path):
        """The direction that must stay true — a flag that is always set carries
        no information."""
        import code_analysis.src.ownership_analyzer as oa

        analyzer = oa.OwnershipAnalyzer.__new__(oa.OwnershipAnalyzer)
        analyzer._truncated_reason = None
        result = analyzer._build_ownership_results([], [], [], [], {}, 0.1)

        assert result["summary"]["truncated"] is False

    def test_the_bounds_are_set_to_values_that_actually_bound(self):
        """The behavioural tests above monkeypatch these, so they prove the
        mechanism works without noticing if the shipped constant were raised to
        something that never fires. Measured: `git blame --line-porcelain` runs
        at a median 0.45s per file on this repo, so the file cap alone allows a
        ~15 minute request — which is why the wall-clock budget is the real
        bound and has to stay small enough to matter."""
        from code_analysis.src.ownership_analyzer import _MAX_BLAME_SECONDS, _MAX_FILES_TO_BLAME

        assert 0 < _MAX_FILES_TO_BLAME <= 10_000, "a cap this high is not a cap"
        assert 0 < _MAX_BLAME_SECONDS <= 60, "a budget longer than a client timeout bounds nothing"

    def test_a_scan_rooted_in_a_worktree_still_sees_its_own_files(self, tmp_path):
        """The trap I walked into: `.worktrees` was added to _SKIP_DIRECTORIES,
        a SECOND skip list that still matched the absolute path. Since
        resolve_project_root() lands inside a worktree on any dev checkout, the
        endpoint returned 200 with zero contributors and no error — a loud 400
        replaced by a silent empty success."""
        from code_analysis.src.ownership_analyzer import OwnershipAnalyzer

        root = tmp_path / ".worktrees" / "issue-13602"
        (root / "pkg").mkdir(parents=True)
        analyzer = OwnershipAnalyzer.__new__(OwnershipAnalyzer)

        assert not analyzer._should_skip_file(root / "pkg" / "real.py", root)
        assert analyzer._should_skip_file(root / ".worktrees" / "nested" / "x.py", root)
        assert analyzer._should_skip_file(root / "node_modules" / "y.py", root)
