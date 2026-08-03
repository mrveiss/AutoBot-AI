# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Repo-wide pytest plugin: catch ``sys.modules`` stubs that escape their directory.

Three conftest/test-module stub leaks were found in two days, all the same
shape — a module-level ``sys.modules`` mutation whose cleanup was not
guaranteed on every path — and each one produced failures that looked like
product bugs somewhere else entirely:

* ``autobot-backend/llc/tests/conftest.py`` installed an ``agents`` stub at
  import time and restored it only at package teardown, so anything importing
  ``initialization.lifespan`` inside that window died with
  ``ModuleNotFoundError: No module named 'agents.overseer'`` (#13337);
* ``autobot-slm-backend/conftest.py`` stubbed ``sqlalchemy`` as a ``MagicMock``
  in every process including the xdist **controller**, which then crashed with
  ``INTERNALERROR`` while rebuilding a worker warning and lost an entire
  session's results (#13320);
* two RBAC test modules replaced ``autobot_shared`` with a bare ``MagicMock``
  and never restored it because ``exec_module()`` raised before the restore
  line, producing **13 of 14** apparent security-cluster failures (#13324).

The rule this plugin enforces is the one all three break:

    A stub installed by a conftest or test module under directory *D* must not
    still be live while pytest imports or runs anything outside *D*.

That rule is deliberately narrow.  A conftest legitimately stubs heavy
dependencies for its own subtree — ``autobot-backend/conftest.py`` does it for
the whole backend — and this plugin says nothing about those, because the owner
directory covers every node they affect.  It fires only when a stub reaches
across into a sibling.

Only *suspicious* mutations are tracked, so an ordinary import never registers:

* **replaced** — the key was already in ``sys.modules`` bound to a different
  object, i.e. something swapped a real module out;
* **synthetic** — the new entry has no ``__spec__``, which is true of
  ``types.ModuleType(...)`` hand-built stubs and of ``MagicMock``, and never of
  a module the import system loaded.

Configuration (env var ``AUTOBOT_SYSMODULES_GUARD``):

``report``  default — warn, and print a dedicated terminal section
``error``   also fail the session with a non-zero exit status
``off``     disable entirely
"""

from __future__ import annotations

import os
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pytest

_MODE_ENV = "AUTOBOT_SYSMODULES_GUARD"
_MODE_OFF = "off"
_MODE_ERROR = "error"

_SECTION_TITLE = "sys.modules leak guard"
_KEYS_PER_OWNER = 8


def _mode() -> str:
    return os.environ.get(_MODE_ENV, "report").strip().lower()


@dataclass(frozen=True)
class _Mutation:
    """A suspicious ``sys.modules`` entry and the file that installed it."""

    key: str
    kind: str  # "replaced" or "synthetic"
    owner: str  # display path of the conftest / test module
    owner_dir: Path
    owner_dir_display: str
    obj_id: int
    # ``owner_dir.parents`` as a set, built once here rather than on every
    # comparison.  ``Path.parents`` is a lazy sequence with no ``__contains__``,
    # so ``x in path.parents`` walks it and constructs a fresh ``Path`` per
    # level; at ~66 tracked stubs times ~1200 checks that was 640k throwaway
    # ``Path`` objects and the single most expensive thing the guard did.
    owner_ancestors: frozenset[Path]

    def is_live(self) -> bool:
        """True while the installed object is still the one in ``sys.modules``."""
        return id(sys.modules.get(self.key)) == self.obj_id

    def escapes_to(self, path: Path | None, path_parents: frozenset[Path]) -> bool:
        """True when *path* is outside the directory that owns this stub.

        A strict *ancestor* directory is not an escape, and treating it as one
        made ``error`` mode unusable.  Pytest builds a ``Dir`` collector for
        every level from the rootdir down, so a session confined entirely to
        ``autobot-backend/`` still collects the rootdir node ``.``; that node
        imports nothing itself, it only lists its children, so a stub being
        live while it runs reaches nothing.  Reporting it fired on every clean
        session, and — because :meth:`_LeakGuard.check` dedupes per
        ``(key, owner)`` and the ancestor node always runs first — it also
        stole the ``first seen at`` slot from the sibling that actually
        inherited the stub, discarding the actionable half of the report.

        Only *directories* are exempted.  A file sitting directly in an
        ancestor directory is never a member of ``owner_dir.parents``, so
        sibling modules one level up are still checked.

        *path_parents* is ``path.parents`` as a set; the caller builds it once
        per check and shares it across every tracked mutation.
        """
        if path is None:
            return False
        if path == self.owner_dir or self.owner_dir in path_parents:
            return False  # inside the owner's own subtree
        if path in self.owner_ancestors:
            return False  # a structural ancestor Dir node imports nothing
        return True


@dataclass(frozen=True)
class _Leak:
    """A live mutation observed while pytest worked outside its owner."""

    mutation: _Mutation
    observed_at: str

    def describe(self) -> str:
        return (
            f"sys.modules[{self.mutation.key!r}] was {self.mutation.kind} by "
            f"{self.mutation.owner} and is STILL INSTALLED while pytest handles "
            f"{self.observed_at} — outside {self.mutation.owner_dir_display}/. "
            f"Install and remove the stub in the same try/finally, scoped to the "
            f"nodes that need it."
        )

    def as_record(self) -> dict:
        """A plain-dict form that survives the xdist worker->controller hop."""
        return {
            "key": self.mutation.key,
            "kind": self.mutation.kind,
            "owner": self.mutation.owner,
            "owner_dir_display": self.mutation.owner_dir_display,
            "observed_at": self.observed_at,
        }


def _is_synthetic(module: object) -> bool:
    """True for hand-built module stubs and mocks, false for real imports."""
    return getattr(module, "__spec__", None) is None


def _is_conftest_module(module: object) -> bool:
    """True when *module* is a conftest pytest loaded, not a stub of anything.

    Without ``--import-mode=importlib`` pytest registers every ``conftest.py``
    under the bare name ``conftest``, so each new one *replaces* the last and
    looks exactly like a module swap.  It is pytest's own bookkeeping and must
    never be reported (caught by the nested-session tests, which run a scratch
    repo in the default import mode).
    """
    origin = getattr(module, "__file__", None)
    return bool(origin) and os.path.basename(str(origin)) == "conftest.py"


# Distinguishes "this key was absent from the baseline" from "it was present
# and bound to ``None``" — ``sys.modules[name] = None`` is legal and is used to
# block an import, so ``None`` cannot serve as the missing marker.
_MISSING = object()

_DISK_CACHE: dict[str, bool] = {}


def _resolves_on_disk(top_level: str) -> bool:
    """True when *top_level* names a real module or package somewhere on sys.path.

    Deliberately a filesystem probe and not ``importlib.util.find_spec``:
    ``find_spec`` imports parent packages and consults ``sys.modules``, which
    would both re-run the very import machinery this guard watches and simply
    find the stub.  Results are cached — a session asks about a few dozen names.
    """
    cached = _DISK_CACHE.get(top_level)
    if cached is not None:
        return cached
    found = False
    for entry in sys.path:
        base = Path(entry or ".")
        if (base / f"{top_level}.py").is_file() or (base / top_level).is_dir():
            found = True
            break
    _DISK_CACHE[top_level] = found
    return found


def _display(path: Path, rootdir: Path) -> str:
    try:
        return str(path.relative_to(rootdir))
    except ValueError:
        return path.name


class _LeakGuard:
    """Track suspicious ``sys.modules`` mutations and where they escape to."""

    def __init__(self, rootdir: Path) -> None:
        self._rootdir = rootdir
        self._baseline: dict[str, object] = {}
        self._tracked: dict[str, _Mutation] = {}
        self._reported: set[tuple[str, str]] = set()
        self._warned_owners: set[str] = set()
        self.leaks: list[_Leak] = []

    @property
    def rootdir(self) -> Path:
        """The repo root every reported path is displayed relative to."""
        return self._rootdir

    def snapshot(self) -> None:
        """Re-baseline. Everything after this point is attributable.

        The baseline stores the module objects and comparison is by identity.
        Building ``{name: id(mod)}`` instead ran a Python-level comprehension
        over every entry ``sys.modules`` holds — ~3600 in an
        ``autobot-backend`` session — on every collector and every test, and
        measured 1.028 ms against 0.087 ms for the plain copy.

        ``sys.modules.copy()`` and never a live view: ``dict.copy()`` is a
        single C-level operation and cannot be torn, whereas iterating
        ``sys.modules.items()`` races with any import happening on another
        thread.  The suite has plenty — the analytics/celery task tests spawn
        them — and the loser of that race is a ``RuntimeError: dictionary
        changed size during iteration`` raised inside a hook, which under xdist
        kills the worker and takes the session down with ``INTERNALERROR``.
        """
        self._baseline = sys.modules.copy()

    def attribute(self, owner_file: Path) -> None:
        """Record the suspicious part of the delta since the last snapshot.

        *owner_file* may be a file (a conftest or a test module) or a directory
        (a ``Dir``/``Package`` collector, which is where a hook-installed stub
        is attributed).  The owning *directory* is the file's parent in the
        first case and the path itself in the second — taking ``.parent``
        unconditionally would blame the level above and make every stub look
        like it never escapes.
        """
        if self._matches_baseline():
            return
        current = sys.modules.copy()
        changed = self._changed_since(current)
        self._baseline = current
        if not changed:
            return
        owner = _display(owner_file, self._rootdir)
        owner_dir = owner_file if owner_file.is_dir() else owner_file.parent
        owner_dir_display = _display(owner_dir, self._rootdir)
        owner_ancestors = frozenset(owner_dir.parents)
        for name, module, previous in changed:
            kind = self._classify(name, module, previous)
            if kind is None:
                continue
            self._tracked[name] = _Mutation(
                key=name,
                kind=kind,
                owner=owner,
                owner_dir=owner_dir,
                owner_dir_display=owner_dir_display,
                obj_id=id(module),
                owner_ancestors=owner_ancestors,
            )

    def _matches_baseline(self) -> bool:
        """True when nothing in ``sys.modules`` moved since the last baseline.

        Most collectors import nothing — every ``Class`` node, every directory
        that only lists its children — and this answers them with one C-level
        dict comparison instead of a copy plus a Python pass over every entry
        (0.065 ms against 0.390 ms at 3600 entries).  Under xdist every worker
        collects the whole suite, so this is the guard's most repeated call.

        CPython compares dict values with an identity short-circuit, so equal
        entries never reach a user-defined ``__eq__``.  A *differing* entry
        can, a Python ``__eq__`` can release the GIL, and a concurrent import
        then makes the comparison raise; falling back to ``False`` runs the
        full copy-and-scan below, which is the correct answer either way.
        """
        try:
            return sys.modules == self._baseline
        except Exception:  # noqa: BLE001 - any failure just means "do the full scan"
            return False

    def _changed_since(self, current: dict[str, object]) -> list[tuple[str, object, object]]:
        """Entries that are new or now bound to a different object.

        This is the whole plugin's hot path — one pass over every entry
        ``sys.modules`` holds, on every collector and every test — so it stays
        free of Python-level calls: a C ``dict.get`` and an identity compare
        per entry, inside a comprehension rather than a statement loop
        (measured 0.290 ms against 0.385 ms at 3600 entries).  Handing every
        module to ``_classify`` instead called it 443,487 times for a
        103-test session, since only a handful of keys ever change while the
        scan has to cover all of them.

        The bindings are gathered in a second pass because the first has to
        stay as narrow as possible and the second runs over the 0-5 names that
        actually changed.
        """
        previous_of = self._baseline.get
        changed = [name for name, module in current.items() if previous_of(name, _MISSING) is not module]
        return [(name, current[name], previous_of(name, _MISSING)) for name in changed]

    def _classify(self, name: str, module: object, previous: object) -> str | None:
        """Return ``"replaced"``/``"synthetic"`` for a suspicious changed entry.

        *previous* is what the baseline had bound to *name*, or ``_MISSING``
        when the key is new.  It is passed in rather than looked up because
        the caller has already re-baselined by the time this runs.

        The first test is an equivalence, not a new rule: a brand-new key
        holding a module with a ``__spec__`` is an ordinary import, which the
        final line already answered ``None`` for.  Answering it up front skips
        a ``__file__`` probe and a ``sys.path`` walk for the large majority of
        changed entries, which are exactly that.
        """
        if previous is _MISSING and not _is_synthetic(module):
            return None
        if _is_conftest_module(module):
            return None  # pytest's own bookkeeping, not a stub
        if not self._shadows_real_code(name):
            return None
        if previous is not _MISSING:
            return "replaced"
        return "synthetic" if _is_synthetic(module) else None

    def _shadows_real_code(self, name: str) -> bool:
        """True when a synthetic entry could be hiding something that exists.

        Two families of ``sys.modules`` entry look exactly like a hand-built
        stub — no ``__spec__``, no ``__loader__``, no ``__file__`` — but are
        nothing of the kind: C-extension pseudo-modules registered by cffi and
        Cython (``_openssl``, ``cython_runtime``, ``_cython_3_2_1``) and
        extension submodules (``_sodium.lib``, ``xml.parsers.expat.errors``).

        What separates a stub from those is not how it was built but what it
        stands in front of: a stub shadows a real module that is installed, so
        some other test can import the wrong thing.  Nothing is importable
        under those extension names, so nothing can be shadowed, and a stub for
        a package that is not installed at all (``torch`` here) cannot break an
        importer either.  Submodules follow their parent.

        The same test gates *replacements*, not just synthetic entries.  A test
        that loads a script through ``spec_from_file_location`` under a
        made-up top-level name and re-registers it per run
        (``zero_downtime_deploy_under_test``) reads as a replacement, but there
        is no such module on disk for it to shadow, so nothing can collide with
        it.  The three historical leaks all shadow installed packages
        (``sqlalchemy``, ``autobot_shared``, ``agents``) and are unaffected.
        """
        parent_name, _, _ = name.rpartition(".")
        if parent_name:
            return parent_name in self._tracked or _resolves_on_disk(parent_name)
        return _resolves_on_disk(name)

    def check(self, path: Path | None, observed_at: str) -> None:
        """Report every tracked stub still live while pytest works on *path*.

        ``path.parents`` is materialised once here and shared with every
        tracked mutation rather than rebuilt inside each comparison.
        """
        if not self._tracked:
            return
        path_parents = frozenset(path.parents) if path is not None else frozenset()
        for mutation in list(self._tracked.values()):
            if not mutation.is_live():
                self._tracked.pop(mutation.key, None)
                continue
            if not mutation.escapes_to(path, path_parents):
                continue
            token = (mutation.key, mutation.owner)
            if token in self._reported:
                continue
            self._reported.add(token)
            leak = _Leak(mutation=mutation, observed_at=observed_at)
            self.leaks.append(leak)
            self._warn_once_per_owner(leak)

    def _warn_once_per_owner(self, leak: _Leak) -> None:
        """Warn on the first key each owner leaks, not on all of them.

        One escaping conftest routinely drags dozens of keys with it
        (``autobot-backend/conftest.py`` alone leaks 60+ into ``repo_tests``),
        and a warning per key buries the finding it is meant to surface.  The
        full key list still reaches the terminal section.
        """
        if leak.mutation.owner in self._warned_owners:
            return
        self._warned_owners.add(leak.mutation.owner)
        warnings.warn(leak.describe(), _SysModulesLeakWarning, stacklevel=1)

    def records(self) -> list[dict]:
        """Every leak in transport form, in first-seen order."""
        return [leak.as_record() for leak in self.leaks]


class _SysModulesLeakWarning(pytest.PytestWarning):
    """Emitted when a conftest stub is live outside the directory that owns it.

    Its ``__module__`` must stay honest.  xdist rebuilds worker warnings on the
    controller through ``unserialize_warning_message``, which does
    ``getattr(importlib.import_module(module), class_name)`` on the pair the
    worker sent.  Claiming ``__module__ = "pytest"`` sends
    ``("pytest", "_SysModulesLeakWarning")``, the controller raises
    ``AttributeError: module 'pytest' has no attribute
    '_SysModulesLeakWarning'``, the node goes down and the session dies with
    ``INTERNALERROR`` — the very #13320 failure mode this guard exists to
    prevent, reintroduced by the guard.  The real module is importable on the
    controller (the rootdir conftest loads this plugin there too), so the
    honest pair round-trips.  Subclass-based ``filterwarnings`` entries such as
    ``always::pytest.PytestWarning`` match on the class hierarchy and are
    unaffected by ``__module__``.
    """


# ---------------------------------------------------------------------------
# pytest hooks
# ---------------------------------------------------------------------------

# The repo root, derived from this file's own location — never hard-coded, so
# moving the checkout or the machine cannot strand the guard.
_REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_guard() -> _LeakGuard | None:
    """Build the guard at *import* time, before any other conftest loads.

    ``pytest_configure`` is far too late: pytest loads the conftest of every
    initial argument path during ``pytest_load_initial_conftests``, which runs
    before configure, so a guard created there would miss exactly the
    import-time conftest mutations it exists to catch.  The rootdir conftest
    pulls this module in through ``pytest_plugins``, and the rootdir conftest is
    an ancestor of every argument, so this runs first.
    """
    if _mode() == _MODE_OFF:
        return None
    guard = _LeakGuard(_REPO_ROOT)
    guard.snapshot()
    return guard


_GUARD: _LeakGuard | None = _make_guard()


def pytest_configure(config: pytest.Config) -> None:
    """Keep the guard's warnings visible even under a strict filter set."""
    if _GUARD is None:
        return
    config.addinivalue_line("filterwarnings", f"always::{__name__}.{_SysModulesLeakWarning.__name__}")


def pytest_plugin_registered(plugin: object, manager: object) -> None:
    """Attribute the ``sys.modules`` delta of a freshly-imported conftest.

    conftest modules are registered as plugins the moment they finish
    executing, and pytest imports them one at a time, so the delta since the
    previous attribution point belongs to this file.
    """
    if _GUARD is None:
        return
    origin = getattr(plugin, "__file__", None)
    if not origin or Path(origin).name != "conftest.py":
        return
    _GUARD.attribute(Path(origin))


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_make_collect_report(collector: pytest.Collector) -> Iterator[None]:
    """Bracket every collector: check before it runs, attribute what it added.

    ``tryfirst`` is load-bearing, not a tidiness flag.  The pattern this guard
    tells implementers to adopt — install and restore from a
    ``pytest_make_collect_report`` hookwrapper — puts the *leaking* conftest's
    wrapper somewhere in the same chain, and this one has to be outermost so
    that ``attribute()`` runs after every inner wrapper has had its chance to
    restore: the correct pattern then leaves an empty delta and the buggy one
    does not.  ``check()`` correspondingly has to run before any inner wrapper
    installs anything, or the guard reacts to a stub that is about to be put
    back.

    There is no re-baseline here.  ``attribute()`` ends by re-baselining, so
    an explicit ``snapshot()`` at this point only re-copied ``sys.modules`` a
    third time per node — the profile showed ``snapshot`` at 270 calls against
    ``attribute``'s 136 — and it *discarded* anything imported between the
    previous node's attribution and this one instead of attributing it.

    Every collector is bracketed, not just ``pytest.Module``.  A ``Dir`` or
    ``Package`` node is where a hook-installed stub is created, so skipping
    those left the guard blind to them.

    The check runs *before* ``collector.collect()`` because that is the moment
    a leaked stub does its damage: it is the import that fails, and the failure
    names the importing module rather than the conftest responsible.
    """
    if _GUARD is None:
        yield
        return
    path = Path(str(collector.path))
    phase = "the collection of" if path.is_dir() else "the import of"
    _GUARD.check(path, f"{phase} {_display(path, _GUARD.rootdir)}")
    try:
        yield
    finally:
        _GUARD.attribute(path)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_protocol(item: pytest.Item, nextitem: object) -> Iterator[None]:
    """Bracket each test the same way — a stub can escape after collection too.

    ``pytest_runtest_setup`` alone only ever *checked*; nothing attributed what
    a run-phase hookwrapper installed, so a stub created for the run window and
    never restored was invisible.  Outermost again, for the same reason.

    Caveat on the owner: during the run phase it is ``item.path``, the module
    the test lives in.  A stub installed lazily *while a test runs* but
    originating from a fixture defined in a conftest further up is therefore
    blamed on whichever directory happened to be executing rather than on the
    conftest that defines the fixture, and the reported directory can be
    narrower than the one the stub really belongs to.  The report still names
    a real key and a real observation point, so it stays actionable, and no
    such case has been observed — the collection phase attributes conftest
    fixtures to the conftest, which is where this shape would normally land.
    Fixing it properly means tracing a stub back to the frame that installed
    it, which costs far more than the guard is worth.
    """
    if _GUARD is None:
        yield
        return
    path = Path(str(item.path)) if item.path else None
    _GUARD.check(path, f"the test {item.nodeid}")
    try:
        yield
    finally:
        if path is not None:
            _GUARD.attribute(path)


# ---------------------------------------------------------------------------
# xdist: detection happens in the workers, reporting happens on the controller
# ---------------------------------------------------------------------------

# Records collected from workers. Empty in a serial run, where the controller
# and the detector are the same process and ``_GUARD.records()`` is used.
_WORKER_RECORDS: list[dict] = []

# ``(key, owner)`` of every record already merged.  Each worker checks the same
# stub against its own share of the nodes, so the same escape arrives from
# several of them with a different ``observed_at``; a full-dict comparison
# treats those as distinct and inflates the reported key count.  The first
# observation is the one kept, matching the serial path's ``_reported``.
_WORKER_TOKENS: set[tuple[str, str]] = set()


def _all_records() -> list[dict]:
    """Every leak this process knows about, worker-reported ones included."""
    local = _GUARD.records() if _GUARD is not None else []
    return local + _WORKER_RECORDS


def _group_records(records: list[dict]) -> dict[str, list[dict]]:
    """Records bucketed by the file that installed them, in first-seen order."""
    grouped: dict[str, list[dict]] = {}
    for record in records:
        grouped.setdefault(record["owner"], []).append(record)
    return grouped


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Ship worker findings to the controller, and fail the run in error mode.

    Under xdist every check runs in a worker, so the controller's own ``_GUARD``
    never sees a leak.  Without this hand-off both the terminal section and the
    ``error`` gate were silently dead under ``-n`` — which is the only shape CI
    uses, so the gate #13361 relies on would not have existed.
    """
    workeroutput = getattr(session.config, "workeroutput", None)
    if workeroutput is not None:
        workeroutput["sys_modules_leaks"] = _GUARD.records() if _GUARD else []
        return
    if _mode() == _MODE_ERROR and _all_records():
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node: object, error: object) -> None:
    """Merge one worker's findings into the controller's list.

    ``optionalhook`` is mandatory here: ``pytest_testnodedown`` is an xdist
    hookspec, so on any run where pytest-xdist is not installed pluggy's
    ``check_pending()`` raises ``PluginValidationError: unknown hook`` and
    takes the whole session down at collection.  Several CI jobs install bare
    pytest (see pytest.ini's note on the xdist-less jobs), so without this the
    guard would break them all.
    """
    output = getattr(node, "workeroutput", None) or {}
    for record in output.get("sys_modules_leaks", []):
        token = (record["key"], record["owner"])
        if token in _WORKER_TOKENS:
            continue  # another worker saw the same stub at a different nodeid
        _WORKER_TOKENS.add(token)
        _WORKER_RECORDS.append(record)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def pytest_terminal_summary(terminalreporter: object, exitstatus: int) -> None:
    """Print the leaks in their own section; a warnings line is too easy to miss."""
    records = _all_records()
    if not records:
        return
    grouped = _group_records(records)
    terminalreporter.section(_SECTION_TITLE, sep="=", red=True, bold=True)
    for owner, owned in grouped.items():
        _write_owner_report(terminalreporter, owner, owned)
    terminalreporter.write_line(
        f"{len(records)} leaked sys.modules key(s) from {len(grouped)} file(s). "
        f"Install and remove each stub in the same try/finally, scoped to the "
        f"nodes that need it. Set {_MODE_ENV}={_MODE_ERROR} to fail the run on "
        f"these, or {_MODE_ENV}={_MODE_OFF} to disable the guard."
    )


def _write_owner_report(terminalreporter: object, owner: str, records: list[dict]) -> None:
    """Print one offender: who, how far it reached, and which keys."""
    first = records[0]
    terminalreporter.write_line(
        f"LEAK: {owner} leaves {len(records)} sys.modules key(s) installed outside "
        f"{first['owner_dir_display']}/ — first seen at {first['observed_at']}",
        red=True,
    )
    keys = [record["key"] for record in records]
    shown = ", ".join(keys[:_KEYS_PER_OWNER])
    overflow = len(keys) - _KEYS_PER_OWNER
    if overflow > 0:
        shown = f"{shown} … (+{overflow} more)"
    terminalreporter.write_line(f"      keys: {shown}")
