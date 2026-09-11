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

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


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


#: Every declaration made by an imported guard module. Populated by ``declare``
#: at import time so the meta-test can enumerate without importing by path.
REGISTRY: dict[str, "Reach"] = {}

#: Memoised discoveries, keyed on (declaration name, resolved root). Frozen
#: dataclasses cannot cache on the instance, and the same walk was otherwise
#: paid once per caller per session.
_MEASURED: dict[tuple[str, str], Sequence[object]] = {}


@dataclass(frozen=True)
class Reach:
    """What one guard examines, and the least it may find and still be believed.

    ``floor`` is bound to what the sweep **discovered**, never to what it
    reported. A floor on findings says "the tree is clean" twice and checks
    neither; that is the failure this exists to separate from an honest pass.
    """

    name: str
    discover: Callable[[Path], Sequence[object]]
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

    def examined(self, root: Path) -> Sequence[object]:
        """Discover under *root*, or fail loudly having found implausibly little.

        This bounds the sweep's **input**. It is not sufficient on its own: a
        guard that lists 1,000 candidates and then silently skips 997 of them
        clears this and still speaks for a tree it never read. Pair it with
        :meth:`completed`.
        """
        found = self.population(root)
        self._require(len(found), "reached", self.what)
        return found

    def population(self, root: Path) -> Sequence[object]:
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
        count = len(self.population(root))
        slack = count - self.floor
        if slack < 0:
            raise ReachFloorError(
                f"[{self.name}] floor {self.floor} exceeds the live population of "
                f"{count} {self.what}. The guard cannot pass; lower the floor to "
                f"{count} only if the population genuinely shrank."
            )
        allowance = self.skips + self.growth
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
                f"If neither is short, the floor is stale: ratchet it toward {count}."
            )

    def headroom(self, root: Path) -> int:
        """Files this population may still gain before the floor goes red.

        Reported because the failure this prevents is silent until it is not:
        `hooks-path-override` sat 14 files from red, and nothing said so until
        someone measured. A guard is allowed to be close to its allowance; it is
        not allowed for that to be invisible.
        """
        return (self.skips + self.growth) - (len(self.population(root)) - self.floor)

    def completed(self, processed: Sequence[object] | int) -> None:
        """Apply the same floor to what the guard actually **finished**.

        Candidates are not coverage (#15826 review). Both guards converted in
        this slice skip items on failure — an unreadable file, a source that
        will not parse — after the input floor has already cleared, so without
        this the floor measured how much work was *available* rather than how
        much was done. A skip is not a clean file.
        """
        count = processed if isinstance(processed, int) else len(processed)
        self._require(count, "completed", self.what)

    def _require(self, count: int, verb: str, what: str) -> None:
        if count < self.floor:
            raise ReachFloorError(
                f"[{self.name}] {verb} {count} {what}; floor is {self.floor}. "
                f"Fix the sweep, not the tree — a clean result below this floor asserts nothing."
            )


def declare(
    name: str,
    *,
    discover: Callable[[Path], Sequence[object]],
    floor: int,
    what: str,
    growth: int = 0,
    skips: int = 0,
) -> Reach:
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
    reach = Reach(name=name, discover=discover, floor=floor, what=what, growth=growth, skips=skips)
    REGISTRY[name] = reach
    return reach
