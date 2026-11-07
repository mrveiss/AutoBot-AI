# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The indexing worker must win the `models` import against its own directory (#17631).

The worker lives beside a ``models.py``, and Python puts a script's own
directory at ``sys.path[0]``. The backend also ships a ``models/`` PACKAGE that
``services.provider_key_vault`` imports as ``models.secret``. Whichever of the
two is earlier on ``sys.path`` wins, and when the module wins, every indexing
run dies at import with ``'models' is not a package``.

These tests execute the REAL preamble out of ``indexing_worker.py`` -- not a
copy of the algorithm -- under the path conditions production actually has, so
reverting the fix fails them.
"""

import subprocess
import sys
from pathlib import Path

import pytest

_WORKER = Path(__file__).parent / "indexing_worker.py"
_BACKEND_ROOT = Path(__file__).parent.parent.parent
_SHARED_ROOT = _BACKEND_ROOT.parent / "autobot_shared"


def _preamble() -> str:
    """The worker's module-level path setup, verbatim, up to its first project import."""
    src = _WORKER.read_text(encoding="utf-8")
    marker = "from api.codebase_analytics.scanner import"
    assert marker in src, "worker no longer imports the scanner -- update this test's marker"
    return src.split(marker)[0]


def _run_preamble(extra_pythonpath: str) -> dict:
    """Run the preamble in a child whose sys.path[0] is the worker's directory.

    That is what a ``python .../indexing_worker.py`` invocation produces, and it
    is the condition the fix exists for. ``extra_pythonpath`` reproduces the
    service unit's own PYTHONPATH.
    """
    probe = (
        _preamble() + "\n" + "import importlib.util, json\n"
        "spec = importlib.util.find_spec('models')\n"
        "print(json.dumps({\n"
        "    'script_dir_on_path': str(Path(__file__).parent) in sys.path,\n"
        "    'first': sys.path[0],\n"
        "    'models_origin': (spec.origin or ''),\n"
        "    'models_is_package': bool(spec.submodule_search_locations),\n"
        "}))\n"
    )
    # Reproduce a SCRIPT run faithfully. `python -c` puts '' (cwd) at sys.path[0];
    # `python path/to/script.py` puts the SCRIPT'S DIRECTORY there. That difference
    # is the entire bug, so the probe must set it up explicitly or it measures
    # nothing -- an earlier version of this test passed against the reverted fix
    # for exactly that reason.
    # Reproduce a SCRIPT run faithfully, in two respects:
    #
    # 1. `python -c` puts '' (cwd) at sys.path[0]; `python path/to/script.py`
    #    puts the SCRIPT'S DIRECTORY there. That difference IS the bug, so the
    #    probe sets it explicitly -- an earlier version of this test omitted it
    #    and passed against the reverted fix, proving nothing.
    # 2. A real interpreter has already imported the stdlib by the time user
    #    code runs. The worker's directory also contains a `types.py` that
    #    shadows the stdlib `types`, so importing the stdlib AFTER putting that
    #    directory first breaks `import logging` itself -- an artifact of the
    #    probe, not of production. Warm the stdlib first, as startup would.
    warmup = "import logging, os, sys, re, enum, types, dataclasses, pathlib\n"
    probe = warmup + ("__file__ = %r\n" % str(_WORKER)) + ("sys.path.insert(0, %r)\n" % str(_WORKER.parent)) + probe
    env_path = extra_pythonpath
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        cwd=str(_BACKEND_ROOT),
        env={"PYTHONPATH": env_path, "PATH": "/usr/bin:/bin"},
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, f"preamble failed: {result.stderr[-2000:]}"
    import json as _json

    return _json.loads(result.stdout.strip().splitlines()[-1])


def test_the_test_can_see_the_shadowing_module() -> None:
    """Positive control. Without it, a pass below could mean the trap is gone."""
    assert (_WORKER.parent / "models.py").is_file(), (
        "api/codebase_analytics/models.py is gone -- the shadowing this guards "
        "against no longer exists, so these tests prove nothing. Delete them or "
        "re-point them at whatever shadows `models` now."
    )


@pytest.mark.parametrize(
    "pythonpath",
    [
        pytest.param("", id="no-PYTHONPATH (dev shell)"),
        pytest.param(
            f"{_BACKEND_ROOT}:{_BACKEND_ROOT}:{_SHARED_ROOT}:{_BACKEND_ROOT.parent}",
            id="service-unit PYTHONPATH (production)",
        ),
    ],
)
def test_models_resolves_to_the_package_not_the_sibling_module(pythonpath: str) -> None:
    """#17631: this failed ONLY in the production case, which is why it shipped.

    With the service unit's PYTHONPATH set, every root the worker wanted to
    insert was already present, so the old `if _p not in sys.path` guard skipped
    all three inserts and left the script directory first.
    """
    seen = _run_preamble(pythonpath)

    assert seen["models_is_package"], (
        "`models` resolved to a module, not a package -- "
        f"origin={seen['models_origin']}. provider_key_vault's "
        "`from models.secret import Secret` dies here and the indexing "
        "subprocess exits 1."
    )
    assert (
        "codebase_analytics" not in seen["models_origin"]
    ), f"`models` resolved inside the worker's own directory: {seen['models_origin']}"


def test_the_worker_directory_is_not_on_the_path() -> None:
    """The root cause, asserted directly rather than through its symptom."""
    seen = _run_preamble(f"{_BACKEND_ROOT}:{_SHARED_ROOT}:{_BACKEND_ROOT.parent}")
    assert not seen["script_dir_on_path"], (
        "the worker's own directory is still on sys.path; any module beside it " "can shadow a top-level package"
    )
    assert seen["first"] == str(_BACKEND_ROOT), f"backend root is not first on sys.path: {seen['first']}"
