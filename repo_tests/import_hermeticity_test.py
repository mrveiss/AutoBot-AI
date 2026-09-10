# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every module under ``api/`` and ``autobot_shared/`` must import inertly (#16198).

The third member of an existing family. ``collected_modules_inert_on_import_test``
asks whether a module calls ``sys.exit`` at import and ``first_party_imports_resolve_test``
asks whether its imports resolve -- both by reading the source. This one asks the
question neither can: **does the module actually import, and does it do anything on
the way?** That needs a real import, in a real interpreter, and the two static
guards cannot answer it.

It exists because #13539's V5 -- a fresh-interpreter import sweep before a release
flips -- is mandatory and cannot run until the offenders are fixed, and **the
offender list is unbounded until this guard runs once** (design B12, S13.6). Every
other piece of that work can be estimated. This one sizes itself, which is why the
design puts it first.

**The sandbox is what makes running it safe.** Each import happens in a subprocess
whose generated ``sitecustomize`` installs a ``sys.addaudithook`` handler that
*raises* on ``socket.connect``, ``subprocess.Popen``, ``os.system`` and on writes
outside the tree. A module with an import-time side effect therefore fails the
probe **instead of performing the side effect** -- no DB, no Redis, no network, and
no risk in running the sweep on a developer machine. That property is load-bearing:
one module in this repository starts an Ollama client at import (#16188).

**One module per interpreter, deliberately.** Batching would be ~40x faster and
would break the property being asserted: module A's import can leave ``sys.modules``
entries, monkeypatches or registered atexit handlers that change whether module B
imports cleanly. A sweep that cannot distinguish "B is inert" from "B is inert after
A ran" is not measuring hermeticity. The cost is real and is paid in CI rather than
in the pre-push budget -- see ``_SWEEP_ENV``.
"""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404  # the sandboxed probe IS the subject of this guard
import sys
import tempfile
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

_REPO_ROOT = repo_root()

#: ``(sys.path entry relative to the repo root, package directory)``. Each backend
#: puts its own directory on ``sys.path``, so ``api`` means a different package in
#: each -- which is exactly why both are swept rather than one standing in for both.
_ROOTS: tuple[tuple[str, str], ...] = (
    ("autobot-backend", "api"),
    ("autobot-slm-backend", "api"),
    (".", "autobot_shared"),
)

#: Set by CI to run the full sweep. Unset locally, only the controls run: 606
#: interpreter startups do not fit the pre-push budget, and a guard that makes
#: every push time out gets disabled within a week.
_SWEEP_ENV = "AUTOBOT_IMPORT_HERMETICITY_SWEEP"

#: Seconds for one module's import. Generous: this is a correctness gate, and a
#: module that takes longer than this to import is itself the finding.
_IMPORT_TIMEOUT_SECONDS = 60

_SANDBOX = """
import sys, os

_TREE = {tree!r}

def _outside_tree(path):
    # Separator-boundary, not a bare prefix: "<tree>-malicious/evil" starts with
    # "<tree>" and is NOT in it. This repo names worktrees "<repo>-<slug>", so the
    # sibling that defeats a prefix check is a shape it actually produces.
    try:
        p = os.path.abspath(path)
    except Exception:
        return False
    return p != _TREE and not p.startswith(_TREE + os.sep)


def _is_write(mode, flags):
    # `open()` reports a mode string; `os.open()` reports mode=None and puts the
    # intent in flags. Checking only mode lets every os.open write through.
    if mode:
        return any(c in str(mode) for c in "wxa+")
    try:
        f = int(flags)
    except (TypeError, ValueError):
        return False
    return bool(f & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC))

def _hook(event, args):
    if event == "socket.connect":
        raise RuntimeError("HERMETIC_VIOLATION socket.connect")
    if event in ("subprocess.Popen", "os.system", "os.exec", "os.spawn", "os.posix_spawn"):
        raise RuntimeError("HERMETIC_VIOLATION " + event)
    if event == "open" and len(args) >= 2:
        path, mode = args[0], args[1]
        flags = args[2] if len(args) > 2 else None
        if _is_write(mode, flags) and _outside_tree(path):
            raise RuntimeError("HERMETIC_VIOLATION write outside tree: %s" % (path,))

sys.addaudithook(_hook)
"""


def _module_name(package: str, path: Path, package_dir: Path) -> str:
    """Dotted name for *path*, which lives under *package_dir*."""
    rel = path.relative_to(package_dir)
    parts = [package] + list(rel.parts)
    if parts[-1] == "__init__.py":
        parts.pop()
    else:
        parts[-1] = parts[-1][: -len(".py")]
    return ".".join(parts)


def _discover(root: Path) -> list[tuple[str, str]]:
    """``(sys.path entry, dotted module)`` for every non-test module in scope.

    Returns an empty list on a tree that holds none, and never raises: the reach
    meta-test hands every declaration an empty repository to prove the floor can
    actually fire (#16154).
    """
    found: list[tuple[str, str]] = []
    for base, package in _ROOTS:
        package_dir = (root / package) if base == "." else (root / base / package)
        if not package_dir.is_dir():
            continue
        path_entry = str(root if base == "." else root / base)
        for path in sorted(package_dir.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            if path.name.endswith("_test.py") or path.name.startswith("test_"):
                continue
            found.append((path_entry, _module_name(package, path, package_dir)))
    return found


REACH = declare(
    "import-hermeticity",
    discover=_discover,
    floor=590,
    what="non-test modules under api/ and autobot_shared/, both backends",
    growth=20,
)


def _probe(path_entry: str, module: str, *, sandbox_dir: str) -> tuple[bool, str]:
    """Import *module* in a fresh sandboxed interpreter. ``(ok, detail)``."""
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("GIT_", "PYTHON"))  # inherited state must not decide the answer
    }
    env["PYTHONPATH"] = os.pathsep.join([sandbox_dir, path_entry, str(_REPO_ROOT)])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        done = subprocess.run(  # nosec B603  # fixed argv, no shell
            [sys.executable, "-c", f"import {module}"],
            cwd=str(_REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=_IMPORT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False, f"TIMEOUT after {_IMPORT_TIMEOUT_SECONDS}s"
    if done.returncode == 0:
        return True, ""
    tail = (done.stderr or done.stdout or "").strip().splitlines()
    return False, tail[-1] if tail else f"exit {done.returncode} with no output"


def _sandbox(tmp: str) -> str:
    Path(tmp, "sitecustomize.py").write_text(_SANDBOX.format(tree=str(_REPO_ROOT)), encoding="utf-8")
    return tmp


def test_the_population_is_large_enough_for_this_to_mean_anything() -> None:
    """A sweep that stopped matching would otherwise report a clean empty result."""
    population = _discover(_REPO_ROOT)
    assert len(population) >= REACH.floor, (
        f"only {len(population)} modules discovered against a floor of {REACH.floor} -- "
        "the sweep has narrowed and its clean result would mean nothing"
    )
    entries = {entry for entry, _ in population}
    assert len(entries) == len(_ROOTS), f"expected all {len(_ROOTS)} roots to contribute, got {entries}"


def test_the_sandbox_catches_a_planted_side_effect() -> None:
    """The detector must fail a module that reaches the network at import.

    Without this, a sandbox that installed no hook -- or hooked an event name that
    does not exist -- would report every module clean and read as a green guard.
    """
    with tempfile.TemporaryDirectory() as tmp:
        sandbox = _sandbox(tmp)
        planted = Path(tmp, "planted_offender.py")
        planted.write_text(
            "import socket\nsocket.create_connection(('127.0.0.1', 9), timeout=1)\n",
            encoding="utf-8",
        )
        ok, detail = _probe(tmp, "planted_offender", sandbox_dir=sandbox)
    assert not ok, "a module opening a socket at import was reported hermetic"
    assert (
        "HERMETIC_VIOLATION" in detail or "socket" in detail.lower()
    ), f"caught it, but not as a hermeticity violation: {detail}"


def test_an_inert_module_passes() -> None:
    """The contrast: the detector must not fail everything it is shown."""
    with tempfile.TemporaryDirectory() as tmp:
        sandbox = _sandbox(tmp)
        Path(tmp, "planted_inert.py").write_text("VALUE = 1\n", encoding="utf-8")
        ok, detail = _probe(tmp, "planted_inert", sandbox_dir=sandbox)
    assert ok, f"an inert module was reported as a violation: {detail}"


def test_a_write_through_os_open_is_caught() -> None:
    """`os.open` reports mode=None, so a mode-only check lets every one of them through.

    Found by review: `os.open(path, O_WRONLY|O_CREAT)` outside the tree exited 0 while
    the equivalent `open(path, "w")` raised. Two spellings of the same act, one caught.
    """
    with tempfile.TemporaryDirectory() as tmp:
        sandbox = _sandbox(tmp)
        target = str(Path(tempfile.gettempdir(), "hermeticity_probe_os_open.tmp"))
        Path(tmp, "planted_os_open.py").write_text(
            "import os\n" f"os.open({target!r}, os.O_WRONLY | os.O_CREAT)\n", encoding="utf-8"
        )
        ok, detail = _probe(tmp, "planted_os_open", sandbox_dir=sandbox)
    assert not ok, "a write via os.open outside the tree was reported hermetic"
    assert "HERMETIC_VIOLATION" in detail, f"caught, but not as a hermeticity violation: {detail}"


def test_a_sibling_directory_is_outside_the_tree() -> None:
    """A bare prefix check calls `<tree>-malicious/` inside the tree, because it is a prefix.

    Not hypothetical here: this repository names worktrees `<repo>-<slug>`, so the
    sibling that defeats a prefix check is a path shape it actually produces.
    """
    sibling = str(_REPO_ROOT) + "-sibling"
    assert not str(_REPO_ROOT).endswith(os.sep), "repo root should not carry a trailing separator"
    # NOT `sibling.startswith(_REPO_ROOT)` -- true by construction, so it asserts
    # nothing. The property that makes this fixture discriminating is the opposite:
    # a string prefix that is NOT a child. If it ever became a child, the test would
    # pass for the wrong reason.
    assert not sibling.startswith(
        str(_REPO_ROOT) + os.sep
    ), "the fixture must be a sibling, not a child, or it does not test the prefix case"
    with tempfile.TemporaryDirectory() as tmp:
        sandbox = _sandbox(tmp)
        Path(tmp, "planted_sibling.py").write_text(
            "import os\n" f"open(os.path.join({sibling!r}, 'x.tmp'), 'w')\n", encoding="utf-8"
        )
        ok, detail = _probe(tmp, "planted_sibling", sandbox_dir=sandbox)
    assert not ok, "a write to a prefix-sibling of the tree was reported hermetic"
    assert "HERMETIC_VIOLATION" in detail, f"caught, but not as a hermeticity violation: {detail}"


def test_an_unimportable_module_fails_loudly_rather_than_reading_as_clean() -> None:
    """*Did not look* and *looked and found nothing* must not share an outcome."""
    with tempfile.TemporaryDirectory() as tmp:
        sandbox = _sandbox(tmp)
        Path(tmp, "planted_broken.py").write_text("import a_module_that_does_not_exist\n", encoding="utf-8")
        ok, detail = _probe(tmp, "planted_broken", sandbox_dir=sandbox)
    assert not ok, "a module that cannot be imported was reported as importing cleanly"
    assert (
        "ModuleNotFoundError" in detail or "No module named" in detail
    ), f"failed, but the reason is not legible: {detail}"


@pytest.mark.skipif(
    not os.environ.get(_SWEEP_ENV),
    reason=f"full sweep runs in CI; set {_SWEEP_ENV}=1 to run all 606 imports locally",
)
def test_every_module_imports_inertly() -> None:
    """The sweep. Its first run's offender list is the deliverable (#16198)."""
    population = _discover(_REPO_ROOT)
    offenders: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory() as tmp:
        sandbox = _sandbox(tmp)
        for path_entry, module in population:
            ok, detail = _probe(path_entry, module, sandbox_dir=sandbox)
            if not ok:
                offenders.append({"module": module, "detail": detail})
    assert not offenders, f"{len(offenders)} of {len(population)} modules do not import inertly.\n" + json.dumps(
        offenders, indent=2
    )
