# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15531 — a conftest stub shadowed a REAL, installed ``python_multipart``.

``autobot-slm-backend/conftest.py`` built a bare ``python_multipart`` module
carrying only ``__version__``/``__all__`` — no ``.multipart`` submodule — and
``setdefault``-ed it into ``sys.modules``. ``setdefault`` reads as "only if
absent", but this early nothing has imported the real package yet, so the key is
always free and the crippled stub always won. Every later
``from python_multipart.multipart import parse_options_header`` — starlette does
exactly that, so every ``import fastapi`` does — then died.

``tests/api/conftest.py`` had the repair, and skipped it: its branch asked
``if "python_multipart" not in sys.modules``, which the outer stub had just made
False. Presence is not usability, and ``setdefault`` cannot repair a broken
entry — the ``multipart`` branch beside it had the same two defects.

The visible cost was `Co-located Smoke / authz-and-selection`, which runs
``tests/api/test_collect_outdated_node_ids.py`` **alone** and is path-filtered on
``api/code_sync.py``, so it only runs when a PR touches that file — the failure
sat latent on the base branch between such PRs. Collection, not a test, is what
broke, so this guard checks collection.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT_CONFTEST = REPO_ROOT / "autobot-slm-backend/conftest.py"
API_CONFTEST = REPO_ROOT / "autobot-slm-backend/tests/api/conftest.py"
# The exact file `authz-and-selection` invokes, on its own.
CI_TARGET = "autobot-slm-backend/tests/api/test_collect_outdated_node_ids.py"

# Floor. A collection that reached nothing would exit 0 and prove nothing.
MIN_COLLECTED = 5


def test_the_conftests_this_guard_reads_are_where_it_thinks():
    """Floor first: a moved conftest must fail by name, not silently pass."""
    assert ROOT_CONFTEST.is_file(), f"FIX THE SWEEP: {ROOT_CONFTEST.name} not found"
    assert API_CONFTEST.is_file(), f"FIX THE SWEEP: {API_CONFTEST.name} not found"
    assert (REPO_ROOT / CI_TARGET).is_file(), f"FIX THE SWEEP: the CI target {CI_TARGET} moved"
    assert "python_multipart" in ROOT_CONFTEST.read_text(encoding="utf-8"), "FIX THE SWEEP: the stub block moved"


def test_the_root_stub_is_gated_on_the_real_package_being_absent():
    src = ROOT_CONFTEST.read_text(encoding="utf-8")
    assert "python_multipart" in src, "FIX THE SWEEP: the stub block moved"
    assert "import python_multipart as _real_python_multipart" in src, (
        "the python_multipart stub must be installed only when importing the real "
        "package fails — an unconditional setdefault shadows a working install (#15531)"
    )


def test_the_api_conftest_asks_whether_the_entry_is_usable_not_merely_present():
    src = API_CONFTEST.read_text(encoding="utf-8")
    assert "_stub_is_usable" in src, "FIX THE SWEEP: the usability predicate is gone"
    assert 'parse_options_header"' in src
    assert 'if "python_multipart" not in sys.modules:' not in src, (
        "presence is not usability: the outer conftest can occupy the key with a "
        "crippled module, and this branch would then skip the repair (#15531)"
    )
    assert (
        'sys.modules.setdefault("python_multipart"' not in src
    ), "setdefault cannot repair a broken entry — assign it (#15531)"


def test_the_ci_invocation_collects():
    """The end-to-end proof, in the shape CI runs it: that file, on its own.

    A subprocess is the point — the defect is import ordering inside a fresh
    interpreter, which cannot be reproduced from inside an already-imported one.
    """
    proc = subprocess.run(  # nosec B603  # fixed argv, no shell
        [sys.executable, "-m", "pytest", CI_TARGET, "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    combined = proc.stdout + proc.stderr
    assert "ModuleNotFoundError: No module named 'python_multipart.multipart'" not in combined, combined[-2000:]
    assert proc.returncode == 0, f"collection failed (rc={proc.returncode}):\n{combined[-2000:]}"

    match = re.search(r"(\d+) tests? collected", combined)
    assert match, f"FIX THE SWEEP: could not read a collected count from:\n{combined[-2000:]}"
    collected = int(match.group(1))
    assert collected >= MIN_COLLECTED, f"FIX THE SWEEP: only {collected} tests collected from {CI_TARGET}"


def test_the_probe_asks_about_the_import_that_actually_breaks():
    """#15531: probing only ``starlette.formparsers`` made the repair unreachable.

    ``formparsers`` imports the legacy ``multipart`` shim, which is installed on
    these hosts, so the probe answered "fine" while ``starlette.requests`` — the
    module ``import fastapi`` actually pulls — was failing on
    ``python_multipart.multipart``. The block below it therefore never ran once.
    """
    src = API_CONFTEST.read_text(encoding="utf-8")
    assert "_starlette_formparsers_import_works" in src, "FIX THE SWEEP: the probe was renamed or removed"
    assert "import starlette.requests" in src, (
        "the probe must cover starlette.requests, not just starlette.formparsers — "
        "otherwise the stub fallback is unreachable exactly when it is needed (#15531)"
    )
