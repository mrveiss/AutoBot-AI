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
flips -- is mandatory and cannot run until the offenders are fixed (design B12,
S13.6). The first full run sized that list: 54 of 608 modules, frozen by tree and by
category in ``import_hermeticity_known_offenders.py`` and drained by #16262. A failure
that list does not name fails the sweep, with its tree, module, category and detail.
So does a listed entry the run probed that no longer fails that way -- a pull request
that fixes a listed module removes its entry in the same change, and the list only
shrinks. Entries a subset did not probe are judged by the next full run.

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
A ran" is not measuring hermeticity. The cost is paid in CI, and narrowed there:

* ``AUTOBOT_IMPORT_HERMETICITY_SWEEP`` unset -- only the controls and the pure-logic
  tests run. Six hundred interpreter startups do not fit the pre-push budget.
* set, with ``AUTOBOT_IMPORT_HERMETICITY_MODULES`` empty -- the whole population.
* set, with that variable holding newline-separated repo-relative paths -- those
  modules plus their direct importers (``_import_hermeticity_scope``). Every listed
  path must match a module, so a filter matching fewer paths than it was handed, or
  none, fails instead of reading as clean.

A subset cannot reach a module that gets to the changed one only through an
intermediate's *function* called at import time, nor the other gaps the scope module
lists; the full sweep on every push to Dev_new_gui does.
"""

from __future__ import annotations

import os
import subprocess  # nosec B404  # the sandboxed probe IS the subject of this guard
import sys
import tempfile
from collections.abc import Mapping, Sequence, Set
from pathlib import Path

import pytest
import yaml
from repo_tests import _import_hermeticity_scope as scope
from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests.import_hermeticity_known_offenders import DOES_NOT_IMPORT, HAS_IMPORT_EFFECT

_REPO_ROOT = repo_root()
_WORKFLOW = ".github/workflows/import-hermeticity-sweep.yml"
_BASELINE_FILE = "repo_tests/import_hermeticity_known_offenders.py"

#: Set by CI to run the sweep. Unset locally, only the controls run: a guard that
#: makes every push time out gets disabled within a week.
_SWEEP_ENV = "AUTOBOT_IMPORT_HERMETICITY_SWEEP"
#: Set by CI on a pull request to narrow the sweep; see the module docstring.
_MODULES_ENV = "AUTOBOT_IMPORT_HERMETICITY_MODULES"

#: Seconds for one module's import. Generous: this is a correctness gate, and a
#: module that takes longer than this to import is itself the finding.
_IMPORT_TIMEOUT_SECONDS = 60

#: The two debts the baseline keeps apart. A module that raises before any effect can
#: be observed is not side-effect debt, and must never read as it (#16262).
_HAS_EFFECT = "has an import effect"
_DOES_NOT_IMPORT = "does not import"
_Record = dict[str, str]
_Baseline = Mapping[str, frozenset[tuple[str, str]]]
_BASELINE: _Baseline = {_HAS_EFFECT: HAS_IMPORT_EFFECT, _DOES_NOT_IMPORT: DOES_NOT_IMPORT}
_FIX = {
    _HAS_EFFECT: "move the connect, spawn or write out of import time -- into a function, a startup hook, or first use",
    _DOES_NOT_IMPORT: "make it import from its own tree under the declared dependency set",
}

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


def _discover(root: Path) -> list[scope.Entry]:
    """The reach population: the same entries the sweep probes, from the scope module."""
    return scope.entries(root)


REACH = declare(
    "import-hermeticity",
    discover=_discover,
    # Measured, not felt (#16199 review): this population grows with ordinary work --
    # 504 modules at e47e4eb02 (~12 Jul), 556 at eef2b3a3e (~11 Aug), 608 on 10 Sep,
    # about 52 per 30 days. A band of 20 would fail an unrelated PR within days, so
    # growth covers a little over a month of that rate; the floor sits just under
    # today's count. Losing a whole root is caught separately: the population test
    # requires every root to contribute.
    floor=600,
    what="non-test modules under api/ and autobot_shared/, both backends",
    growth=60,
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


# ------------------------------------------------------------ records and the baseline


def _record(entry: scope.Entry, detail: str) -> _Record:
    """One failure, tree-qualified: without its tree, ``api.auth`` names two modules."""
    category = _HAS_EFFECT if "HERMETIC_VIOLATION" in detail else _DOES_NOT_IMPORT
    return {"tree": entry.tree, "module": entry.module, "category": category, "detail": detail}


def _line(record: Mapping[str, str]) -> str:
    return f"{record['tree']}  {record['module']}  [{record['category']}]  {record['detail']}"


def _unbaselined(records: Sequence[_Record], baseline: _Baseline) -> list[_Record]:
    """Failures the baseline does not list under the category they failed with."""
    return [r for r in records if (r["tree"], r["module"]) not in baseline.get(r["category"], frozenset())]


def _stale(
    records: Sequence[_Record], baseline: _Baseline, *, full: bool, probed: Set[tuple[str, str]]
) -> list[tuple[str, str, str]]:
    """``(tree, module, category)`` listed but not failing that way, among the entries judged.

    A full run judges every entry. A subset judges only the entries it probed: a pull
    request that fixes a listed module must drop its entry in the same change, or the
    full run after the merge goes red on the base. An entry a subset never probed is
    left to the full run -- its silence there is not evidence that it passes.
    """
    failing = {(r["tree"], r["module"], r["category"]) for r in records}
    listed = {(tree, module, category) for category, pairs in baseline.items() for tree, module in pairs}
    judged = listed if full else {entry for entry in listed if entry[:2] in probed}
    return sorted(judged - failing)


def _verdict(
    records: Sequence[_Record], baseline: _Baseline, *, full: bool, probed: Set[tuple[str, str]]
) -> str | None:
    """The failure message, or None when every failure is listed and nothing judged is stale."""
    parts: list[str] = []
    new = _unbaselined(records, baseline)
    if new:
        lines = "".join(f"\n  {_line(r)}\n      fix: {_FIX[r['category']]}" for r in new)
        parts.append(
            f"{len(new)} of {len(probed)} examined modules fail and are not in the baseline:{lines}\n"
            f"The baseline ({_BASELINE_FILE}) only shrinks: listing a new offender is not the fix (#16198)."
        )
    stale = _stale(records, baseline, full=full, probed=probed)
    if stale:
        lines = "".join(f"\n  {tree}  {module}  [{category}]" for tree, module, category in stale)
        parts.append(
            f"{len(stale)} baseline entries were examined and no longer fail that way -- remove each from "
            f"the baseline ({_BASELINE_FILE}) in this PR; the list only shrinks:{lines}"
        )
    return "\n\n".join(parts) or None


def _selection(root: Path, population: Sequence[scope.Entry], raw: str) -> list[scope.Entry]:
    """The whole population, or -- given paths -- those modules plus their direct importers.

    Every listed path must match a module. That equality is a subset's floor: a filter
    matching fewer paths than it was handed fails here, and so does one matching none.
    An empty list is a full run, never an empty one.
    """
    listed = scope.listed_paths(raw)
    if not listed:
        return list(population)
    matched = scope.matching(population, listed)
    unmatched = sorted(set(listed) - {entry.path for entry in matched})
    assert len(matched) == len(listed), (
        f"{_MODULES_ENV} listed {len(listed)} paths and {len(matched)} matched a swept module; "
        f"unmatched: {unmatched}"
    )
    return scope.with_direct_importers(root, population, matched)


def _sweep(examined: Sequence[scope.Entry]) -> list[_Record]:
    """Probe each module in its own sandboxed interpreter; one record per failure."""
    records: list[_Record] = []
    with tempfile.TemporaryDirectory() as tmp:
        sandbox = _sandbox(tmp)
        for entry in examined:
            ok, detail = _probe(entry.path_entry(_REPO_ROOT), entry.module, sandbox_dir=sandbox)
            if not ok:
                records.append(_record(entry, detail))
    return records


# --------------------------------------------------------------------- the controls


def test_the_population_is_large_enough_for_this_to_mean_anything() -> None:
    """A sweep that stopped matching would otherwise report a clean empty result."""
    population = _discover(_REPO_ROOT)
    assert len(population) >= REACH.floor, (
        f"only {len(population)} modules discovered against a floor of {REACH.floor} -- "
        "the sweep has narrowed and its clean result would mean nothing"
    )
    trees = {entry.tree for entry in population}
    expected = {tree for tree, _ in scope.ROOTS}
    assert trees == expected, f"expected all {len(expected)} roots to contribute, got {sorted(trees)}"


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


# ------------------------------------------------------------------------ the sweep


@pytest.mark.skipif(
    not os.environ.get(_SWEEP_ENV),
    reason=f"the sweep runs in CI; set {_SWEEP_ENV}=1 to run it locally, one interpreter per module",
)
def test_every_module_imports_inertly() -> None:
    """The sweep: the population, or a pull request's changed modules and their direct importers."""
    raw = os.environ.get(_MODULES_ENV, "")
    examined = _selection(_REPO_ROOT, REACH.examined(_REPO_ROOT), raw)
    records = _sweep(examined)
    probed = {(entry.tree, entry.module) for entry in examined}
    message = _verdict(records, _BASELINE, full=not scope.listed_paths(raw), probed=probed)
    assert message is None, message


# ---------------------------------------------------------------- which modules a diff reaches

#: Two backends and the shared root, with import edges whose answer is known.
_TREE = {
    "autobot-backend/api/__init__.py": "",
    "autobot-backend/api/a.py": "def f():\n    return 1\n",
    "autobot-backend/api/b.py": "from api.a import f\n",
    "autobot-backend/api/c.py": "from . import a\n",
    "autobot-backend/api/d.py": "import api.b\n",
    "autobot-backend/api/lazy.py": "def g():\n    import api.a\n",
    "autobot-backend/api/pkg/__init__.py": "from ..a import f\n",
    "autobot-backend/api/uses_shared.py": "from autobot_shared.x import y\n",
    "autobot-backend/api/a_test.py": "from api.a import f\n",
    "autobot-slm-backend/api/__init__.py": "",
    "autobot-slm-backend/api/a.py": "",
    "autobot-slm-backend/api/b.py": "from api.a import f\n",
    "autobot_shared/__init__.py": "",
    "autobot_shared/x.py": "y = 1\n",
}
_BACKEND, _SLM = "autobot-backend", "autobot-slm-backend"


def _plant(root: Path) -> list[scope.Entry]:
    for rel, text in _TREE.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return scope.entries(root)


def _selected(root: Path, raw: str) -> set[tuple[str, str]]:
    return {(entry.tree, entry.module) for entry in _selection(root, _plant(root), raw)}


def test_a_changed_module_selects_itself_and_its_direct_importers(tmp_path: Path) -> None:
    """Absolute, relative, parent-relative and function-level imports all count. An
    importer's importer (``api.d``) does not, nor does the SLM's ``api.b``, which
    imports a different ``api.a``."""
    expected = {(_BACKEND, name) for name in ("api.a", "api.b", "api.c", "api.lazy", "api.pkg")}
    assert _selected(tmp_path, "autobot-backend/api/a.py\n") == expected


def test_importers_resolve_in_their_own_tree_first_then_the_root(tmp_path: Path) -> None:
    assert _selected(tmp_path, "autobot-slm-backend/api/a.py") == {(_SLM, "api.a"), (_SLM, "api.b")}
    assert _selected(tmp_path, "autobot_shared/x.py") == {(".", "autobot_shared.x"), (_BACKEND, "api.uses_shared")}


@pytest.mark.parametrize(
    "raw",
    [
        "autobot-backend/api/a.py\nautobot-backend/api/gone.py",  # one of two matches
        "autobot-backend/api/a_test.py",  # a test file is not in the population
        "docs/README.md",  # matches nothing at all
    ],
)
def test_a_listed_path_matching_no_module_fails_rather_than_narrowing(tmp_path: Path, raw: str) -> None:
    """The subset's floor: fewer matches than paths handed over is a failure, never a smaller sweep."""
    with pytest.raises(AssertionError, match="matched a swept module"):
        _selection(tmp_path, _plant(tmp_path), raw)


def test_no_listed_paths_is_the_whole_population(tmp_path: Path) -> None:
    population = _plant(tmp_path)
    assert _selection(tmp_path, population, " \n\n") == population


def test_the_plan_is_full_on_the_sweep_itself_and_none_when_no_swept_module_changed(tmp_path: Path) -> None:
    population = _plant(tmp_path)
    assert scope.plan(["autobot-backend/api/a.py", _BASELINE_FILE], population) == ("full", [])
    unswept = ["autobot-backend/api/a_test.py", "autobot-backend/services/s.py", "requirements-ci.txt"]
    assert scope.plan(["autobot-backend/api/a.py", *unswept], population) == ("subset", ["autobot-backend/api/a.py"])
    assert scope.plan(unswept, population) == ("none", [])


def test_every_self_file_exists_and_triggers_the_workflow() -> None:
    """A self file the ``paths:`` filters omit could never force the full run it is listed to force."""
    doc = yaml.safe_load((_REPO_ROOT / _WORKFLOW).read_text(encoding="utf-8"))
    triggers = doc.get(True) or doc.get("on") or {}
    missing = [
        (event, path)
        for event in ("pull_request", "push")
        for path in sorted(scope.SELF_FILES)
        if path not in (triggers.get(event) or {}).get("paths", [])
    ]
    assert not missing, f"{_WORKFLOW}: these sweep files do not trigger it: {missing}"
    absent = sorted(path for path in scope.SELF_FILES if not (_REPO_ROOT / path).is_file())
    assert not absent, f"SELF_FILES names files that do not exist: {absent}"


# ------------------------------------------------------------ the baseline ratchet

_SOCKET = "RuntimeError: HERMETIC_VIOLATION socket.connect"
_MISSING = "ModuleNotFoundError: No module named 'utils'"
#: Synthetic, so the ratchet is proved on sets whose answer is known.
_KNOWN: _Baseline = {
    _HAS_EFFECT: frozenset({(_SLM, "api.auth")}),
    _DOES_NOT_IMPORT: frozenset({(".", "autobot_shared.facade")}),
}
_KNOWN_PAIRS = frozenset().union(*_KNOWN.values())


def _failure(tree: str, module: str, detail: str) -> _Record:
    return _record(scope.Entry(tree, module, f"{tree}/{module.replace('.', '/')}.py"), detail)


def test_a_failure_record_names_its_tree_and_category() -> None:
    """``api.auth`` is two modules; a record without its tree cannot say which (#16198)."""
    entry = scope.Entry(_SLM, "api.auth", "autobot-slm-backend/api/auth.py")
    assert _record(entry, _SOCKET) == {"tree": _SLM, "module": "api.auth", "category": _HAS_EFFECT, "detail": _SOCKET}
    assert _record(entry, _MISSING)["category"] == _DOES_NOT_IMPORT
    assert _record(entry, "TIMEOUT after 60s")["category"] == _DOES_NOT_IMPORT
    assert _line(_record(entry, _SOCKET)) == f"{_SLM}  api.auth  [{_HAS_EFFECT}]  {_SOCKET}"


def test_a_known_offender_passes_a_subset_and_a_full_run() -> None:
    records = [_failure(_SLM, "api.auth", _SOCKET), _failure(".", "autobot_shared.facade", _MISSING)]
    assert _verdict(records, _KNOWN, full=False, probed=_KNOWN_PAIRS) is None
    assert _verdict(records, _KNOWN, full=True, probed=_KNOWN_PAIRS) is None


def test_a_new_offender_fails_naming_its_tree_category_and_fix() -> None:
    """Same name as a listed module, other tree: new, because the pair is the identity."""
    probed = {(_BACKEND, "api.auth")}
    message = _verdict([_failure(_BACKEND, "api.auth", _SOCKET)], _KNOWN, full=False, probed=probed)
    assert message is not None
    assert f"{_BACKEND}  api.auth  [{_HAS_EFFECT}]  {_SOCKET}" in message
    assert _FIX[_HAS_EFFECT] in message and "not in the baseline" in message


def test_a_listed_module_failing_the_other_way_is_new() -> None:
    """A listed effect that now fails to import is a different debt, not the listed one."""
    records = [_failure(_SLM, "api.auth", _MISSING), _failure(".", "autobot_shared.facade", _MISSING)]
    assert _unbaselined(records, _KNOWN) == [records[0]]


def test_a_probed_entry_that_now_imports_cleanly_fails_a_subset() -> None:
    """The PR that fixes a listed module drops its entry, or the full run after the merge goes red."""
    records = [_failure(_SLM, "api.auth", _SOCKET)]  # the facade was probed and now imports
    assert _unbaselined(records, _KNOWN) == [], "a stale entry must not also read as a new offender"
    message = _verdict(records, _KNOWN, full=False, probed=_KNOWN_PAIRS)
    assert message is not None and "autobot_shared.facade" in message
    assert "in this PR; the list only shrinks" in message and "api.auth" not in message


def test_an_unprobed_stale_entry_passes_a_subset_and_fails_a_full_run() -> None:
    """A subset never examined it, so its silence proves nothing; the full run judges it."""
    records = [_failure(_SLM, "api.auth", _SOCKET)]  # the facade now imports, but was not probed
    assert _verdict(records, _KNOWN, full=False, probed={(_SLM, "api.auth")}) is None
    message = _verdict(records, _KNOWN, full=True, probed={(_SLM, "api.auth")})
    assert message is not None and "no longer fail" in message and "autobot_shared.facade" in message


def test_the_baseline_names_only_modules_in_the_population() -> None:
    """RATCHET_BASELINES rule 2: a pair that stops naming a swept module fails on every
    run, not only at the next full sweep -- and no module is two debts at once."""
    population = {(entry.tree, entry.module) for entry in _discover(_REPO_ROOT)}
    assert not HAS_IMPORT_EFFECT & DOES_NOT_IMPORT, "a module is listed in both categories"
    gone = sorted((HAS_IMPORT_EFFECT | DOES_NOT_IMPORT) - population)
    assert not gone, f"no longer in the population -- remove from {_BASELINE_FILE}, the list only shrinks: {gone}"
