# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for tools/lint/check_no_utcnow_isoformat.py — see #5269.

Covers detection, allowlisting, edge cases, and exit codes for the
regression-prevention hook shipped in PR #5264 (#5178 Part C).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Import the script-under-test as a module. The script is intentionally
# at tools/lint/ (not on a package path) — load it directly by file.
_HOOK_PATH = Path(__file__).parent / "check_no_utcnow_isoformat.py"
_spec = importlib.util.spec_from_file_location("_hook_under_test", _HOOK_PATH)
assert _spec is not None and _spec.loader is not None
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)


# ---------------------------------------------------------------------------
# Detection — positive cases (each banned pattern produces a hit)
# ---------------------------------------------------------------------------


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def test_detects_utcnow_isoformat_after_from_import(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        "case.py",
        "from datetime import datetime\nts = datetime.utcnow().isoformat()\n",
    )
    rc = hook.main(["check_no_utcnow_isoformat", str(f)])
    assert rc == 1


def test_detects_utcnow_isoformat_after_module_import(tmp_path: Path) -> None:
    # `import datetime; datetime.datetime.utcnow().isoformat()` — same regex
    # because the inner `datetime.utcnow().isoformat(` substring matches.
    f = _write(
        tmp_path,
        "case.py",
        "import datetime\nts = datetime.datetime.utcnow().isoformat()\n",
    )
    rc = hook.main(["check_no_utcnow_isoformat", str(f)])
    assert rc == 1


def test_detects_z_suffix_mixed_format(tmp_path: Path) -> None:
    # The #5238 pattern: invalid microseconds + Z combined.
    f = _write(
        tmp_path,
        "case.py",
        'from datetime import datetime\nts = datetime.utcnow().isoformat() + "Z"\n',
    )
    rc = hook.main(["check_no_utcnow_isoformat", str(f)])
    assert rc == 1


def test_detects_z_suffix_with_single_quotes(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        "case.py",
        "from datetime import datetime\nts = datetime.utcnow().isoformat() + 'Z'\n",
    )
    rc = hook.main(["check_no_utcnow_isoformat", str(f)])
    assert rc == 1


def test_detects_naive_strftime_iso(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        "case.py",
        'import time\nts = time.strftime("%Y-%m-%dT%H:%M:%S")\n',
    )
    rc = hook.main(["check_no_utcnow_isoformat", str(f)])
    assert rc == 1


def test_detects_naive_strftime_with_seconds_only(tmp_path: Path) -> None:
    # time.strftime with a longer ISO format also fires
    f = _write(
        tmp_path,
        "case.py",
        'import time\nts = time.strftime("%Y-%m-%dT%H:%M:%SZ")\n',
    )
    rc = hook.main(["check_no_utcnow_isoformat", str(f)])
    assert rc == 1


# ---------------------------------------------------------------------------
# Detection — negative cases (these should NOT fire)
# ---------------------------------------------------------------------------


def test_clean_file_passes(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        "clean.py",
        "from autobot_shared.time_utils import utc_timestamp\n" "ts = utc_timestamp()\n",
    )
    rc = hook.main(["check_no_utcnow_isoformat", str(f)])
    assert rc == 0


def test_canonical_aware_isoformat_not_flagged(tmp_path: Path) -> None:
    # `datetime.now(timezone.utc).isoformat()` is the CORRECT pattern;
    # the hook must not flag it.
    f = _write(
        tmp_path,
        "ok.py",
        "from datetime import datetime, timezone\n" "ts = datetime.now(timezone.utc).isoformat()\n",
    )
    rc = hook.main(["check_no_utcnow_isoformat", str(f)])
    assert rc == 0


def test_strftime_with_explicit_time_arg_not_flagged(tmp_path: Path) -> None:
    # Passing an explicit time tuple (e.g. time.gmtime()) makes strftime
    # safe — the hook only flags the no-arg form. The regex requires the
    # closing paren immediately after the format-string literal, so a
    # comma-separated second argument should pass.
    f = _write(
        tmp_path,
        "ok.py",
        'import time\nts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())\n',
    )
    rc = hook.main(["check_no_utcnow_isoformat", str(f)])
    assert rc == 0


def test_non_iso_strftime_not_flagged(tmp_path: Path) -> None:
    # Date-only / non-T-separated formats are out of scope for the
    # #5178 regression hook (they don't produce the broken ISO-8601
    # strings the hook protects against).
    f = _write(
        tmp_path,
        "ok.py",
        'import time\nts = time.strftime("%Y-%m-%d %H:%M:%S")\n',
    )
    rc = hook.main(["check_no_utcnow_isoformat", str(f)])
    assert rc == 0


def test_bare_utcnow_without_isoformat_not_flagged(tmp_path: Path) -> None:
    # Pattern A/B/C (#5211 territory) — the bare utcnow() call is NOT
    # the responsibility of THIS hook; #5211's own enforcement (Ruff
    # DTZ003) will cover it once enabled.
    f = _write(
        tmp_path,
        "ok.py",
        "from datetime import datetime\n"
        "started_at = datetime.utcnow()\n"
        "delta = (datetime.utcnow() - started_at).total_seconds()\n",
    )
    rc = hook.main(["check_no_utcnow_isoformat", str(f)])
    assert rc == 0


# ---------------------------------------------------------------------------
# Allowlist
# ---------------------------------------------------------------------------


def test_allowlisted_path_not_scanned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Place a file at an allowlisted path inside tmp_path, point repo_root
    # at tmp_path, and confirm scanning is skipped.
    allowed = "autobot_shared/time_utils.py"
    target = tmp_path / allowed
    target.parent.mkdir(parents=True)
    target.write_text(
        "from datetime import datetime\nts = datetime.utcnow().isoformat()\n",
        encoding="utf-8",
    )
    hits = hook._scan(target, tmp_path)
    assert hits == [], "allowlisted file must not produce hits"


def test_non_allowlisted_path_with_same_pattern_does_fire(tmp_path: Path) -> None:
    # Sanity check the inverse — same pattern in non-allowlisted location
    # DOES fire (proves the allowlist test isn't a no-op).
    target = tmp_path / "autobot-backend" / "api" / "some_file.py"
    target.parent.mkdir(parents=True)
    target.write_text(
        "from datetime import datetime\nts = datetime.utcnow().isoformat()\n",
        encoding="utf-8",
    )
    hits = hook._scan(target, tmp_path)
    assert len(hits) == 1
    assert hits[0][1] == "isoformat"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_path_outside_repo_root_handled(tmp_path: Path) -> None:
    # The fix in PR #5264 made _scan() resilient to files outside repo_root
    # via try/except on relative_to() — verify it still works.
    f = _write(
        tmp_path,
        "outside.py",
        "from datetime import datetime\nts = datetime.utcnow().isoformat()\n",
    )
    # Use a different "repo root" so the file is "outside" it
    fake_root = tmp_path / "different_root"
    fake_root.mkdir()
    hits = hook._scan(f, fake_root)
    assert len(hits) == 1


def test_non_utf8_file_silently_skipped(tmp_path: Path) -> None:
    # Files with bytes that don't decode as UTF-8 must not crash the scan.
    f = tmp_path / "binary.py"
    f.write_bytes(b"\xff\xfe\x00datetime.utcnow().isoformat()")
    hits = hook._scan(f, tmp_path)
    assert hits == []


def test_missing_file_silently_skipped(tmp_path: Path) -> None:
    # OSError on read should be swallowed (no exception, no hit).
    nonexistent = tmp_path / "nope.py"
    hits = hook._scan(nonexistent, tmp_path)
    assert hits == []


def test_multiple_patterns_one_line(tmp_path: Path) -> None:
    # A line with both `utcnow().isoformat()` AND `+ "Z"` produces TWO hits
    # (one per matching pattern) because the `+ "Z"` regex matches the
    # whole expression and the bare `isoformat()` regex matches the prefix.
    f = _write(
        tmp_path,
        "case.py",
        'from datetime import datetime\nts = datetime.utcnow().isoformat() + "Z"\n',
    )
    hits = hook._scan(f, tmp_path)
    pattern_ids = sorted(h[1] for h in hits)
    assert pattern_ids == ["isoformat", "z-suffix-isoformat"]


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


def test_exit_zero_when_clean(tmp_path: Path) -> None:
    f = _write(tmp_path, "clean.py", "from autobot_shared.time_utils import utc_timestamp\n")
    rc = hook.main(["check_no_utcnow_isoformat", str(f)])
    assert rc == 0


def test_exit_one_when_violations_found(tmp_path: Path) -> None:
    f = _write(
        tmp_path,
        "bad.py",
        "from datetime import datetime\nts = datetime.utcnow().isoformat()\n",
    )
    rc = hook.main(["check_no_utcnow_isoformat", str(f)])
    assert rc == 1


# ---------------------------------------------------------------------------
# argv handling
# ---------------------------------------------------------------------------


def test_explicit_argv_overrides_full_scan(tmp_path: Path) -> None:
    # When argv has paths, the scanner uses ONLY those paths — does not
    # walk the whole repo. Confirms the pre-commit invocation pattern.
    clean = _write(tmp_path, "clean.py", "ts = 'ok'\n")
    rc = hook.main(["check_no_utcnow_isoformat", str(clean)])
    assert rc == 0  # clean file → exit 0 even though repo has violations


def test_non_python_argv_silently_skipped(tmp_path: Path) -> None:
    # Pre-commit may pass non-.py files through; the scanner filters by
    # `.py` suffix and silently skips others.
    md = _write(tmp_path, "notes.md", "datetime.utcnow().isoformat() in markdown\n")
    rc = hook.main(["check_no_utcnow_isoformat", str(md)])
    assert rc == 0


# ---------------------------------------------------------------------------
# .worktrees exclusion (#5394) + full-scan directory exclusions live in
# tools/lint/_scan_helpers_test.py after #5449 extracted the shared helper.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Path-aware suggestion (#5397) — message recommends inline form for
# components that lack autobot_shared on path
# ---------------------------------------------------------------------------


def test_suggestion_uses_helper_for_default_path() -> None:
    # autobot-backend/ files have autobot_shared on path → recommend helper
    msg = hook._suggestion_for("autobot-backend/services/something.py")
    assert "utc_timestamp()" in msg
    assert "autobot_shared.time_utils" in msg


def test_suggestion_uses_inline_for_slm_agent_standalone() -> None:
    # Standalone agent runs on remote nodes possibly without autobot_shared
    msg = hook._suggestion_for("autobot-slm-agent/agent.py")
    assert "datetime.now(timezone.utc).isoformat()" in msg
    assert "inline" in msg


def test_suggestion_uses_inline_for_slm_backend_agent_subpackage() -> None:
    # Same agent code lives under slm-backend/slm/agent/ — also remote-deployed
    msg = hook._suggestion_for("autobot-slm-backend/slm/agent/health_collector.py")
    assert "datetime.now(timezone.utc).isoformat()" in msg


def test_suggestion_uses_inline_for_ansible_synced_copy() -> None:
    # Ansible-synced mirror of the agent code — same constraints
    msg = hook._suggestion_for("autobot-slm-backend/ansible/roles/slm_agent/files/slm/agent/agent.py")
    assert "datetime.now(timezone.utc).isoformat()" in msg


def test_suggestion_uses_inline_for_infra_shared_scripts() -> None:
    # Log forwarders run as standalone scripts on infra nodes
    msg = hook._suggestion_for("autobot-infrastructure/shared/scripts/seq_log_forwarder.py")
    assert "datetime.now(timezone.utc).isoformat()" in msg


def test_scan_emits_path_aware_suggestion_in_message(tmp_path: Path) -> None:
    # End-to-end: a violation in an inline-path file produces a message
    # recommending the inline form, not utc_timestamp().
    target = tmp_path / "autobot-slm-agent" / "agent.py"
    target.parent.mkdir(parents=True)
    target.write_text(
        "from datetime import datetime\nts = datetime.utcnow().isoformat()\n",
        encoding="utf-8",
    )
    hits = hook._scan(target, tmp_path)
    assert len(hits) == 1
    _, _, message = hits[0]
    assert "datetime.now(timezone.utc).isoformat()" in message
    assert "utc_timestamp()" not in message


# ---------------------------------------------------------------------------
# #5393 allowlist — knowledge_context_suggestions_test.py is exempt because
# the test deliberately exercises naive-timestamp handling
# ---------------------------------------------------------------------------


def test_naive_timestamp_test_fixture_allowlisted(tmp_path: Path) -> None:
    # The test at autobot-backend/knowledge/knowledge_context_suggestions_test.py
    # has `naive = datetime.utcnow().isoformat()` by design. Allowlist exempts it.
    target = tmp_path / "autobot-backend" / "knowledge" / "knowledge_context_suggestions_test.py"
    target.parent.mkdir(parents=True)
    target.write_text(
        "def test_naive_timestamp_handled(mixin):\n"
        "    naive = datetime.utcnow().isoformat()\n"
        "    assert mixin._compute_recency_score(naive) >= 0.0\n",
        encoding="utf-8",
    )
    hits = hook._scan(target, tmp_path)
    assert hits == [], "knowledge_context_suggestions_test.py must be allowlisted (#5393)"
