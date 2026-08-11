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

    def test_the_file_cap_is_a_real_number(self):
        from code_analysis.src.ownership_analyzer import _MAX_FILES_TO_BLAME

        assert isinstance(_MAX_FILES_TO_BLAME, int) and _MAX_FILES_TO_BLAME > 0
