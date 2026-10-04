# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A guard declares what it examined, so the claim can be checked (#15826).

A tree-scanning guard that finds no violations is only good news if it looked.
A glob that stops matching, a root that moves, a filter inverted, a shallow
checkout — each turns the guard into a function that returns "clean" without
reading anything, and the clean line is byte-identical to the honest one.

WHY THIS IS NOT `enforce_reach`
-------------------------------
``tools/lint/_scan_helpers.enforce_reach`` is the same idea for a *hook*: it
takes ``full_repo`` and returns an exit code. A pytest guard cannot use it
naturally, and the census that motivated this issue counted its callers — which
measured which dialect a file was written in, not whether the property held.
Guards in ``repo_tests/`` already express it as ``assert len(found) >= _MIN_X``;
what they cannot do is prove that assertion *fires*, because nothing drives
their discovery against an empty tree.

WHAT THIS ADDS
--------------
Declaring reach as data rather than as an assertion inside one test makes it
enumerable, so ``reach_declarations_test.py`` can take every declaration in the
suite, run its discovery against an empty directory, and **require the
failure**. That is the mutation half — applied once, mechanically, instead of
one hand-written mutation per guard that nobody maintains.

A floor without a test proving it fires is decoration; this is the machinery
that makes the proof automatic rather than a promise.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Generic, Sequence, TypeVar

#: What one ``discover`` returns. ``Reach`` is generic over it so a caller's own element type
#: survives into ``examined()`` instead of being flattened to ``object`` (#16987). Every guard
#: doing ``root / rel`` on an ``examined()`` result was correct at runtime and unverifiable
#: statically; ``repo_tests/`` is outside CI's mypy scope, so nothing reported it.
T = TypeVar("T")


class ReachDiscoveryError(AssertionError):
    """`discover` raised instead of returning — the sweep is broken, not the tree.

    Kept distinct from :class:`ReachFloorError` because they call for opposite
    responses. A floor error says the tree shrank or the sweep narrowed; a
    discovery error says the enumeration could not run at all. Collapsing them
    into one type is how "the guard is broken" gets read as "the tree is small".
    """


class ReachFloorError(AssertionError):
    """Raised only by :meth:`Reach._require` — the floor rejecting a sweep.

    A distinct type because ``AssertionError`` alone cannot carry the claim.
    ``examined()`` calls ``discover(root)`` before the floor runs, and the
    guards this module exists to migrate "already express it as
    ``assert len(found) >= _MIN_X``" — so a discovery callback wrapping an
    existing assert-based guard raises ``AssertionError`` too. A meta-test
    catching the bare type cannot tell *the floor rejected an empty sweep* from
    *the discovery blew up before the floor ran*, which is the same conflation
    the earlier fixes each closed one instance of.

    Subclassing ``AssertionError`` keeps every existing guard's behaviour and
    pytest's assertion reporting unchanged; only the meta-test narrows.
    """


class ReachScopeError(AssertionError):
    """The declared scope and the sweep disagree (#17844).

    Separate from :class:`ReachFloorError` because the floor and the scope are different claims
    about the same call. A floor says *how much* the sweep found; ``roots=`` says *where it was
    entitled to look*. A guard can be floored correctly over the wrong population, and that
    state raises neither of the other two errors -- it is the third of the three coverage
    states in #17844's table, and the only one nothing used to catch.
    """


#: Every declaration made by an imported guard module. Populated by ``declare``
#: at import time so the meta-test can enumerate without importing by path.
REGISTRY: dict[str, "Reach[Any]"] = {}

#: Memoised discoveries, keyed on (declaration name, resolved root). Frozen
#: dataclasses cannot cache on the instance, and the same walk was otherwise
#: paid once per caller per session.
_MEASURED: dict[tuple[str, str], Sequence[Any]] = {}


#: How much of ``growth`` must remain unspent for a floor to be accepted (#17356). A tenth:
#: large enough that a floor pinned at the very bottom is refused on the spot, small enough that
#: a deliberate mid-window pin is not re-litigated by the next merge.
_WINDOW_MARGIN = 0.10


def floor_div_fraction(total: int, fraction: float) -> int:
    """``total * fraction``, rounded DOWN.

    Down, so a declared fraction is a floor the sweep may sit exactly on rather than one it has
    to exceed. ``1.0`` therefore means "every file in the reference", which is what
    ``conflict-marker-scanned-files`` asserts, and rounding up would make that unsatisfiable.
    """
    return math.floor(total * fraction)


#: Reference enumerations, keyed on the resolved root. Same reason as ``_MEASURED``: every
#: relative declaration measures the same denominator, and #17810 found the suite paying one
#: ``git ls-files`` per declaration for an answer that cannot differ within a session.
_REFERENCE: dict[str, int] = {}


def tracked_file_count(root: Path) -> int:
    """Total tracked files -- the scale-free denominator for a relative floor (#17142).

    Deliberately NOT derived from any guard's own ``discover``. If the sweep breaks, every
    number computed from it breaks together, so a reach check comparing two of its outputs
    compares a number to itself. The first design for #17142 did exactly that -- ``examined()``
    against ``population()``, which are the same call -- and would have passed unconditionally.
    The reference has to come from outside the sweep, and ``git ls-files`` is the one
    enumeration no guard owns.
    """
    from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths  # noqa: PLC0415

    key = str(root.resolve())
    if key in _REFERENCE:
        return _REFERENCE[key]
    try:
        total = len(tracked_paths(root))
    except EmptyEnumeration:
        total = 0
    _REFERENCE[key] = total
    return total


@dataclass(frozen=True)
class Reach(Generic[T]):
    """What one guard examines, and the least it may find and still be believed.

    ``floor`` is bound to what the sweep **discovered**, never to what it
    reported. A floor on findings says "the tree is clean" twice and checks
    neither; that is the failure this exists to separate from an honest pass.
    """

    name: str
    discover: Callable[[Path], Sequence[T]]
    floor: int
    what: str
    #: How far the live population may sit **above** ``floor`` before
    #: ``reach_declarations_test`` demands the floor be ratcheted up (#15928).
    #:
    #: Zero — equality — is right whenever ordinary work does not move the
    #: number: a fixed set of workflows, of provider baselines, of scrub sites.
    #: A population that grows with almost every commit (tracked files, dict
    #: literals) cannot be equality-pinned without failing unrelated PRs, and
    #: states a band instead.
    #:
    #: The question that decides it is **"does normal work move this number?"**
    #: -- not "how much slack feels safe". Slack chosen by feel is what this
    #: field exists to stop: the two guards that adopted this module first
    #: declared floors of 500 and 1000 against a live population of 5,599.
    growth: int = 0
    #: Discovered items this guard is expected to be unable to **complete** --
    #: unreadable, unparseable, skipped for cause (#15928). Declared separately
    #: from ``growth`` because one floor serves two populations: ``examined()``
    #: bounds what ``discover`` returned, ``completed()`` bounds what the guard
    #: finished, and the floor has to clear the lower one while the meta-test
    #: measures the higher.
    #:
    #: Folding this into ``growth`` is what broke the first version of this
    #: change. ``audio-extension-allowlist`` discovers 5,601 files and completes
    #: 5,337, so a single band of 500 spent 264 of itself on the skip gap before
    #: buying one file of growth headroom -- and the tree consumed the remainder
    #: within the hour. **A number that silently spends most of itself on a
    #: different quantity cannot be chosen well**, which is the argument for two
    #: names rather than a bigger one.
    skips: int = 0
    #: RELATIVE mode (#17142). When set, this declaration's reach is checked as a FRACTION of
    #: an external reference measured in the same run, and ``floor``/``growth`` are not used.
    #:
    #: The absolute form could not be kept current: the floor is a constant, the tree grows,
    #: and the gap between them is consumed on a schedule. ``hooks-path-override`` was re-pinned
    #: SEVENTEEN times and `conflict-marker-scanned-files` reached one file of headroom on the
    #: same afternoon -- two guards, the same mechanism, neither number ever wrong when written.
    #:
    #: A fraction does not get consumed, because tree growth moves numerator and denominator
    #: together. It also changes what the check is ABOUT: the absolute floor fires on a fact
    #: about the tree (it grew past a constant), where this fires on a fact about the SWEEP (it
    #: covers a smaller share of the tree than it should). Only the second is what a reach floor
    #: is for, so this is strictly more sensitive than the floor it replaces, not less.
    #:
    #: Declared per guard rather than shared, because expected coverage is a property of the
    #: guard: ``conflict-marker-scanned-files`` scans every tracked file and states ``1.0``,
    #: while ``hooks-path-override`` covers 0.6488 of them and states ``0.45``. Two guards an
    #: order of magnitude apart in slack is the argument for per-declaration values.
    #:
    #: Residual limitation, stated rather than discovered later: a large body of files this
    #: guard does not count -- several thousand docs, say -- grows the denominator alone and
    #: lowers the fraction with no sweep breakage. At 0.45 against a live 0.6488 the tracked
    #: total would have to grow about 44% faster than the counted set before it fired.
    min_fraction: float | None = None
    #: The denominator for ``min_fraction``. Defaults to :func:`tracked_file_count`. Overridable
    #: so a guard whose population is not a subset of tracked files can name its own reference.
    reference: Callable[[Path], int] | None = None
    #: The population's SCOPE, as data rather than as prose inside ``what`` (#17844).
    #:
    #: ``floor`` is a number the framework verifies; ``what`` was free text nobody verified, and
    #: the two sit in the same call. Seven guards claimed some form of *"production python
    #: files"* over floors spanning 2555..3247 -- a 692-file spread explained entirely by
    #: differing scan roots, and invisible because only two of them said so.
    #:
    #: Each entry is a repository-relative path PREFIX. When set, ``declare`` renders it into
    #: ``what`` so the string cannot disagree with the data, and :meth:`verify_scope` holds the
    #: sweep to it in both directions.
    roots: tuple[str, ...] | None = None

    def examined(self, root: Path) -> Sequence[T]:
        """Discover under *root*, or fail loudly having found implausibly little.

        This bounds the sweep's **input**. It is not sufficient on its own: a
        guard that lists 1,000 candidates and then silently skips 997 of them
        clears this and still speaks for a tree it never read. Pair it with
        :meth:`completed`.
        """
        found = self.population(root)
        if self.min_fraction is None:
            self._require(len(found), "reached", self.what)
        else:
            self._require_fraction(len(found), root, "reached")
        return found

    def population(self, root: Path) -> Sequence[T]:
        """What ``discover`` returns for *root*, measured once per root.

        Each discovery shells out to ``git ls-files`` and some open files on top
        of it, so the same walk was being paid three times a session -- twice by
        the meta-test and once by the guard itself. Memoised on a module-level
        map because :class:`Reach` is frozen and cannot hold a cache.

        Keyed on the RESOLVED root, so a guard asked about a scratch directory
        and about the repository does not get one answer for both -- which is
        exactly what the empty-tree mutation test relies on.

        A raising ``discover`` is translated to :class:`ReachDiscoveryError`
        naming the cause (#16154), here rather than in each caller -- both
        :meth:`examined` and :meth:`verify_floor` route through this method, so
        the translation is paid once instead of duplicated at every call site.
        """
        key = (self.name, str(root.resolve()))
        if key in _MEASURED:
            return _MEASURED[key]
        try:
            found = self.discover(root)
        except ReachFloorError:
            raise
        except Exception as exc:  # noqa: BLE001 - re-raised with the cause named
            raise ReachDiscoveryError(
                f"[{self.name}] discover() raised {type(exc).__name__} instead of returning a "
                f"result: {exc}\n"
                "On an EMPTY tree `discover` must return an empty sequence, not raise. "
                "`reach_declarations_test` hands every declaration an empty repository on "
                "purpose and needs an empty RESULT to compare against the live one — an "
                "exception ends that test early and proves nothing.\n"
                "See repo_tests/excluded_tree_size_debt_test.py:76-92 for the handling this "
                "expects: catch `EmptyEnumeration`, return [], and let the floor below raise "
                "`ReachFloorError`. That does not weaken the refusal, it relocates it to the "
                "typed one this mechanism is built around."
            ) from exc
        _MEASURED[key] = found
        return found

    def verify_floor(self, root: Path) -> None:
        """Refuse a floor that sits too far below its own population (#15928).

        This lives on the primitive rather than in the meta-test that used to
        hold it, so the rule belongs to ``declare()`` rather than to whoever
        remembers to enumerate declarations. It still runs on demand rather than
        at declaration time, and that is deliberate: ``declare()`` executes at
        IMPORT, where a raise takes the whole module down before any test can
        report it, and where the root is not yet known. ``_paths.py`` records the
        same ruling for the same reason.

        Raises :class:`ReachFloorError` rather than asserting, so a caller can
        tell a floor violation from an unrelated failure.
        """
        if self.min_fraction is not None:
            # Nothing to go stale: there is no recorded constant. What this still has to
            # discharge is that the fraction HOLDS now -- the meta-test runs this for every
            # declaration, and a declaration whose fraction was already breached would
            # otherwise only surface when some unrelated PR ran the guard itself.
            self._require_fraction(len(self.population(root)), root, "reached")
            return
        count = len(self.population(root))
        slack = count - self.floor
        if slack < 0:
            raise ReachFloorError(
                f"[{self.name}] floor {self.floor} exceeds the live population of "
                f"{count} {self.what}. The guard cannot pass; lower the floor to "
                f"{count} only if the population genuinely shrank."
            )
        allowance = self.skips + self.growth
        if allowance and slack <= allowance:
            self._require_mid_window(count, slack)
        if slack > allowance:
            raise ReachFloorError(
                f"[{self.name}] floor {self.floor} sits {slack} below its live "
                f"population of {count} {self.what}, which exceeds the declared "
                f"allowance of {allowance} (skips={self.skips} + growth={self.growth}).\n"
                f"A floor this far below what the sweep finds passes while most of the "
                f"tree stops being reached.\n"
                f"Raise the one that is actually short:\n"
                f"  skips=  items this guard cannot COMPLETE (unreadable, unparseable). "
                f"Measure it from a `completed` failure; do not estimate it.\n"
                f"  growth= ordinary growth tolerated before a deliberate ratchet.\n"
                f"If neither is short, the floor is stale: {self._window_sentence(count)}"
            )

    def window(self, root: Path) -> tuple[int, int, int]:
        """``(lowest legal floor, highest legal floor, the value to pin)`` -- #17356.

        BOTH bounds, because a floor has two and every re-pin comment in
        ``hooks_path_override_15961_test.py`` quotes only the first -- which is why there are
        seventeen of them. The lower bound is the gap bound :meth:`verify_floor` enforces; the
        upper is the most :meth:`completed` can clear, since a guard that skips ``skips`` items
        finishes ``population - skips`` of them and a floor above that fails the stronger of the
        two checks while satisfying the weaker.

        The third value is the one to write down. ``population - (skips + growth)`` -- the
        arithmetic every re-pin reached for -- is the BOTTOM of the window and has zero
        tolerance by construction: correct at the instant of measurement, red for every tree
        with one more file.
        """
        return self._bounds(len(self.population(root)))

    def _bounds(self, count: int) -> tuple[int, int, int]:
        """The arithmetic, in ONE place. :meth:`window` and the failure messages had a copy
        each, and two copies of a formula are two chances for a message to recommend a value
        the check would then refuse."""
        highest = count - self.skips
        return highest - self.growth, highest, highest - self.growth // 2

    def _window_sentence(self, count: int) -> str:
        lowest, highest, mid = self._bounds(count)
        return (
            f"the window against a population of {count} is "
            f"[{lowest}, {highest}] -- its bottom is the gap bound "
            f"(skips={self.skips} + growth={self.growth}) and its top is the most completed() "
            f"can clear (population - skips). Pin MID-window, at {mid}."
        )

    def _require_mid_window(self, count: int, slack: int) -> None:
        """Refuse a floor pinned at the bottom of its own window (#17356).

        A convention was not enough, and that is measured rather than argued: the author who
        wrote up *"`population - growth` has zero tolerance"* pinned two new declarations at
        exactly that value within the hour, and both went red on the next rebase. Seven reds,
        five declarations, one night. A rule its own author violates belongs in the tool.

        The margin is a tenth of ``growth`` -- the band the caller declared as ordinary
        movement, not a number chosen here. ``growth=0`` is exempt: an equality pin is the
        deliberate choice ``growth``'s own docstring asks for when normal work does not move the
        number, and it has no window to sit in the bottom of.
        """
        if not self.growth:
            return
        margin = max(1, math.ceil(self.growth * _WINDOW_MARGIN))
        if slack <= self.skips + self.growth - margin:
            return
        raise ReachFloorError(
            f"[{self.name}] floor {self.floor} sits in the bottom {margin} of its window, which "
            f"is zero tolerance dressed as an allowance: the next "
            f"{self.skips + self.growth - slack} file(s) of ordinary growth turn it red on a PR "
            f"that did not touch this guard.\n"
            f"{self._window_sentence(count)}\n"
            f"Re-measure rather than carrying a number across (#15928): the value above is this "
            f"run's measurement, not a figure from a comment."
        )

    def verify_scope(self, root: Path) -> None:
        """Refuse a declared scope the sweep does not match, in either direction (#17844).

        Separate from :meth:`verify_floor` and raising its own type, because the two answer
        different questions about the same call: the floor asks *how much* was found, this asks
        *where*. Collapsing them is how "the guard is floored" came to be read as "the guard is
        floored over the population it names".

        A declaration with no ``roots`` is not checked -- ``_reach_scope``'s docstring states
        that boundary and ``reach_declarations_test`` records the un-scoped set so it shrinks.
        """
        if self.roots is None:
            return
        from repo_tests._reach_scope import relative_paths, scope_complaint  # noqa: PLC0415

        rels = relative_paths(self.population(root), root)
        complaint = scope_complaint(self.name, self.what, self.roots, rels)
        if complaint:
            raise ReachScopeError(complaint)

    def headroom(self, root: Path) -> int:
        """Files this population may still gain before the floor goes red.

        Reported because the failure this prevents is silent until it is not:
        `hooks-path-override` sat 14 files from red, and nothing said so until
        someone measured. A guard is allowed to be close to its allowance; it is
        not allowed for that to be invisible.
        """
        return (self.skips + self.growth) - (len(self.population(root)) - self.floor)

    def completed(self, processed: Sequence[object] | int, root: Path | None = None) -> None:
        """Apply the same bound to what the guard actually **finished**.

        Candidates are not coverage (#15826 review). Both guards converted in
        this slice skip items on failure — an unreadable file, a source that
        will not parse — after the input floor has already cleared, so without
        this the floor measured how much work was *available* rather than how
        much was done. A skip is not a clean file.

        ``root`` is REQUIRED for a relative declaration and refused loudly when absent (#17142).
        The first version of the relative mode left this method on ``_require``, which compares
        against ``floor`` — and a relative declaration carries ``floor=0``, so a guard that listed
        7137 files and opened NONE passed. The mode fixed the input bound and silently removed the
        completion bound, which is the stronger of the two and the one #15826 is about. Raising on
        a missing root rather than defaulting to the absolute path is deliberate: a default would
        reintroduce the same silence for the next declaration that adopts a fraction.
        """
        count = processed if isinstance(processed, int) else len(processed)
        if self.min_fraction is None:
            self._require(count, "completed", self.what)
            return
        if root is None:
            raise ReachFloorError(
                f"[{self.name}] completed() needs the root for a relative declaration: the bound "
                f"is a fraction of a reference that has to be measured. Without it this call "
                f"would assert nothing, because a relative declaration carries floor=0."
            )
        self._require_fraction(count, root, "completed")

    def _require_fraction(self, count: int, root: Path, verb: str) -> None:
        """Refuse a sweep covering less than ``min_fraction`` of the external reference.

        A reference of zero RAISES rather than passing. ``reach_declarations_test`` hands every
        declaration an empty repository to prove its floor can fire, and ``count >= 0 * fraction``
        is true of every sweep including a broken one -- so a fraction check that treated an empty
        reference as satisfied would be the one declaration in the registry whose floor cannot
        fire. It is also the right behaviour on its own terms: a reference that found nothing is a
        failed measurement, not a clean result.
        """
        fraction = self.min_fraction
        assert fraction is not None, "_require_fraction is only reachable on a relative declaration"
        total = (self.reference or tracked_file_count)(root)
        if total <= 0:
            raise ReachFloorError(
                f"[{self.name}] the reference enumeration found {total} files, so a fraction of it "
                f"asserts nothing about the {count} {self.what} this sweep {verb}. "
                f"Fix the reference, not the fraction."
            )
        required = floor_div_fraction(total, fraction)
        if count < required:
            raise ReachFloorError(
                f"[{self.name}] {verb} {count} {self.what}, which is "
                f"{count / total:.4f} of the {total}-file reference -- below the declared "
                f"min_fraction of {self.min_fraction} ({required} files).\n"
                f"Fix the sweep, not the fraction: this fires when the sweep covers a smaller "
                f"share of the tree than it should, which tree growth cannot cause."
            )

    def _require(self, count: int, verb: str, what: str) -> None:
        if count < self.floor:
            raise ReachFloorError(
                f"[{self.name}] {verb} {count} {what}; floor is {self.floor}. "
                f"Fix the sweep, not the tree — a clean result below this floor asserts nothing."
            )


def declare(
    name: str,
    *,
    discover: Callable[[Path], Sequence[T]],
    what: str,
    floor: int = 0,
    growth: int = 0,
    skips: int = 0,
    min_fraction: float | None = None,
    reference: Callable[[Path], int] | None = None,
    roots: tuple[str, ...] | None = None,
) -> Reach[T]:
    """Register a reach declaration and return it.

    Registration is the point: an undeclared guard is invisible to the meta-test
    and its floor is unproven, so adoption is measurable rather than assumed.

    ``floor`` is refused by :meth:`Reach.verify_floor`, which the meta-test
    discharges for every declaration (#15928). It is NOT checked here, and that
    is a ruling rather than an omission: ``declare()`` runs at IMPORT, where the
    root is not yet known and where a raise takes the whole module down before
    any test can report it — losing every parametrised case for that guard,
    which is the precise failure the meta-test exists to catch.

    The rule belongs to the primitive; the timing belongs to the caller.

    **``discover`` must return an empty sequence on an empty tree, never raise**
    (#16154). ``reach_declarations_test`` hands every declaration an empty
    repository to prove the floor can actually fire, and needs an empty *result*
    to compare against the live one — an exception ends that test early and
    proves nothing. `tracked_paths` raises `EmptyEnumeration` for good reasons of
    its own, so a guard using it must catch that and return ``[]``; the floor
    below then raises `ReachFloorError`, which is the typed refusal this
    mechanism is built around. See ``excluded_tree_size_debt_test:76-92``, which
    does this correctly and explains why relocating the refusal does not weaken
    it.

    Adoption alone does not make a floor tight. Both guards that adopted this
    module first passed a number chosen by feel, an order of magnitude below
    what their own ``discover`` returns, and every floor examined in review
    during #15896, #15901 and #15913 was set the same way. The mechanism was
    never the missing part; the number was.
    """
    # The two modes are mutually exclusive, and refusing the mix is the point: a declaration
    # carrying both would be read as whichever one the reader happened to look at, and the
    # absolute fields are exactly what #17142 is removing from the guards that adopt a fraction.
    if min_fraction is None:
        if floor <= 0:
            raise ValueError(
                f"[{name}] declare() needs either a positive floor or a min_fraction; "
                f"got floor={floor} and no min_fraction. A floor of zero asserts nothing."
            )
    else:
        if not 0 < min_fraction <= 1:
            raise ValueError(f"[{name}] min_fraction must be in (0, 1]; got {min_fraction}.")
        if floor or growth:
            raise ValueError(
                f"[{name}] min_fraction replaces floor/growth; got floor={floor}, growth={growth}. "
                f"Drop them rather than keeping a constant the relative mode does not read."
            )
    if roots is not None:
        if not roots or any(not prefix or not isinstance(prefix, str) for prefix in roots):
            raise ValueError(f"[{name}] roots= must be a non-empty tuple of path prefixes; got {roots!r}.")
        if " under " in what:
            raise ValueError(
                f"[{name}] what={what!r} already spells a scope out longhand while roots= carries "
                f"it as data. Pass the bare population noun; the scope is rendered from roots, so "
                f"the string cannot drift from the tuple the check reads."
            )
        what = f"{what} under {', '.join(roots)}"
    reach = Reach(
        name=name,
        discover=discover,
        floor=floor,
        what=what,
        growth=growth,
        skips=skips,
        min_fraction=min_fraction,
        reference=reference,
        roots=roots,
    )
    REGISTRY[name] = reach
    return reach
