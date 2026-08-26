# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Say, right beside the local test result, when the environment is below floor (#15091).

The point of failure this addresses is not a red run -- it is a green one.
A developer or agent runs the suite, sees it pass, and reads that as evidence
about the change. When the interpreter's packages are older than the versions
the repo declares, the pass is evidence about a different environment than the
one CI builds, and nothing said so.

``pytest_terminal_summary`` is the placement that matters: the banner lands
immediately after the pass/fail counts, which is the line actually read. A
report header would scroll away behind the run.

The banner never changes the exit status. The decision to warn rather than
fail is recorded in docs/developer/CLAUDE_WORKFLOW.md -- a box below floor is
still usable for ordinary work, and a gate that blocks every local run on this
box would be removed within a day.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CHECKER = _REPO_ROOT / "pipeline-scripts" / "check_dependency_floors.py"
_MODULE_NAME = "check_dependency_floors"


def _load_checker() -> ModuleType:
    """Load the checker by path, once.

    ``pipeline-scripts`` is not an importable package, and this plugin is
    imported from the rootdir conftest before ``pytest.ini``'s ``pythonpath``
    entries can be relied on, so it is loaded by location -- the same thing
    ``repo_tests/requirements_ci_drift_test.py`` does for the same reason.

    The ``sys.modules`` assignment before ``exec_module`` is required, not
    incidental: ``@dataclass`` resolves its annotations through
    ``sys.modules[cls.__module__]``, so a module executed without that key
    raises ``AttributeError: 'NoneType' object has no attribute '__dict__'``
    on import. Reusing an already-loaded module keeps the key stable across
    calls, which is what ``repo_tests/sys_modules_leak_guard.py`` wants.
    """
    cached = sys.modules.get(_MODULE_NAME)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _CHECKER)
    if spec is None or spec.loader is None:  # pragma: no cover - unreachable with the file present
        raise ImportError(f"cannot load the dependency floor checker from {_CHECKER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def pytest_terminal_summary(terminalreporter) -> None:
    """Report unsatisfied declared floors under the run's result counts."""
    checker = _load_checker()
    found, examined = checker.audit(_REPO_ROOT)
    if not found:
        return
    terminalreporter.write_sep("=", "environment is BELOW the declared dependency floors", red=True)
    for line in checker.render(found, examined):
        terminalreporter.write_line(line)
