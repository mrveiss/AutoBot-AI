# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard: every ``autobot_shared`` module imports under a fully mocked config manager (#19288).

Reproduces the SLM test harness: ``config`` is a ``MagicMock``, so every ``get_nested(...)`` the
logging manager makes returns a ``MagicMock``. Before #19288 that made ``get_logger(__name__)`` raise
at import, so a module calling it at module level broke every harness that imported it, and modules
took to stdlib ``logging`` to dodge it. The SLM-backend half of this guard is
``autobot-slm-backend/tests/stdlib_logging_ratchet_19288_test.py``, which runs under the SLM
interpreter.

Runs in CI's backend unit-test step: ci.yml passes ``autobot_shared`` to pytest and pytest.ini's
``python_files`` matches ``*_test.py``, so the 12-way stable shard places it in one of the shards.
"""

import json
from pathlib import Path

from repo_tests._mocked_config_import import REPO_ROOT, run_sweep

_PACKAGE = REPO_ROOT / "autobot_shared"

#: Modules that cannot be imported standalone, each with its reason. A module listed here is not
#: checked; keep the reason specific so the entry can be removed once it no longer holds.
_EXCLUDED: dict[str, str] = {}

#: Floor on the swept population. Measured 304 non-test modules (train 80 tree); window [254, 304],
#: pinned mid-window so ordinary growth or shrink does not force a re-pin (RATCHET_BASELINES.md).
#: The set comparison below is the real check; this only refuses a sweep that found next to nothing.
_FLOOR = 279


def _is_test(path: Path) -> bool:
    name = path.stem
    return name.endswith("_test") or name.startswith("test_") or name == "conftest" or "tests" in path.parts


def _modules_on_disk() -> set[str]:
    """The same population derived from the filesystem, not from pkgutil (RATCHET_BASELINES rule 3).

    A directory counts only when every directory from the package down carries ``__init__.py``,
    which is what ``pkgutil.walk_packages`` needs to descend into it.
    """
    found: set[str] = set()
    for path in _PACKAGE.rglob("*.py"):
        rel = path.relative_to(REPO_ROOT)
        package_dirs = (REPO_ROOT.joinpath(*rel.parts[:i]) for i in range(1, len(rel.parts)))
        if _is_test(rel) or not all((d / "__init__.py").exists() for d in package_dirs):
            continue
        parts = rel.with_suffix("").parts
        found.add(".".join(parts[:-1] if parts[-1] == "__init__" else parts))
    found.discard("autobot_shared")
    return found - set(_EXCLUDED)


def test_every_autobot_shared_module_imports_under_a_mocked_config(tmp_path: Path) -> None:
    report = run_sweep(tmp_path, excluded=tuple(_EXCLUDED))
    targets = report["targets"]
    assert isinstance(targets, list) and len(targets) >= _FLOOR, f"sweep found {len(targets)} modules"
    assert "autobot_shared.logging_manager" in targets, "known positive missing: the sweep is not walking"
    assert set(targets) == _modules_on_disk(), "pkgutil and the filesystem disagree on the population"
    assert report["failures"] == {}, json.dumps(report["failures"], indent=2)
