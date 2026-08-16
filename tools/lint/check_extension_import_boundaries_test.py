# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guards for the extension/skill/plugin import boundary checker (#14329).

The checker used to block only a hand-written list of package names while its
docstring claimed the whole ``autobot-backend`` namespace was closed. Anything
nobody remembered to add — ``media``, ``tools``, ``transcriber`` — was importable
from an extension and the check passed. The namespace is now derived from the
directory listing, so the property worth pinning is that a package *nobody has
heard of* is blocked.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "tools" / "lint" / "check_extension_import_boundaries.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECKER), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def _write_skill(tmp_path: Path, body: str) -> Path:
    """Write a probe file inside the real skills/builtin tree.

    It has to live there: scope is decided by path, so a file in tmp_path is not
    in scope and the checker would pass it for the wrong reason.
    """
    probe = REPO_ROOT / "autobot-backend" / "skills" / "builtin" / "_boundary_probe.py"
    probe.write_text(body, encoding="utf-8")
    return probe


def test_a_newly_added_core_package_is_blocked_without_editing_the_checker(tmp_path):
    """The whole point of deriving the namespace instead of listing it."""
    new_pkg = REPO_ROOT / "autobot-backend" / "_probe_pkg_14329"
    new_pkg.mkdir(exist_ok=True)
    (new_pkg / "__init__.py").touch()
    probe = _write_skill(tmp_path, "from _probe_pkg_14329.thing import X\n")
    try:
        result = _run(str(probe))
        assert result.returncode == 1
        assert "_probe_pkg_14329" in result.stdout
    finally:
        probe.unlink(missing_ok=True)
        (new_pkg / "__init__.py").unlink(missing_ok=True)
        new_pkg.rmdir()


def test_autobot_shared_is_allowed(tmp_path):
    probe = _write_skill(tmp_path, "from autobot_shared.logging_manager import get_logger\n")
    try:
        assert _run(str(probe)).returncode == 0
    finally:
        probe.unlink(missing_ok=True)


def test_inline_waiver_still_works(tmp_path):
    probe = _write_skill(
        tmp_path,
        "from services.llm_service import x  # nosemgrep: extension-no-core-internals\n",
    )
    try:
        assert _run(str(probe)).returncode == 0
    finally:
        probe.unlink(missing_ok=True)


def test_repo_currently_passes_the_boundary_rule():
    """The tree must be clean under the stricter rule, via the CI invocation."""
    files = []
    for rel in ("autobot-backend/middleware/builtin", "autobot-backend/skills/builtin", "plugins/core-plugins"):
        files.extend(str(p) for p in (REPO_ROOT / rel).rglob("*.py"))
    result = _run(*files)
    assert result.returncode == 0, result.stdout


def test_baseline_has_no_stale_entries():
    """A dormant exemption naming a moved file exempts nothing, silently."""
    result = _run("--audit-baseline")
    assert result.returncode == 0, result.stdout
