# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every flag of the two retired indexers is accepted by the one CLI (#18129)."""

import importlib.util
import subprocess
import sys

import pytest
from repo_tests._paths import repo_root


def _cli():
    path = repo_root() / "tools" / "index_documentation.py"
    spec = importlib.util.spec_from_file_location("index_documentation_18129", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("alias", ["--force", "--full", "--reindex"])
def test_the_retired_full_flags_all_mean_force(alias: str) -> None:
    assert _cli().parse_args([alias]).force is True


def test_the_retired_scoping_flags_are_accepted() -> None:
    args = _cli().parse_args(
        ["--tier", "1", "--category", "api", "--file", "CLAUDE.md", "--dry-run", "--verbose", "--output", "o.json"]
    )
    assert (args.tier, args.category, args.file, args.dry_run, args.output) == (1, "api", "CLAUDE.md", True, "o.json")
    args = _cli().parse_args(["--search", "q", "--results", "3"])
    assert (args.search, args.results) == ("q", 3)
    assert _cli().parse_args(["--stats"]).stats is True


@pytest.mark.parametrize(
    "shim", ["autobot-infrastructure/shared/tools", "autobot-infrastructure/shared/scripts/utilities"]
)
def test_each_shim_reaches_the_one_entry_point(shim: str) -> None:
    """Running a shim with --help prints the CLI's own flags, `--category` included."""
    proc = subprocess.run(  # noqa: S603
        [sys.executable, str(repo_root() / shim / "index_documentation.py"), "--help"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "--category" in proc.stdout and "--rebuild" in proc.stdout
