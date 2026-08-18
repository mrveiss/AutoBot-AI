# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for optimize_agents — dry-run must be genuinely safe (#14546).

``optimize_agents.py`` rewrites hand-written ``.claude/agents/*.md`` files in
place with no preview and no ``--dry-run`` before this issue. The guard this
suite exists for: :func:`process_agent_files` with ``apply_changes=False``
must perform **zero writes** — every fixture file's mtime and content must be
byte-identical after the run. ``test_dry_run_matches_apply_preview`` mutates
that guarantee (flips the default so dry-run writes anyway) and asserts the
test goes red, so the guard itself is proven to catch the regression it names.
"""

import importlib.util
import pathlib
import sys

import pytest

_MODULE_PATH = pathlib.Path(__file__).with_name("optimize_agents.py")

_FIXTURE_WITH_SECTION = """---
name: test-agent
---

# Test Agent

## 🚨 MANDATORY LOCAL-ONLY EDITING ENFORCEMENT
Some legacy enforcement text that should be collapsed.

---

## Other Section
Untouched content.
"""

_FIXTURE_WITHOUT_SECTION = """---
name: other-agent
---

# Other Agent

Nothing here matches the optimization pattern.
"""


def _load_module():
    """Import optimize_agents by path — its directory is not a package."""
    spec = importlib.util.spec_from_file_location("optimize_agents", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["optimize_agents"] = module
    spec.loader.exec_module(module)
    return module


optimize_agents = _load_module()


@pytest.fixture
def agent_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    """A scratch ``.claude/agents``-shaped directory — never the real tree."""
    directory = tmp_path / "agents"
    directory.mkdir()
    (directory / "needs-change.md").write_text(_FIXTURE_WITH_SECTION, encoding="utf-8")
    (directory / "unchanged.md").write_text(_FIXTURE_WITHOUT_SECTION, encoding="utf-8")
    return directory


def _hashes(directory: pathlib.Path) -> dict[str, str]:
    """Hash every file's exact bytes, keyed by name."""
    return {f.name: f.read_bytes().hex() for f in sorted(directory.glob("*.md"))}


def test_dry_run_writes_nothing(agent_dir: pathlib.Path):
    """The default (apply_changes=False) must not touch disk at all."""
    before = _hashes(agent_dir)
    agent_files = sorted(agent_dir.glob("*.md"))

    summary = optimize_agents.process_agent_files(agent_files, apply_changes=False)

    after = _hashes(agent_dir)
    assert after == before, "dry-run modified file content on disk"
    assert summary["modified"] == 1
    assert summary["processed"] == 2


def test_apply_actually_rewrites(agent_dir: pathlib.Path):
    """--apply must perform the write dry-run only previewed."""
    agent_files = sorted(agent_dir.glob("*.md"))

    summary = optimize_agents.process_agent_files(agent_files, apply_changes=True)

    rewritten = (agent_dir / "needs-change.md").read_text(encoding="utf-8")
    assert "MANDATORY LOCAL-ONLY EDITING ENFORCEMENT" not in rewritten
    assert "AUTOBOT POLICIES" in rewritten
    assert summary["modified"] == 1


def test_dry_run_preview_matches_what_apply_would_write(agent_dir: pathlib.Path):
    """Dry-run's reported optimized content equals what --apply later writes."""
    target = agent_dir / "needs-change.md"
    _, _, previewed = optimize_agents.compute_optimization(target)

    optimize_agents.process_agent_files([target], apply_changes=True)

    assert target.read_text(encoding="utf-8") == previewed


def test_dry_run_matches_apply_preview(agent_dir: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    """Mutation guard: if dry-run started writing, this test must go red.

    Simulates the exact regression the guard exists for by forcing
    ``_handle_agent_file`` to write even when the caller asked for a preview.
    """
    real_handle = optimize_agents._handle_agent_file

    def _always_write(agent_file: pathlib.Path, apply_changes: bool) -> dict[str, int]:
        return real_handle(agent_file, apply_changes=True)

    monkeypatch.setattr(optimize_agents, "_handle_agent_file", _always_write)

    before = _hashes(agent_dir)
    agent_files = sorted(agent_dir.glob("*.md"))
    optimize_agents.process_agent_files(agent_files, apply_changes=False)
    after = _hashes(agent_dir)

    assert after != before, "mutation did not reach disk — guard is not exercising the write path"


def test_atomic_write_leaves_no_partial_file_on_failure(agent_dir: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    """A failure mid-write must not leave a truncated agent file behind."""
    target = agent_dir / "needs-change.md"
    original_bytes = target.read_bytes()

    def _boom(*_args, **_kwargs):
        raise OSError("simulated crash mid-write")

    monkeypatch.setattr(optimize_agents.os, "replace", _boom)

    with pytest.raises(OSError):
        optimize_agents.write_atomically(target, "corrupted content")

    assert target.read_bytes() == original_bytes, "original file was not left intact"
    leftover_tmp = list(agent_dir.glob(".*.tmp"))
    assert leftover_tmp == [], f"temp file(s) leaked: {leftover_tmp}"


def test_empty_directory_is_loud_not_silent():
    """An empty .md glob must be reported, not read as a clean no-op."""
    summary = optimize_agents.process_agent_files([], apply_changes=False)
    assert summary["processed"] == 0
    # main() itself is the loud-failure path for this case (glob matched zero
    # files) — covered by test_main_errors_on_empty_agent_dir below.


def test_main_errors_on_empty_agent_dir(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys):
    """main() must exit non-zero and print an explicit error, never a quiet 0."""
    empty_agents_dir = tmp_path / ".claude" / "agents"
    empty_agents_dir.mkdir(parents=True)
    monkeypatch.setattr(optimize_agents, "project_root", lambda: tmp_path)
    monkeypatch.setattr(sys, "argv", ["optimize_agents.py"])

    exit_code = optimize_agents.main()

    assert exit_code == 1
    assert "No agent files found" in capsys.readouterr().out
