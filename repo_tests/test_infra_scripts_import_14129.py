# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Import-integrity guard for autobot-infrastructure/shared/scripts/ (#14129).

`manage_system_knowledge.py` referenced `KnowledgeBase`, `SystemKnowledgeManager`
and `yaml` without importing any of them (flake8 F821 x7); `start_hardware_monitoring.py`
imported `start_phase9_monitoring`/`stop_phase9_monitoring`, renamed to
`start_hardware_monitoring`/`stop_hardware_monitoring` in #10666/#10733, and computed
its `sys.path` insertion two directories short of `autobot-backend/` (landing on
`autobot-infrastructure/shared/`, which has no `utils` package). Both operator entry
points were unimportable.

Nothing caught either: `.pre-commit-config.yaml`'s flake8 hook excludes
`autobot-infrastructure/` entirely, so F821 never gated a commit here, and neither
script is imported by anything under test. "An import smoke test... would have caught
both on the commit that broke them" (#14129) — this is that smoke test, generalised to
the whole directory so the next regression is caught too, not just these two.

Two checks:

1. `test_script_has_no_undefined_names` — a static, per-file `flake8 --select=F821`
   sweep of every script in the tree. Cheap, catches names referenced but never
   imported/defined (the `manage_system_knowledge.py` class of bug). Pre-existing
   offenders beyond the two fixed here are tracked in `KNOWN_BROKEN_AT_GUARD_INTRODUCTION`
   with a reference to #14405 — fixing #14129 is not the same PR as fixing all of them.
2. `test_operator_script_imports_in_a_realistic_subprocess` — a genuine dynamic import,
   in a fresh subprocess with `autobot-backend` and the repo root (for `autobot_shared`)
   on PYTHONPATH (the convention every other script under this tree assumes; see
   `autobot-infrastructure/shared/scripts/restore_kb_backup.sh`), for the two scripts
   #14129 fixed. Catches a name that IS imported but does not exist in the target module
   (the `start_hardware_monitoring.py` class of bug) — undetectable by static analysis
   alone, since pyflakes never loads the module a `from X import Y` names.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _REPO_ROOT / "autobot-infrastructure" / "shared" / "scripts"
_BACKEND_DIR = _REPO_ROOT / "autobot-backend"

# Pre-existing undefined-name breakage found while introducing this guard, not fixed
# here (#14129 scoped its fix to the two scripts below). Remove an entry when its file
# is fixed and #14405 can drop the corresponding acceptance criterion.
KNOWN_BROKEN_AT_GUARD_INTRODUCTION: dict[str, str] = {
    "populate_knowledge_base.py": "#14405",
    "comprehensive_log_aggregator.py": "#14405",
    "seq_log_forwarder.py": "#14405",
    "profile_api_endpoints.py": "#14405",
    "diagnose_backend.py": "#14405",
    "analysis/test_gui_chat_visual.py": "#14405",
    "analysis/check_backend_status.py": "#14405",
    "analysis/test_llm_interface_direct.py": "#14405",
    "analysis/npu_performance_measurement.py": "#14405",
    "analysis/test_frontend_errors.py": "#14405",
    "utilities/report_processing_system.py": "#14405",
    "utilities/system_monitor.py": "#14405",
}

# The two scripts #14129 made importable. Exercised with a real subprocess import
# (Verification bar: "in a subprocess with a realistic path, not via a fixture that
# pre-stubs the missing name") rather than in-process importlib, which would let an
# already-imported `utils`/`knowledge`/`agents` module in the pytest session's own
# sys.modules mask a sys.path regression these scripts are prone to (#14129).
_OPERATOR_ENTRYPOINTS = (
    "utilities/manage_system_knowledge.py",
    "monitoring/start_hardware_monitoring.py",
)


def _discover_scripts() -> list[Path]:
    return sorted(p for p in _SCRIPTS_DIR.rglob("*.py") if "__pycache__" not in p.parts)


def _relative_key(path: Path) -> str:
    return str(path.relative_to(_SCRIPTS_DIR))


def _undefined_name_lines(path: Path) -> list[str]:
    """Every `flake8 --select=F821` finding for *path*, one per line.

    `--isolated`: the repo's own `.flake8` sets `count = True` / `statistics = True`
    for the pre-commit hook's human-readable output, which appends a bare count line
    (and, with findings, a summary line) after the real violations. Reading `.flake8`
    here would count every clean file as "broken" (its trailing ``0``).
    """
    result = subprocess.run(
        [sys.executable, "-m", "flake8", "--isolated", "--select=F821", str(path)],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        check=False,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def _script_params() -> list:
    params = []
    for path in _discover_scripts():
        key = _relative_key(path)
        marks = []
        if key in KNOWN_BROKEN_AT_GUARD_INTRODUCTION:
            marks.append(
                pytest.mark.xfail(
                    reason=f"tracked in {KNOWN_BROKEN_AT_GUARD_INTRODUCTION[key]}",
                    strict=True,
                )
            )
        params.append(pytest.param(path, id=key, marks=marks))
    return params


def test_the_guard_actually_found_scripts():
    """An empty discovery would make every parametrised check below vacuous."""
    assert len(_discover_scripts()) > 100


@pytest.mark.parametrize("path", _script_params())
def test_script_has_no_undefined_names(path: Path):
    """Every name a script references must be imported or defined somewhere in it.

    This is what `manage_system_knowledge.py` failed before #14129: `KnowledgeBase`,
    `SystemKnowledgeManager` and `yaml` were referenced inside function bodies with no
    corresponding import anywhere in the file.
    """
    undefined = _undefined_name_lines(path)
    assert undefined == [], "\n".join(undefined)


@pytest.mark.parametrize("relative_path", _OPERATOR_ENTRYPOINTS)
def test_operator_script_imports_in_a_realistic_subprocess(relative_path: str):
    """The script must actually import, with PYTHONPATH set the way every other
    script under this tree expects it (`autobot-backend` + the repo root, for
    `autobot_shared` — see restore_kb_backup.sh) — not via a fixture that stubs
    the name out.

    This is what `start_hardware_monitoring.py` failed before #14129:
    `from utils.hardware_metrics import start_phase9_monitoring` named a function
    that had been renamed to `start_hardware_monitoring` in #10666/#10733, and the
    script's own `sys.path` calculation landed two directories short of
    `autobot-backend/` regardless. Neither is visible to a static per-file check.
    """
    script = _SCRIPTS_DIR / relative_path
    assert script.is_file(), f"entrypoint moved or renamed: {script}"

    code = (
        "import importlib.util\n"
        f"spec = importlib.util.spec_from_file_location('operator_entrypoint', {str(script)!r})\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
    )
    # `autobot_shared.*` imports resolve off the repo ROOT (the package is
    # `autobot_shared/__init__.py`, not a `src`-layout); `autobot-backend` is
    # needed for `utils`/`knowledge`/`agents` (#14129).
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(_BACKEND_DIR), str(_REPO_ROOT), env.get("PYTHONPATH", "")])

    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
