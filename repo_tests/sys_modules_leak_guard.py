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

What a finding costs is decided by a checked-in baseline of the owners that
leak today (``repo_tests/sys_modules_leak_baseline.txt``), applied per *owner*
rather than per key — one conftest dragging 40 keys along is one line:

* an owner **on** the baseline is reported and does not fail the run; that is
  pre-existing debt, tracked in #13361, and failing on it would mean the gate
  could not be switched on until the last one was fixed;
* an owner **not** on the baseline **fails the run** — a new leak is a
  regression, and gating it is the whole point of the guard;
* an owner on the baseline that the session exercised and that **no longer
  leaks** also **fails the run**, asking for its line to be deleted.

The last rule is what makes the list shrink-only: it cannot rot, and every fix
lands with a one-line deletion that proves it.  It needs the session to have
actually given the owner a chance to escape — a run confined to
``autobot-backend/`` never takes that conftest's stubs anywhere they could be
seen — so :meth:`_LeakGuard._note_escape_opportunity` only counts an owner once
pytest has handled a node outside it.

A handful of owners install their stub *while their own tests run* rather than
at import, and those are marked ``run-phase`` in the baseline.  CI shards the
suite twelve ways, so eleven of those twelve sessions collect such a module,
never run a single one of its tests, and see nothing — which under the rule
above would read as "fixed, delete the line" and fail eleven shards over a leak
that is still there.  Annotated entries are therefore reported but never
checked for removal.  Nothing else changes for them: they are still on the
list, so they never fail as a regression either.

The predecessor of this was a ``report``/``error`` pair (#13370) where
``report`` never failed on anything and ``error`` failed on everything, so the
only reachable setting gated nothing at all (#13398).

Configuration:

``AUTOBOT_SYSMODULES_GUARD=off``   disable the guard entirely (local escape hatch)
``AUTOBOT_SYSMODULES_BASELINE``    read the baseline from elsewhere; the guard's
                                   own nested-session tests are the only caller
"""

from __future__ import annotations

import os
import types
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pytest

_MODE_ENV = "AUTOBOT_SYSMODULES_GUARD"
_MODE_OFF = "off"

_BASELINE_ENV = "AUTOBOT_SYSMODULES_BASELINE"
_BASELINE_NAME = "sys_modules_leak_baseline.txt"
_RUN_PHASE = "run-phase"

_SECTION_TITLE = "sys.modules leak guard"
_KEYS_PER_OWNER = 8


def _enabled() -> bool:
    """False only for ``AUTOBOT_SYSMODULES_GUARD=off``, the local escape hatch."""
    return os.environ.get(_MODE_ENV, "").strip().lower() != _MODE_OFF


def _baseline_path() -> Path:
    """Where the allowlist lives — beside this file unless the env var moves it."""
    override = os.environ.get(_BASELINE_ENV, "").strip()
    return Path(override) if override else Path(__file__).resolve().with_name(_BASELINE_NAME)


@dataclass(frozen=True)
class _Baseline:
    """The checked-in allowlist, split by what each entry may be judged on."""

    owners: frozenset[str]  # every listed owner — none of these fails as new
    removal_checked: frozenset[str]  # the subset whose silence means "fixed"


def _load_baseline(path: Path) -> _Baseline:
    """Read the allowlist: one repo-relative owner path per line.

    Blank lines and ``#`` comments are ignored.  A trailing ``run-phase``
    marks an owner that only leaks while its own tests run, which exempts it
    from the removal check (see the module docstring); it is the only
    annotation, and anything else is deliberately treated as no annotation so
    a typo shows up as a failing removal check rather than as silence.

    A missing file means an *empty* allowlist rather than a disabled gate —
    that is the right answer for the scratch repos the guard's own tests build,
    and it keeps a deleted or mistyped path loud instead of silent.
    """
    if not path.is_file():
        return _Baseline(frozenset(), frozenset())
    owners: set[str] = set()
    removal_checked: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        owner, _, annotation = entry.partition(" ")
        owners.add(owner)
        if annotation.strip() != _RUN_PHASE:
            removal_checked.add(owner)
    return _Baseline(frozenset(owners), frozenset(removal_checked))


def _outside_owner_dir(
    path: Path | None,
    path_parents: frozenset[Path],
    owner_dir: Path,
    owner_ancestors: frozenset[Path],
) -> bool:
    """The escape rule, shared by leak detection and baseline bookkeeping.

    See :meth:`_Mutation.escapes_to` for why an ancestor directory is exempt.
    """
    if path is None:
        return False
    if path == owner_dir or owner_dir in path_parents:
        return False  # inside the owner's own subtree
    return path not in owner_ancestors  # a structural ancestor Dir imports nothing


@dataclass(frozen=True)
class _Mutation:
    """A suspicious ``sys.modules`` entry and the file that installed it."""

    key: str
    kind: str  # "replaced" or "synthetic"
    owner: str  # display path of the conftest / test module
    owner_dir: Path
    owner_dir_display: str
    obj_id: int
    prev_kind: str  # what the key held before, for the leak report (#13651)
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
        made the gate unusable.  Pytest builds a ``Dir`` collector for
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
        return _outside_owner_dir(path, path_parents, self.owner_dir, self.owner_ancestors)


def _occupant(key: str, expected_obj_id: int) -> str:
    """Describe whatever currently sits at *key*, for the leak report (#13651).

    The report names the file blamed for a key and the test that witnessed it,
    but not *what object* is parked there — so a reader cannot tell an
    unremoved stub from a real module someone re-imported over the top, and
    every diagnosis of #13651 so far has been an inference about exactly that.

    Cheap and total: this runs only when a leak is already being printed.
    """
    module = sys.modules.get(key)
    if module is None:
        return "absent-at-report-time"

    same = "same-object" if id(module) == expected_obj_id else "REPLACED-since"
    kind = type(module).__name__
    origin = getattr(module, "__file__", None)
    spec = "spec" if getattr(module, "__spec__", None) is not None else "no-spec"
    where = origin if origin else "no-__file__"
    return f"{same}, {kind}, {spec}, {where}"


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
            "occupant": (
                f"{self.mutation.prev_kind} -> "
                f"{_occupant(self.mutation.key, self.mutation.obj_id)}"
            ),
        }


def _is_synthetic(module: object) -> bool:
    """True for hand-built module stubs and mocks, false for real imports."""
    return getattr(module, "__spec__", None) is None


def _previous_kind(previous: object) -> str:
    """Describe what a key held before the mutation, for the report (#13651)."""
    if previous is _MISSING:
        return "was-absent"
    if _is_synthetic(previous):
        return "was-synthetic"
    return "was-genuine"


def _has_real_file(module: object) -> bool:
    """True when *module* was loaded from a file that exists on disk (#13651).

    ``__spec__`` alone is not enough: a package may register a spec-carrying
    compatibility shim for a submodule it deleted, and those have no file. The
    exemption above must not fire for one of those.
    """
    origin = getattr(module, "__file__", None)
    if not origin:
        return False
    try:
        return Path(origin).is_file()
    except (OSError, ValueError):
        return False


def _is_self_rebind(name: str, module: object, previous: object) -> bool:
    """True when *module* is a real package re-registering itself under its own name.

    A package may legitimately replace its own ``sys.modules`` entry while it is
    importing.  ``transformers`` does exactly this: the entry the import
    machinery installs is swapped for a ``_LazyModule``, so the key changes
    object mid-import.  The guard's "replaced" rule was written for a *test*
    swapping a real module out, and cannot tell the two apart by the fact of
    replacement alone.

    What separates them is whether the replacement is itself a real module that
    still knows its own name.  A ``_LazyModule`` keeps a populated ``__spec__``
    and a ``__name__`` equal to the key.  The three historical leaks do not:
    ``autobot_shared`` and ``sqlalchemy`` were replaced by bare ``MagicMock``
    objects and ``agents`` by a ``types.ModuleType`` with no spec — none carries
    a ``__spec__``, so all three stay reported (#13599).

    The name check matters as well as the spec: aliasing one real module onto a
    different key (``sys.modules["x"] = real_yaml``) is a genuine swap, and its
    ``__name__`` would not match, so it is still caught.

    **What was there before matters just as much.** Displacing a conftest stub
    with the genuine module — which ``tests/agents/test_causal_reasoning.py`` and
    ``tests/orchestration/test_causal_error_recovery.py`` both do deliberately —
    also ends with a real, correctly-named module under the key. Judging on the
    new object alone silences those, and they are exactly the kind of run-phase
    leak the baseline tracks. A package rebinding itself is distinguished by the
    *previous* value also being a real spec-carrying module of the same name:
    the partially-initialised module the import machinery installed moments
    earlier. Replacing a stub does not satisfy that, because a stub has no spec.
    """
    if not isinstance(module, types.ModuleType):
        return False
    if getattr(module, "__spec__", None) is None:
        return False
    if getattr(module, "__name__", None) != name:
        return False
    if not isinstance(previous, types.ModuleType):
        return False
    return getattr(previous, "__spec__", None) is not None


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
    """*path* in the form the baseline file stores: repo-relative and POSIX.

    A path outside the root keeps its absolute form instead of collapsing to a
    basename.  Collapsing made every ``conftest.py`` in the tree share one
    display name, and since the baseline is keyed on that name, two different
    conftests became one entry — harmless in this repo, where nothing sits
    outside the root, but not in the scratch repos the guard's own
    nested-session tests build under ``tmp_path``.
    """
    try:
        return path.relative_to(rootdir).as_posix()
    except ValueError:
        return str(path)


class _LeakGuard:
    """Track suspicious ``sys.modules`` mutations and where they escape to."""

    def __init__(self, rootdir: Path, removal_candidates: frozenset[str] = frozenset()) -> None:
        self._rootdir = rootdir
        self._baseline: dict[str, object] = {}
        # Only the owners the shrink check may fire on are worth watching; the
        # rest are on the allowlist and nothing this session sees can move them.
        self._removal_candidates = removal_candidates
        # Their basenames, so the visit check can reject the overwhelming
        # majority of nodes — every directory and every unrelated module — on
        # one set lookup instead of building a repo-relative display path for
        # each of the thousands of collectors a session brackets.
        self._candidate_names = {Path(owner).name for owner in removal_candidates}
        self._tracked: dict[str, _Mutation] = {}
        self._reported: set[tuple[str, str]] = set()
        self._warned_owners: set[str] = set()
        # Baselined owners this session has loaded but not yet taken anywhere
        # they could escape to, mapped to their directory and its ancestors.
        self._visited: dict[str, tuple[Path, frozenset[Path]]] = {}
        # Baselined owners the session *has* taken outside their directory —
        # the only ones whose silence is evidence that they were fixed.
        self._exercised: set[str] = set()
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
        self._note_visit(owner_file)
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
                prev_kind=_previous_kind(previous),
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
        changed = [
            name for name, module in current.items() if previous_of(name, _MISSING) is not module
        ]
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
        if _is_self_rebind(name, module, previous) and self._is_third_party(module):
            return None  # a third-party package re-registering itself mid-import  # a package re-registering itself during its own import
        if previous is _MISSING and self._parent_is_genuine(name):
            return None  # a real package's own shim, not a test's leftover
        if not self._shadows_real_code(name):
            return None
        if previous is not _MISSING:
            # #13651: a *stub* giving way to the genuine module is a repair, not
            # a leak. `sys.modules.setdefault(name, MagicMock())` is a no-op when
            # the real module is already imported, so on a shard where something
            # imported it first, the knowledge suite installs no stub at all —
            # the teardown pops the real module and it is imported again. The
            # guard then saw a "replacement" whose end state is exactly what
            # Python should hold, and failed the run for it.
            #
            # Narrow on purpose: real-over-real stays reported, because repo code
            # displacing a genuine module is the case #13633 kept. Only
            # synthetic -> genuine is exempt, and only when the newcomer really
            # is genuine (a __spec__ AND a file, so a spec-less shim cannot pass).
            if _is_synthetic(previous) and not _is_synthetic(module) and _has_real_file(module):
                return None
            return "replaced"
        return "synthetic" if _is_synthetic(module) else None

    def _is_third_party(self, module: object) -> bool:
        """True when *module* is loaded from outside this repository.

        The last discriminator standing. Repo code re-importing a real module
        over another real module — which ``conftest``'s ``_real_load_and_bind``
        plus a test's stub displacement produce together — is structurally
        identical to a package rebinding itself during import: both end with a
        correctly-named, spec-carrying module replacing another. Only the file
        location tells them apart, and it is the property that actually matters:
        the guard exists to police *this repository's* stubs.
        """
        origin = getattr(module, "__file__", None)
        if not origin:
            return False
        try:
            Path(origin).resolve().relative_to(self._rootdir)
        except ValueError:
            return True
        return False

    def _parent_is_genuine(self, name: str) -> bool:
        """True when *name* is a **new** child of a real, untouched package (#13450).

        ``_is_synthetic`` asks whether a ``sys.modules`` entry lacks a
        ``__spec__``.  That correctly describes a hand-built stub — and it also
        describes something else the guard was never meant to police: a real
        distribution registering a shim for one of its own submodules.

        ``transformers==5.14.1`` does exactly that.  It *removed*
        ``tokenization_utils``, ``tokenization_utils_fast`` and
        ``image_processing_utils_fast`` and installs spec-less compatibility
        objects under the old names; the files do not exist on disk.  Measured,
        those entries are indistinguishable from ``types.ModuleType("x")`` by
        ``__spec__``, ``__file__``, ``__loader__`` and object type alike, so no
        attribute of the entry itself can separate the two cases.

        What does separate them is **ownership of the parent**.  A library's
        shim always sits under its own real, spec-carrying package.  A leaked
        stub replaces the package itself, which is why all three historical
        leaks — ``sqlalchemy``, ``autobot_shared``, ``agents`` — are unaffected:
        stubbing a package drops the parent's ``__spec__``, and this returns
        False for them and for their children.

        The parent must also not be tracked. If the session installed the parent
        as a stub, its children are that stub's business and stay reportable
        however genuine the parent looks.

        **The trade this makes, stated plainly:** a test that stubs only a
        submodule while leaving the real parent intact is no longer caught —
        ``sys.modules["json.decoder"] = MagicMock()`` with ``json`` untouched.
        Nothing in this repository does that; both stub lists in
        ``autobot-backend/conftest.py`` install the parent alongside the child.
        Accepted deliberately (#13450) to stop the guard reddening every base
        run over a library's own bookkeeping.
        """
        parent_name, _, _ = name.rpartition(".")
        if not parent_name or parent_name in self._tracked:
            return False
        parent = sys.modules.get(parent_name)
        if not isinstance(parent, types.ModuleType):
            return False
        if getattr(parent, "__spec__", None) is None:
            return False
        # The parent must be a third-party distribution, not repo code. Without
        # this the exemption also covers a conftest stubbing one submodule of a
        # real repo package — which this repository genuinely does:
        # ``tests/orchestration/test_causal_error_recovery.py`` leaves spec-less
        # ``orchestration.causal_error_analyzer`` / ``…causal_error_recovery``
        # entries under the real ``orchestration`` package, and both are on the
        # leak baseline. Those must stay reported (#13599).
        parent_file = getattr(parent, "__file__", None)
        if not parent_file:
            return False
        try:
            Path(parent_file).resolve().relative_to(self._rootdir)
        except ValueError:
            return True  # outside the repo — a third-party package's own shim
        return False

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

        This is also where a baselined owner earns the right to be called
        fixed: the same step that would have caught its stub records that the
        session gave it the chance to escape.
        """
        if not self._tracked and not self._visited:
            return
        path_parents = frozenset(path.parents) if path is not None else frozenset()
        self._note_escape_opportunity(path, path_parents)
        for mutation in list(self._tracked.values()):
            if not mutation.is_live():
                self._tracked.pop(mutation.key, None)
                continue
            if self._now_exempt(mutation.key):
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

    def _now_exempt(self, key: str) -> bool:
        """True when a tracked key has since become explicable (#13599).

        Classification happens at the snapshot that first sees a key, and that
        is sometimes *mid-import* of the package the key belongs to. A
        ``transformers.*`` compat shim is registered before the parent finishes
        binding its own ``_LazyModule``, so at classification time the parent is
        not yet a genuine spec-carrying package and the exemption in
        :meth:`_classify` cannot apply. Once tracked, a mutation was never
        revisited, so the entry stayed reportable for the rest of the session
        even though the reason for suspecting it had evaporated.

        Re-checking here costs one dict lookup per tracked key per node and is
        what makes the exemption actually reachable. It only ever *removes*
        suspicion, and only on the same two grounds :meth:`_classify` uses, so
        it cannot hide a stub that classification would have caught.
        """
        module = sys.modules.get(key)
        if module is None:
            return False
        return _is_synthetic(module) and self._parent_is_genuine(key)

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

    def _note_visit(self, owner_file: Path) -> None:
        """Remember that a baselined owner was loaded by this session.

        Recorded *before* :meth:`attribute`'s no-delta early return: an owner
        that has stopped leaking installs nothing and so produces no delta at
        all, and that is precisely the case the baseline has to notice.
        """
        if owner_file.name not in self._candidate_names:
            return
        owner = _display(owner_file, self._rootdir)
        if (
            owner not in self._removal_candidates
            or owner in self._visited
            or owner in self._exercised
        ):
            return
        owner_dir = owner_file if owner_file.is_dir() else owner_file.parent
        self._visited[owner] = (owner_dir, frozenset(owner_dir.parents))

    def _note_escape_opportunity(self, path: Path | None, path_parents: frozenset[Path]) -> None:
        """Promote every visited baselined owner that *path* lies outside of.

        "This owner did not leak" is only evidence when the session gave it the
        chance to: a run confined to ``autobot-backend/`` never takes that
        conftest's stubs anywhere they could be seen, and concluding from such
        a run that the entry is removable would fail every partial run in the
        tree.  The test is the same one leak detection uses, so an owner is
        exercised exactly when a leak would have been reported had one been
        live.
        """
        if not self._visited or path is None:
            return
        for owner, (owner_dir, ancestors) in list(self._visited.items()):
            if _outside_owner_dir(path, path_parents, owner_dir, ancestors):
                del self._visited[owner]
                self._exercised.add(owner)

    def exercised_owners(self) -> set[str]:
        """Baselined owners this session took outside their own directory."""
        return set(self._exercised)

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

# Read once, at import: the file is small, and every hook below needs it.
_BASELINE_PATH = _baseline_path()
_BASELINE = _load_baseline(_BASELINE_PATH)
_BASELINE_DISPLAY = _display(_BASELINE_PATH, _REPO_ROOT)


def _make_guard() -> _LeakGuard | None:
    """Build the guard at *import* time, before any other conftest loads.

    ``pytest_configure`` is far too late: pytest loads the conftest of every
    initial argument path during ``pytest_load_initial_conftests``, which runs
    before configure, so a guard created there would miss exactly the
    import-time conftest mutations it exists to catch.  The rootdir conftest
    pulls this module in through ``pytest_plugins``, and the rootdir conftest is
    an ancestor of every argument, so this runs first.
    """
    if not _enabled():
        return None
    guard = _LeakGuard(_REPO_ROOT, _BASELINE.removal_checked)
    guard.snapshot()
    return guard


_GUARD: _LeakGuard | None = _make_guard()


def pytest_configure(config: pytest.Config) -> None:
    """Keep the guard's warnings visible even under a strict filter set."""
    if _GUARD is None:
        return
    config.addinivalue_line(
        "filterwarnings", f"always::{__name__}.{_SysModulesLeakWarning.__name__}"
    )


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

# Baselined owners the workers took outside their own directory. Merged as a
# union: an owner only has to be exercised somewhere for its silence to count.
_WORKER_EXERCISED: set[str] = set()


def _all_records() -> list[dict]:
    """Every leak this process knows about, worker-reported ones included."""
    local = _GUARD.records() if _GUARD is not None else []
    return local + _WORKER_RECORDS


def _all_exercised_owners() -> set[str]:
    """Every baselined owner given a chance to escape, in any process."""
    local = _GUARD.exercised_owners() if _GUARD is not None else set()
    return local | _WORKER_EXERCISED


@dataclass(frozen=True)
class _Verdict:
    """What this session's findings mean once the baseline is applied."""

    new_owners: list[str]  # leaking and unlisted — a regression, fails the run
    known_owners: list[str]  # leaking and listed — known debt, reported only
    fixed_owners: list[str]  # listed, exercised, silent — delete the line

    @property
    def failed(self) -> bool:
        return bool(self.new_owners or self.fixed_owners)


def _verdict() -> _Verdict:
    """Split the session's owners into regression / known debt / removable.

    ``fixed_owners`` subtracts *every* leaking owner rather than only the ones
    this process saw: under xdist one worker can exercise an owner without
    meeting its stub while another meets it, and an entry is removable only
    when nobody saw it leak.
    """
    leaking = {record["owner"] for record in _all_records()}
    return _Verdict(
        new_owners=sorted(leaking - _BASELINE.owners),
        known_owners=sorted(leaking & _BASELINE.owners),
        fixed_owners=sorted((_all_exercised_owners() & _BASELINE.removal_checked) - leaking),
    )


def _group_records(records: list[dict]) -> dict[str, list[dict]]:
    """Records bucketed by the file that installed them, in first-seen order."""
    grouped: dict[str, list[dict]] = {}
    for record in records:
        grouped.setdefault(record["owner"], []).append(record)
    return grouped


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Ship worker findings to the controller, and fail on an unbaselined verdict.

    Under xdist every check runs in a worker, so the controller's own ``_GUARD``
    never sees a leak.  Without this hand-off both the terminal section and the
    gate were silently dead under ``-n`` — which is the only shape CI uses, so
    the gate this guard exists to be would not have existed.

    Both halves of the verdict travel: the leaks, and the baselined owners this
    process took outside their directory without meeting their stub.  The
    second is what lets the controller tell "fixed, delete the line" from
    "never exercised, say nothing".
    """
    workeroutput = getattr(session.config, "workeroutput", None)
    if workeroutput is not None:
        workeroutput["sys_modules_leaks"] = _GUARD.records() if _GUARD else []
        workeroutput["sys_modules_exercised"] = sorted(_GUARD.exercised_owners()) if _GUARD else []
        return
    if _verdict().failed:
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
    _WORKER_EXERCISED.update(output.get("sys_modules_exercised", []))


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def pytest_terminal_summary(terminalreporter: object, exitstatus: int) -> None:
    """Print the findings in their own section, split by what has to be done.

    Only a *failing* verdict paints the section red.  A full CI run is 12
    shards times 2 invocations, so a red block per shard for debt nobody is
    required to act on is 24 sections of wallpaper — which is exactly how a
    report-only guard stops being read (#13398).
    """
    verdict = _verdict()
    grouped = _group_records(_all_records())
    if not grouped and not verdict.fixed_owners:
        return
    terminalreporter.section(_SECTION_TITLE, sep="=", red=verdict.failed, bold=True)
    _write_new_owners(terminalreporter, verdict, grouped)
    _write_fixed_owners(terminalreporter, verdict)
    _write_known_owners(terminalreporter, verdict, grouped)


def _write_new_owners(
    terminalreporter: object, verdict: _Verdict, grouped: dict[str, list[dict]]
) -> None:
    """Regressions: files that leak and are not on the baseline."""
    if not verdict.new_owners:
        return
    for owner in verdict.new_owners:
        _write_owner_report(terminalreporter, owner, grouped[owner])
    terminalreporter.write_line(
        f"{len(verdict.new_owners)} file(s) above are NOT on {_BASELINE_DISPLAY}, so this run "
        f"fails. Install and remove each stub in the same try/finally, scoped to the nodes "
        f"that need it — do not add a line to the baseline, it only shrinks. "
        f"{_MODE_ENV}={_MODE_OFF} disables the guard for a local run.",
        red=True,
    )


def _write_fixed_owners(terminalreporter: object, verdict: _Verdict) -> None:
    """The shrink-only rule: a listed file that no longer leaks must be delisted."""
    for owner in verdict.fixed_owners:
        terminalreporter.write_line(
            f"FIXED: {owner} no longer leaks — remove it from {_BASELINE_DISPLAY}",
            red=True,
        )


def _write_known_owners(
    terminalreporter: object, verdict: _Verdict, grouped: dict[str, list[dict]]
) -> None:
    """Known debt (#13361): listed, still leaking, and not a failure."""
    if not verdict.known_owners:
        return
    keys = sum(len(grouped[owner]) for owner in verdict.known_owners)
    terminalreporter.write_line(
        f"{len(verdict.known_owners)} known leaking file(s), {keys} sys.modules key(s), all on "
        f"{_BASELINE_DISPLAY} — not a failure. Fixing one means deleting its line (#13361)."
    )
    for owner in verdict.known_owners:
        terminalreporter.write_line(f"      known: {owner} ({len(grouped[owner])} key(s))")


def _write_owner_report(terminalreporter: object, owner: str, records: list[dict]) -> None:
    """Print one offender: who, how far it reached, and which keys."""
    first = records[0]
    terminalreporter.write_line(
        f"LEAK: {owner} leaves {len(records)} sys.modules key(s) installed outside "
        f"{first['owner_dir_display']}/ — first seen at {first['observed_at']}",
        red=True,
    )
    for record in records[:_KEYS_PER_OWNER]:
        occupant = record.get("occupant")
        if occupant:
            terminalreporter.write_line(f"      {record['key']}: {occupant}", red=True)
    keys = [record["key"] for record in records]
    shown = ", ".join(keys[:_KEYS_PER_OWNER])
    overflow = len(keys) - _KEYS_PER_OWNER
    if overflow > 0:
        shown = f"{shown} … (+{overflow} more)"
    terminalreporter.write_line(f"      keys: {shown}")
