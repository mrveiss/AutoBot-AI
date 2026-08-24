# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for the behavioural pre-commit hook gate (#14878).

Every case drives ``main()`` — the production entry point the workflow step
calls — and asserts on its exit code, not on a helper's return value. The
defect this gate exists to remove is a verdict that never reaches a merge
decision, so a test that stops at the parser would repeat it one level down.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE = Path(__file__).with_name("check_gating_precommit_hooks.py")
_REPO_ROOT = Path(__file__).resolve().parents[1]
_REAL_CONFIG = _REPO_ROOT / ".pre-commit-config.yaml"


@pytest.fixture
def gate():
    spec = importlib.util.spec_from_file_location("check_gating_precommit_hooks", _MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# A minimal config in the same shape as the real one. Written here rather than
# read from disk so the failure directions can be exercised without editing the
# repository's own config.
_CONFIG = """\
repos:
  - repo: local
    hooks:
      - id: ssot-config-lib-guard
        name: Shell SSOT Library Self-Test (#14041)
        entry: bash autobot-infrastructure/shared/tests/test_ssot_config_lib.sh
      - id: black
        name: black
"""

_GUARD = "Shell SSOT Library Self-Test (#14041)"


def _output(guard_status: str | None) -> str:
    """A pre-commit --all-files transcript, optionally omitting the guard's line."""
    lines = ["black" + "." * 60 + "Failed", "check yaml" + "." * 55 + "Passed"]
    if guard_status is not None:
        lines.insert(1, _GUARD + "." * 30 + guard_status)
    return "\n".join(lines) + "\n"


def _run(gate, tmp_path, output, config=_CONFIG):
    log = tmp_path / "precommit-output.txt"
    log.write_text(output, encoding="utf-8")
    cfg = tmp_path / "config.yaml"
    cfg.write_text(config, encoding="utf-8")
    return gate.main([str(log), "--config", str(cfg)])


def test_passing_guard_exits_zero_even_though_formatters_failed(gate, tmp_path):
    """The formatter/behavioural split is the whole point: black Failed here."""
    assert _run(gate, tmp_path, _output("Passed")) == 0


def test_failing_guard_blocks(gate, tmp_path):
    assert _run(gate, tmp_path, _output("Failed")) == 1


def test_skipped_guard_blocks(gate, tmp_path):
    """A behavioural suite that did not run validated nothing (#14878)."""
    assert _run(gate, tmp_path, _output("Skipped")) == 1


def test_absent_result_line_blocks(gate, tmp_path):
    """An absent result must not read as a clean one."""
    assert _run(gate, tmp_path, _output(None)) == 1


def test_empty_output_blocks(gate, tmp_path):
    assert _run(gate, tmp_path, "") == 1


def test_allowlist_entry_stranded_by_a_rename_blocks(gate, tmp_path):
    """An id no longer in the config exempts nothing — it must say so loudly."""
    renamed = _CONFIG.replace("id: ssot-config-lib-guard", "id: ssot-config-lib-guard-v2")
    assert _run(gate, tmp_path, _output("Passed"), config=renamed) == 1


def test_ansi_coloured_output_is_still_read(gate, tmp_path):
    coloured = _output("Failed").replace(_GUARD, "\x1b[1m" + _GUARD + "\x1b[m")
    assert _run(gate, tmp_path, coloured) == 1


def test_no_files_to_check_postfix_is_parsed(gate, tmp_path):
    """pre-commit's own skip wording, which carries a parenthesised postfix."""
    output = _output(None).replace(
        "black", _GUARD + "." * 10 + "(no files to check)Skipped\nblack", 1
    )
    assert _run(gate, tmp_path, output) == 1


def test_every_allowlisted_id_exists_in_the_real_config(gate):
    """The guard against the exemption list drifting away from the real hooks."""
    names = gate.hook_names(_REAL_CONFIG.read_text(encoding="utf-8"))
    missing = [hook_id for hook_id in gate.GATING_HOOK_IDS if hook_id not in names]
    assert not missing, f"allowlisted hook ids absent from .pre-commit-config.yaml: {missing}"


def test_allowlist_is_not_empty(gate):
    """An empty allowlist would pass everything while looking like a gate."""
    assert gate.GATING_HOOK_IDS


def test_names_come_from_the_yaml_parser_not_the_raw_text(gate):
    """A ``#`` issue ref in an unquoted name opens a YAML comment.

    ``name: Function Length Check (Issue #5512)`` parses to
    ``Function Length Check (Issue`` and that truncated string is what
    pre-commit prints. Matching the spelling in the file would never hit.
    """
    names = gate.hook_names("repos:\n  - repo: local\n    hooks:\n      - id: x\n        name: A (Issue #1)\n")
    assert names["x"] == "A (Issue"


def test_a_hook_reporting_both_statuses_resolves_to_the_worse_one(gate, tmp_path):
    """Ambiguity must never resolve in the green direction."""
    output = _output("Passed").replace("black", _GUARD + "." * 10 + "Failed\nblack", 1)
    assert _run(gate, tmp_path, output) == 1
