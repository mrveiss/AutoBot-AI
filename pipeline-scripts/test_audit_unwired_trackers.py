#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for pipeline-scripts/audit_unwired_trackers.py (#6929).

Covers the surfaces flagged in #6927 (SCAN_DIRS gap), #6928 (regex gap),
and #6929 (no tests). The script is the Tier-3 cron defense for the
#6836 closure-gate process — silent regressions in its regex / scan /
dedup paths erode the entire defense, so these tests pin the contract.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

import audit_unwired_trackers as audit

# ---------------------------------------------------------------------------
# extract_tracker_refs / ISSUE_REF_RE — #6928 regex coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "doctext,expected",
    [
        # Original 4 shapes (must keep working).
        ('"""Issue #1234: foo."""', [1234]),
        ('"""Topology-Aware Router (#2138)."""', [2138]),
        ("# #5678: heading style\n", [5678]),
        ("See https://github.com/x/y/issues/9999\n", [9999]),
        # New shapes added by #6928.
        ('"""Closes #4321."""', [4321]),
        ('"""Fixes #1111 and Resolves #2222."""', [1111, 2222]),
        ("# Related #3456 and Tracking #7890.\n", [3456, 7890]),
        ("See [#5555](https://github.com/x/y/issues/5555) for details.\n", [5555]),
        # Multiple in same docstring — order preserved, deduped.
        ('"""Issue #100 — Closes #100 (dup) and Fixes #200."""', [100, 200]),
        # Mixed case isn't matched (`closes` lower would not be the convention).
        ('"""closes #999 lowercase."""', []),
    ],
)
def test_extract_tracker_refs_shapes(tmp_path: Path, doctext: str, expected: list[int]) -> None:
    f = tmp_path / "sample.py"
    f.write_text(doctext, encoding="utf-8")
    assert audit.extract_tracker_refs(f) == expected


def test_extract_tracker_refs_only_first_40_lines(tmp_path: Path) -> None:
    """Refs deeper than DOCSTRING_HEAD_LINES are intentionally ignored —
    the audit is a docstring-citation check, not a full-file scan."""
    f = tmp_path / "deep.py"
    f.write_text("\n" * 100 + "Issue #4242", encoding="utf-8")
    assert audit.extract_tracker_refs(f) == []


def test_extract_tracker_refs_unreadable_file(tmp_path: Path) -> None:
    """OSError / UnicodeDecodeError must return [] not crash the audit."""
    f = tmp_path / "binary.py"
    f.write_bytes(b"\x80\x81\x82\xfe\xff\x00")
    assert audit.extract_tracker_refs(f) == []


# ---------------------------------------------------------------------------
# is_test_path / should_skip_path — boundary cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,is_test",
    [
        (Path("autobot-backend/foo_test.py"), True),
        (Path("autobot-backend/foo.test.ts"), True),
        (Path("autobot-backend/tests/test_foo.py"), True),
        (Path("autobot-frontend/src/__tests__/Foo.spec.ts"), True),
        # #7128: pytest test_*.py PREFIX style — these are pytest modules in
        # production directories, not unwired production code. Previously
        # leaked into the audit's findings (7 of 252 in the 2026-05-06 run).
        (Path("autobot-backend/agent_loop/test_loop_repetition.py"), True),
        (Path("autobot-backend/knowledge/test_rag_benchmarks.py"), True),
        (Path("autobot-backend/knowledge/backends/test_async_base.py"), True),
        (Path("autobot-backend/foo.py"), False),
        # Edge: 'test' in a non-test segment shouldn't match
        (Path("autobot-backend/contestant.py"), False),
        # Edge: 'testfile.py' without underscore shouldn't match
        (Path("autobot-backend/testfile.py"), False),
    ],
)
def test_is_test_path(path: Path, is_test: bool) -> None:
    assert audit.is_test_path(path) is is_test


@pytest.mark.parametrize(
    "rel,should_skip",
    [
        # Fragments require a leading separator — the audit's intent is to
        # skip paths that *contain* these as directory segments, never as
        # filename prefixes (e.g. a real "build_*.py" production file).
        ("autobot-backend/__pycache__/foo.cpython-310.pyc", True),
        ("autobot-frontend/node_modules/x/index.ts", True),
        (".worktrees/issue-1234/foo.py", True),
        ("autobot-backend/dist/bundle.js", True),
        ("autobot-backend/build/out.js", True),
        ("autobot-backend/migrations/0001_init.py", True),
        ("autobot-backend/foo.py", False),
    ],
)
def test_should_skip_path(rel: str, should_skip: bool) -> None:
    """Paths are checked relative to REPO_ROOT (#7128b: previously absolute,
    which caused false-positives when the audit ran from inside a worktree)."""
    p = audit.REPO_ROOT / rel
    assert audit.should_skip_path(p) is should_skip


def test_should_skip_path_handles_running_from_worktree() -> None:
    """Regression: when REPO_ROOT itself contains `.worktrees/`, files INSIDE
    that REPO_ROOT must NOT be auto-skipped (#7128b)."""
    # Simulate: REPO_ROOT = /home/foo/repo/.worktrees/issue-X
    # File:    /home/foo/repo/.worktrees/issue-X/autobot-backend/auth_rbac.py
    # Should NOT be skipped — the .worktrees/ in REPO_ROOT itself is irrelevant.
    fake_root = Path("/home/foo/repo/.worktrees/issue-X")
    p = fake_root / "autobot-backend" / "auth_rbac.py"
    with patch.object(audit, "REPO_ROOT", fake_root):
        assert audit.should_skip_path(p) is False
    # But a *nested* worktree under that fake_root should still be skipped:
    nested = fake_root / ".worktrees" / "issue-Y" / "autobot-backend" / "x.py"
    with patch.object(audit, "REPO_ROOT", fake_root):
        assert audit.should_skip_path(nested) is True


# ---------------------------------------------------------------------------
# SCAN_DIRS — #6927 expansion
# ---------------------------------------------------------------------------


def test_scan_dirs_includes_slm_and_infrastructure() -> None:
    """#6927: ensure the historically-skipped backends are now scanned."""
    assert "autobot-slm-backend" in audit.SCAN_DIRS
    assert "autobot-infrastructure" in audit.SCAN_DIRS
    assert "autobot-npu-worker" in audit.SCAN_DIRS


# ---------------------------------------------------------------------------
# grep_count_production_callers — ambiguous-stem skip + dedup
# ---------------------------------------------------------------------------


def test_grep_count_skips_ambiguous_stem(tmp_path: Path) -> None:
    """Module names like `utils`, `__init__`, `types` are too noisy to grep
    reliably — must short-circuit to -1 (skip) before invoking grep."""
    fake_self = tmp_path / "utils.py"
    fake_self.write_text("", encoding="utf-8")
    assert audit.grep_count_production_callers("utils", fake_self) == -1
    assert audit.grep_count_production_callers("__init__", fake_self) == -1
    assert audit.grep_count_production_callers("types", fake_self) == -1


def test_grep_count_excludes_self_and_test_paths() -> None:
    """The grep result must not count the module's own file or test files."""
    fake_stdout = (
        f"{audit.REPO_ROOT}/autobot-backend/foo.py:10:from foo import bar\n"  # self
        f"{audit.REPO_ROOT}/autobot-backend/foo_test.py:5:from foo import bar\n"  # test
        f"{audit.REPO_ROOT}/autobot-backend/tests/test_foo.py:5:from foo import bar\n"  # test
        f"{audit.REPO_ROOT}/autobot-backend/__pycache__/foo.cpython-310.pyc:0:cached\n"  # pyc
        f"{audit.REPO_ROOT}/autobot-backend/real_caller.py:42:from foo import bar\n"  # real
    )
    fake_run = MagicMock(returncode=0, stdout=fake_stdout, stderr="")
    self_path = audit.REPO_ROOT / "autobot-backend/foo.py"
    with patch.object(audit.subprocess, "run", return_value=fake_run):
        assert audit.grep_count_production_callers("foo", self_path) == 1


def test_grep_count_handles_grep_error() -> None:
    """grep returncode > 1 means an error — return -1 (skip) not 0."""
    fake_run = MagicMock(returncode=2, stdout="", stderr="grep: I/O error")
    with patch.object(audit.subprocess, "run", return_value=fake_run):
        assert audit.grep_count_production_callers("foo", Path("/dev/null")) == -1


def test_grep_count_handles_timeout() -> None:
    """subprocess.TimeoutExpired must return -1, not crash."""
    import subprocess as _sp

    def _raise(*_a, **_kw):
        raise _sp.TimeoutExpired(cmd="grep", timeout=60)

    with patch.object(audit.subprocess, "run", side_effect=_raise):
        assert audit.grep_count_production_callers("foo", Path("/dev/null")) == -1


# ---------------------------------------------------------------------------
# grep regex coverage — #6872b widening for dynamic-import patterns
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "caller_line,stem,should_match",
    [
        # Static patterns — already worked pre-#6872b
        ("from auth_rbac import require_permission", "auth_rbac", True),
        ("import auth_rbac", "auth_rbac", True),
        # JS/TS dynamic ES-module imports — the FP class this PR fixes
        ("    component: () => import('@/views/CustomDashboard.vue'),", "CustomDashboard", True),
        ("const m = await import('./modules/MyModule.js')", "MyModule", True),
        # CommonJS / Vite require()
        ("const x = require('./helpers/MyHelper.ts')", "MyHelper", True),
        # Python dynamic loaders
        ("mod = importlib.import_module('autobot.foo')", "foo", True),
        ("mod = __import__('my_module')", "my_module", True),
        # Negative: stem appearing only in unrelated code (no import-shape) doesn't match
        ("logger.info('message about CustomDashboard usage')", "CustomDashboard", False),
        ("self.helper = MyHelper()", "MyHelper", False),
    ],
)
def test_grep_count_regex_pattern_shapes(caller_line: str, stem: str, should_match: bool, tmp_path: Path) -> None:
    """Verify the regex used by grep matches both static and dynamic imports.

    Constructs the same regex the script uses and runs it via Python's `re`
    so the test isn't coupled to system grep's specific dialect.
    """
    import re

    # Mirror the script's pattern construction exactly
    pattern = (
        rf"from .*\b{stem}\b"
        rf"|import .*\b{stem}\b"
        rf"|import\([^)]*\b{stem}\b"
        rf"|require\([^)]*\b{stem}\b"
        rf"|importlib\.[a-z_]+\([^)]*\b{stem}\b"
        rf"|__import__\([^)]*\b{stem}\b"
    )
    matched = re.search(pattern, caller_line) is not None
    assert matched is should_match, (
        f"pattern: {pattern!r}\n"
        f"line:    {caller_line!r}\n"
        f"stem:    {stem!r}\n"
        f"expected match={should_match}, got match={matched}"
    )


# ---------------------------------------------------------------------------
# fetch_closed_tracker_set — gh JSON parsing + error path
# ---------------------------------------------------------------------------


def test_fetch_closed_tracker_set_parses_gh_output() -> None:
    fake_run = MagicMock(
        returncode=0,
        stdout=json.dumps([{"number": 1}, {"number": 2}, {"number": 3}]),
        stderr="",
    )
    with patch.object(audit.subprocess, "run", return_value=fake_run):
        assert audit.fetch_closed_tracker_set() == {1, 2, 3}


def test_fetch_closed_tracker_set_gh_unavailable() -> None:
    """gh missing or non-zero exit must degrade gracefully to empty set."""
    with patch.object(audit.subprocess, "run", side_effect=FileNotFoundError("gh")):
        assert audit.fetch_closed_tracker_set() == set()


def test_fetch_closed_tracker_set_invalid_json() -> None:
    fake_run = MagicMock(returncode=0, stdout="<<not json>>", stderr="")
    with patch.object(audit.subprocess, "run", return_value=fake_run):
        assert audit.fetch_closed_tracker_set() == set()


# ---------------------------------------------------------------------------
# existing_audit_issues_by_tracker — title-prefix dedup
# ---------------------------------------------------------------------------


def test_existing_audit_issues_extracts_tracker_numbers() -> None:
    fake_run = MagicMock(
        returncode=0,
        stdout=json.dumps(
            [
                {
                    "number": 9000,
                    "title": "discovery(unwired-tracker): wire in foo (tracker #1234 closed prematurely)",
                },
                {
                    "number": 9001,
                    "title": "discovery(unwired-tracker): wire in bar (tracker #5678 closed prematurely)",
                },
                # No tracker number → must not crash, just skipped
                {"number": 9002, "title": "unrelated issue title"},
            ]
        ),
        stderr="",
    )
    with patch.object(audit.subprocess, "run", return_value=fake_run):
        assert audit.existing_audit_issues_by_tracker() == {1234, 5678}


def test_existing_audit_issues_gh_failure() -> None:
    """gh failures must return empty set (open-mode default — file new ones)."""
    with patch.object(audit.subprocess, "run", side_effect=FileNotFoundError("gh")):
        assert audit.existing_audit_issues_by_tracker() == set()


# ---------------------------------------------------------------------------
# render_human / render_json — output shape contracts
# ---------------------------------------------------------------------------


def test_render_human_no_findings() -> None:
    out = audit.render_human([])
    assert "✅" in out
    assert "No unwired-tracker findings" in out


def test_render_human_with_findings() -> None:
    findings = [
        audit.Finding(file="autobot-backend/foo.py", tracker=42, tracker_state="CLOSED", production_callers=0),
    ]
    out = audit.render_human(findings)
    assert "❌" in out
    assert "autobot-backend/foo.py" in out
    assert "#42" in out


def test_render_json_round_trips() -> None:
    findings = [
        audit.Finding(file="x.py", tracker=1, tracker_state="CLOSED", production_callers=0),
    ]
    parsed = json.loads(audit.render_json(findings))
    assert parsed == [{"file": "x.py", "tracker": 1, "tracker_state": "CLOSED", "production_callers": 0}]


# ---------------------------------------------------------------------------
# derive_module_path / load_router_registry_modules — #7109 registry detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rel,expected",
    [
        ("autobot-backend/api/captcha.py", "api.captcha"),
        ("autobot-backend/intelligence/streaming_executor.py", "intelligence.streaming_executor"),
        ("autobot-frontend/src/composables/useApi.ts", None),  # not .py
        ("README.md", None),  # not .py and no scan-dir layout
        ("autobot-backend/conftest.py", "conftest"),  # ends up empty inner
    ],
)
def test_derive_module_path(rel: str, expected: Optional[str]) -> None:
    p = audit.REPO_ROOT / rel
    assert audit.derive_module_path(p) == expected


def test_load_router_registry_modules_extracts_dotted_paths(tmp_path: Path) -> None:
    """Parses ('module.path', ...) tuples from any router_registry/*.py."""
    fake_registry = tmp_path / "router_registry"
    fake_registry.mkdir()
    (fake_registry / "feature_routers.py").write_text(
        """FEATURE_ROUTERS = [
    ("api.captcha", "", ["captcha"], "captcha"),
    ("api.vision", "/vision", ["vision"], "vision"),
]
""",
        encoding="utf-8",
    )
    (fake_registry / "core_routers.py").write_text(
        """CORE_ROUTERS = [
    ("api.health", "/health", ["health"], "health"),
]
""",
        encoding="utf-8",
    )
    (fake_registry / "__init__.py").write_text("# excluded by name", encoding="utf-8")

    with patch.object(audit, "ROUTER_REGISTRY_DIR", fake_registry):
        modules = audit.load_router_registry_modules()
    assert modules == {"api.captcha", "api.vision", "api.health"}


def test_load_router_registry_modules_missing_dir() -> None:
    """No registry dir → empty set, no crash."""
    with patch.object(audit, "ROUTER_REGISTRY_DIR", Path("/nonexistent/path")):
        assert audit.load_router_registry_modules() == set()


def test_scan_skips_router_registry_modules(tmp_path: Path) -> None:
    """End-to-end: a file registered in router_registry must not be flagged.

    Reproduces the #7109 false-positive: api/captcha.py looks unwired to
    the import-grep heuristic but is actually a live router.
    """
    fake_root = tmp_path
    backend = fake_root / "autobot-backend"
    api = backend / "api"
    api.mkdir(parents=True)
    (api / "captcha.py").write_text('"""Issue #206 — captcha API."""\n', encoding="utf-8")

    registry_dir = backend / "initialization" / "router_registry"
    registry_dir.mkdir(parents=True)
    (registry_dir / "feature_routers.py").write_text(
        'X = [("api.captcha", "", ["captcha"], "captcha")]\n',
        encoding="utf-8",
    )

    with (
        patch.object(audit, "REPO_ROOT", fake_root),
        patch.object(audit, "ROUTER_REGISTRY_DIR", registry_dir),
        patch.object(audit, "fetch_closed_tracker_set", return_value={206}),
        patch.object(audit, "grep_count_production_callers", return_value=0),
    ):
        findings = audit.scan()

    assert findings == [], f"api/captcha.py should be filtered as registry-wired, got {findings}"


# ---------------------------------------------------------------------------
# is_entry_point_script — #7128b runner-script + demos/scripts/bin filter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,is_dts",
    [
        (Path("autobot-frontend/src/types/global.d.ts"), True),
        (Path("autobot-frontend/src/config/AppConfig.d.ts"), True),
        # Negative: regular .ts file
        (Path("autobot-frontend/src/utils/helper.ts"), False),
        # Negative: filename ends in .d.ts but it's a directory marker (.d.ts in path component)
        # This shouldn't ever happen but let's be explicit:
        (Path("autobot-frontend/src/types/foo.ts"), False),
    ],
)
def test_is_ambient_type_declaration(path: Path, is_dts: bool) -> None:
    assert audit.is_ambient_type_declaration(path) is is_dts


@pytest.mark.parametrize(
    "path,is_entry",
    [
        # run_*.py prefix style (the case that flagged my own runners post-#7127)
        (Path("autobot-backend/intelligence/demos/run_intelligent_agent.py"), True),
        (Path("autobot-backend/intelligence/demos/run_streaming_executor.py"), True),
        (Path("scripts/run_smoke.py"), True),
        # /demos/, /scripts/, /bin/ directory conventions
        (Path("autobot-backend/intelligence/demos/__init__.py"), True),
        (Path("autobot-backend/scripts/migrate_data.py"), True),
        (Path("bin/server.py"), True),
        # Non-entry-point production code
        (Path("autobot-backend/api/captcha.py"), False),
        (Path("autobot-backend/intelligence/intelligent_agent.py"), False),
        # Edge: a non-py file should not match (the filter is .py-only)
        (Path("autobot-frontend/run_thing.ts"), False),
        # Edge: 'demoscope.py' contains 'demos' substring but not '/demos/'
        (Path("autobot-backend/utils/demoscope.py"), False),
    ],
)
def test_is_entry_point_script(path: Path, is_entry: bool) -> None:
    assert audit.is_entry_point_script(path) is is_entry


def test_scan_skips_entry_point_runners(tmp_path: Path) -> None:
    """Reproduces the post-#7127 false-positive: runner scripts cite #7127
    (closed) and have 0 callers by design — they shouldn't be flagged.
    """
    fake_root = tmp_path
    backend = fake_root / "autobot-backend"
    demos = backend / "intelligence" / "demos"
    demos.mkdir(parents=True)
    (demos / "run_intelligent_agent.py").write_text(
        '"""Standalone demo runner (#7127)."""\n',
        encoding="utf-8",
    )
    registry_dir = backend / "initialization" / "router_registry"
    registry_dir.mkdir(parents=True)
    (registry_dir / "feature_routers.py").write_text("X = []\n", encoding="utf-8")

    with (
        patch.object(audit, "REPO_ROOT", fake_root),
        patch.object(audit, "ROUTER_REGISTRY_DIR", registry_dir),
        patch.object(audit, "fetch_closed_tracker_set", return_value={7127}),
        patch.object(audit, "grep_count_production_callers", return_value=0),
    ):
        findings = audit.scan()

    assert findings == [], f"runner script should be skipped as entry-point, got {findings}"


def test_scan_still_flags_truly_orphaned_module(tmp_path: Path) -> None:
    """Sanity check: real orphans (not in registry, 0 callers) still get flagged."""
    fake_root = tmp_path
    backend = fake_root / "autobot-backend"
    orphan_dir = backend / "orchestration"
    orphan_dir.mkdir(parents=True)
    (orphan_dir / "ghost_module.py").write_text(
        '"""Issue #4242 — never wired anywhere."""\n',
        encoding="utf-8",
    )
    registry_dir = backend / "initialization" / "router_registry"
    registry_dir.mkdir(parents=True)
    (registry_dir / "feature_routers.py").write_text("X = []\n", encoding="utf-8")

    with (
        patch.object(audit, "REPO_ROOT", fake_root),
        patch.object(audit, "ROUTER_REGISTRY_DIR", registry_dir),
        patch.object(audit, "fetch_closed_tracker_set", return_value={4242}),
        patch.object(audit, "grep_count_production_callers", return_value=0),
    ):
        findings = audit.scan()

    assert len(findings) == 1
    assert findings[0].tracker == 4242
    assert findings[0].file.endswith("ghost_module.py")
