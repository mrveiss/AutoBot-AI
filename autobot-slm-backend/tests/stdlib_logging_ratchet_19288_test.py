# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SLM-backend half of the #19288 guard; runs under the SLM interpreter in CI's slm-backend step.

1. The modules moved off stdlib logging import under a mocked ``config``, as the SLM conftest
   installs it.
2. A ratchet: a module-level ``logging.getLogger`` in a non-test SLM module must be listed in
   ``stdlib_logging_baseline_19288.txt``. A NEW stdlib logger -- or one of the moved modules going
   back -- fails here, so the moved list below is not the only line of defence.
"""

import ast
import json
import re
from pathlib import Path

from repo_tests._mocked_config_import import run_sweep
from repo_tests._paths import repo_root

_SLM_ROOT = repo_root() / "autobot-slm-backend"
_BASELINE = Path(__file__).with_name("stdlib_logging_baseline_19288.txt")

#: Modules that used stdlib logging only because of #19288 and now call get_logger at import.
_SLM_MOVED = (
    "api._pricing_post_sync",
    "api._resume_plan",
    "api._rsync_paths",
    "api.code_sync_paths",
    "api.memory_lifecycle_proxy",
    "api.venv_reconcile",
    "services.admin_password_sync",
    "services.auth",
    "services.frontend_bundle_health",
    "services.full_tree_drift",
    "services.generated_system_secrets",
    "services.git_subprocess",
    "services.password_epoch_store",
    "services.process_divergence",
    "services.service_remediation_tracker",
    "services.sync_deletions",
    "services.token_denylist",
)

_DETECTOR = re.compile(r"^[A-Za-z_]\w* = logging\.getLogger\(", re.MULTILINE)


def _sources() -> list[Path]:
    """Non-test .py files under the SLM root: the population the baseline is about."""
    out = []
    for path in sorted(_SLM_ROOT.rglob("*.py")):
        rel = path.relative_to(_SLM_ROOT)
        name = rel.name
        if {"tests", "test"} & set(rel.parts[:-1]) or name == "conftest.py":
            continue
        if name.endswith("_test.py") or name.startswith("test_"):
            continue
        out.append(path)
    return out


def _by_regex(paths: list[Path]) -> set[str]:
    return {str(p.relative_to(_SLM_ROOT)) for p in paths if _DETECTOR.search(p.read_text(encoding="utf-8"))}


def _is_stdlib_logger(node: ast.stmt) -> bool:
    if not (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)):
        return False
    call = node.value
    return (
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "getLogger"
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "logging"
    )


def _by_ast(paths: list[Path]) -> set[str]:
    """Second derivation (RATCHET_BASELINES rule 3): module-level assignments, from the syntax tree."""
    found = set()
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(_is_stdlib_logger(node) for node in tree.body):
            found.add(str(path.relative_to(_SLM_ROOT)))
    return found


def _baseline() -> set[str]:
    lines = _BASELINE.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def test_moved_slm_modules_import_under_a_mocked_config(tmp_path: Path) -> None:
    report = run_sweep(tmp_path, _SLM_MOVED, (_SLM_ROOT,))
    assert report["targets"] == list(_SLM_MOVED)
    assert report["failures"] == {}, json.dumps(report["failures"], indent=2)


def test_no_new_module_level_stdlib_logger_in_the_slm_backend() -> None:
    paths = _sources()
    found = _by_regex(paths)
    assert "scripts/autobot-admin.py" in found, "known positive missing: the detector is not reading"
    assert found == _by_ast(paths), "regex and AST disagree on which modules use stdlib logging"
    new = sorted(found - _baseline())
    assert not new, f"new stdlib logger(s), use get_logger (#19288): {new}"
    stale = sorted(_baseline() - found)
    assert not stale, f"no longer stdlib, delete from {_BASELINE.name}: {stale}"


def test_no_moved_module_is_back_on_the_baseline() -> None:
    moved_paths = {name.replace(".", "/") + ".py" for name in _SLM_MOVED}
    assert not moved_paths & _baseline()
