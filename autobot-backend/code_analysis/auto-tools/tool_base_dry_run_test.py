# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""`--dry-run` must not modify the tree (#12678).

`ConsoleLogToolBase` rewrites source files in place. The CLI accepted
``--dry-run`` and discarded it — `cli_main` never handed the parsed args to the
instance — so the flag a user would most reasonably trust before letting a tool
rewrite their tree did nothing.

These assert on **file bytes**, not on a reported counter: a dry run that
reports "0 modified" while still writing would pass a counter-based test and be
worse than the honest no-op it replaced.
"""

import argparse
import importlib.util
import pathlib
import sys

import pytest

_DIR = pathlib.Path(__file__).parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


tool_base = _load("tool_base")

DIRTY = "function f() {\n  console.log('x');\n  return 1;\n}\n"


@pytest.fixture
def js_file(tmp_path):
    path = tmp_path / "app.js"
    path.write_text(DIRTY, encoding="utf-8")
    return path


class _Cleaner(tool_base.ConsoleLogToolBase):
    """Minimal concrete tool: strips the console.log line."""

    REPORT_COUNT_KEY = "console_logs_removed"

    def __init__(self, project_path, backup_dir=None):
        # The base declares no __init__; it reads these attributes directly.
        self.project_root = pathlib.Path(project_path)
        self.backup_dir = pathlib.Path(backup_dir or (self.project_root / "backups"))
        self.report = {self.REPORT_COUNT_KEY: 0}

    def _transform_content(self, content, file_path):
        lines = [ln for ln in content.splitlines(keepends=True) if "console.log" not in ln]
        removed = len(content.splitlines()) - len(lines)
        return "".join(lines), removed


def test_dry_run_leaves_the_file_byte_identical(js_file, tmp_path):
    tool = _Cleaner(str(tmp_path))
    tool._apply_cli_args(argparse.Namespace(dry_run=True))

    changed = tool.process_file(js_file)

    assert changed is True, "a dry run should still report that it would change the file"
    assert js_file.read_text(encoding="utf-8") == DIRTY, "dry run modified the file"


def test_dry_run_still_reports_what_it_would_change(js_file, tmp_path):
    tool = _Cleaner(str(tmp_path))
    tool._apply_cli_args(argparse.Namespace(dry_run=True))

    tool.process_file(js_file)

    assert tool.report["console_logs_removed"] == 1


def test_dry_run_creates_no_backup(js_file, tmp_path):
    tool = _Cleaner(str(tmp_path))
    tool._apply_cli_args(argparse.Namespace(dry_run=True))

    tool.process_file(js_file)
    backups = [p for p in tmp_path.rglob("*") if p.is_file() and p != js_file]

    assert backups == [], f"dry run wrote {backups}"


def test_without_dry_run_the_file_is_rewritten(js_file, tmp_path):
    tool = _Cleaner(str(tmp_path))

    tool.process_file(js_file)

    assert "console.log" not in js_file.read_text(encoding="utf-8")


def test_apply_cli_args_defaults_to_writing(js_file, tmp_path):
    """A tool that declares no flags must keep its previous behaviour."""
    tool = _Cleaner(str(tmp_path))
    tool._apply_cli_args(argparse.Namespace())

    tool.process_file(js_file)

    assert "console.log" not in js_file.read_text(encoding="utf-8")
