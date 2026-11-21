#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#17558 item 2/4 — a bound the production plane states and the CI plane cannot keep.

THE SHAPE, from #17557. `chromadb==1.5.9` is declared in the CI plane and
requires `opentelemetry-api>=1.2.0` with no upper bound. The production plane
pins `opentelemetry-api==1.44.0`. The CI plane never declares it, so pip
resolved whatever was newest, the two planes agreed by coincidence, and the
coincidence ended the morning 1.45.0 shipped -- taking `python-suite shard 1/12`
red on eight unrelated pull requests, none of which had touched a requirements
file.

WHY `check_requirements_ci_drift.py` CANNOT SEE IT. That checker compares
packages declared in BOTH planes. Here the package is declared in one and merely
*installed* in the other, so there is no pair to compare and it is silent.

WHY THIS IS A SEPARATE MODULE. The drift checker is purely static -- it reads
requirement files and nothing else. This check must know what the CI plane
actually drags in, which only the installed distributions can answer. Folding a
metadata-dependent question into a static guard would make the static one
environment-dependent, which is the conflation #17558 exists to remove. So the
environment-reading half lives here and names the environment it read.

WHAT IS AND IS NOT A FINDING. Two refinements, both load-bearing; either alone
gives a wrong answer:

* A bare ``>=`` floor in the production plane is SAFE under an unbounded CI
  resolve, because newest satisfies it. The trigger is an **upper bound the CI
  plane does not restate** -- ``==``, ``<``, ``<=`` or ``~=``. Filtering on
  ``==`` alone finds one of the three candidates in this tree.
* A requirer that bounds the package above ITSELF makes the agreement
  structural, not coincidental. `langchain` requires `langgraph<1.3.0` where
  production says `<2.0.0`: stricter, so the resolution cannot escape.
  Reporting those would be the false-positive noise that makes a check ignored.

THE CONTRAST PAIR IS FREE. Before #17502 declared the four OpenTelemetry
packages in `requirements-ci/storage.txt`, this check would have reported them.
It is silent on them now. So it reproduces #17557 when the fix is absent and
says nothing when it is present, which is what a guard's contrast pair is for.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
from dataclasses import dataclass

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from check_requirements_ci_drift import (  # noqa: E402
    _CI_REQUIREMENTS,
    _PRODUCTION_REQUIREMENTS,
    _normalize,
    ci_requirement_names,
    production_requirement_names,
)

#: Acute pairs accepted for now. **ONLY SHRINKS.** An entry leaves when the CI
#: plane declares the package or the requirer gains an upper bound; it is never
#: added to make a new one pass -- that is the decision this file keeps visible.
#: ``package -> the unbounded requirer that makes it a pair``. **ONLY SHRINKS.**
#:
#: The requirer is recorded, not just the package, so the check can tell
#: "no longer a pair" from "that requirer is not installed in this
#: interpreter". Without it a leaner environment reports a false stale entry --
#: which is how this was found: the pre-push hook runs a different interpreter
#: (#16715), `torchmetrics` was absent, and the bidirectional contract fired a
#: confident "torch is no longer an unenforced pair".
BASELINE: dict[str, str] = {
    # production `>=7.36.2,<8.0.0`; `onnxruntime` requires `protobuf>=4.25.8`,
    # unbounded, so CI takes 8.0 the day it ships. The HIGHER-RISK entry: that
    # cap is not incidental -- requirements.txt:10-14 records it as the real
    # incompatibility boundary, re-derived under #15070 after an earlier note
    # claimed the opposite. Declaring protobuf in the CI plane at the production
    # constraint is the #17502 fix applied again, but it moves what CI installs
    # and that cap deserves its own review. Filed as #17582.
    "protobuf": "onnxruntime",
}

#: Read by this checker; code-quality.yml's filter must cover each, or a PR
#: touching only one of them skips the required check (#14550/#14551/#17542).
GUARD_INPUT_PATHS = (*_PRODUCTION_REQUIREMENTS, _CI_REQUIREMENTS, "requirements-ci/*.txt")

_UPPER = re.compile(r"(==|<=|<|~=)")
_REQ_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


@dataclass(frozen=True)
class UnenforcedPair:
    """A production upper bound nothing in the CI plane keeps."""

    name: str
    production: str
    requirers: tuple[tuple[str, str], ...]

    def describe(self) -> str:
        via = "; ".join(f"{who} requires {spec}" for who, spec in self.requirers[:2])
        return f"{self.name}: production says {self.production}, CI never declares it <- {via}"


def bounds_above(specifier: str) -> bool:
    """True when *specifier* forbids arbitrarily new versions."""
    return bool(_UPPER.search(specifier))


def _parsed(requirement: str):
    """``packaging.requirements.Requirement``, or None when it will not parse."""
    from packaging.requirements import Requirement  # noqa: PLC0415

    try:
        return Requirement(requirement)
    except Exception:  # noqa: BLE001 - malformed metadata raises several types
        return None


def requirement_name(requirement: str) -> str:
    """The distribution name at the head of a requirement string."""
    parsed = _parsed(requirement)
    if parsed is not None:
        return _normalize(parsed.name)
    match = _REQ_NAME.match(requirement.strip())
    return _normalize(match.group(1)) if match else ""


def specifier_of(requirement: str) -> str:
    """Only the version specifier -- never the environment marker.

    #17610 review: `bounds_above` used to scan the whole requirement suffix, so
    `widget>=1.0; python_version < "3.10"` looked capped because of the `<` in
    its MARKER. That turns a genuinely unbounded requirer into a structurally
    bounded one and hides a real pair -- a false negative in the direction that
    matters, since this guard exists to find pairs nothing bounds.
    """
    parsed = _parsed(requirement)
    if parsed is not None:
        return str(parsed.specifier)
    # Unparseable: drop anything after the marker separator rather than scanning
    # it. Better to under-claim a bound than to invent one.
    return requirement.split(";", 1)[0]


def is_optional(requirement: str) -> bool:
    """True when *requirement* only applies under an extra.

    #17610 review: the previous test was `"extra ==" in requirement`, a substring
    check that missed `extra=="x"` and any other spacing valid metadata may use.
    Retaining an optional requirement invents a pair nothing installs. The marker
    is evaluated with an empty extra, which is what "installed without extras"
    means.
    """
    parsed = _parsed(requirement)
    if parsed is None or parsed.marker is None:
        return False
    try:
        return not parsed.marker.evaluate({"extra": ""})
    except Exception:  # noqa: BLE001 - an undefined marker variable raises
        return False


def ci_transitive_closure(ci_names: set[str], requires: dict[str, list[str]]) -> dict[str, list[tuple[str, str]]]:
    """``{package: [(requirer, its requirement string)]}`` reachable from the CI plane.

    *requires* is injected rather than read here so the rule can be tested
    without an installed environment -- the environment is the one input a test
    must not depend on.

    EVERY requirer is recorded, not the first one found. Do not "optimise" this
    into a first-match sweep: an earlier version of this measurement did exactly
    that and reported `protobuf` as structurally enforced, because the first
    requirer it happened to reach (`opentelemetry-proto`) caps it at `<8.0`. The
    fourth, `onnxruntime`, requires `protobuf>=4.25.8` with no upper bound at all,
    which is the whole finding. A sweep that stops at the first match reports a
    property of its iteration order as a property of the world.
    """
    reached: dict[str, list[tuple[str, str]]] = {}
    stack = list(ci_names)
    while stack:
        current = stack.pop()
        for requirement in requires.get(current, []):
            dependency = requirement_name(requirement)
            if not dependency:
                continue
            first_time = dependency not in reached
            reached.setdefault(dependency, []).append((current, requirement))
            if first_time:
                stack.append(dependency)
    return reached


def floating_packages(
    ci: dict[str, str],
    closure: dict[str, list[tuple[str, str]]],
) -> set[str]:
    """Closure packages whose installed version the CI plane does not hold still.

    #17558 item 2 AC2: a cap is only structural if the package STATING it is
    itself held. `opentelemetry-proto` is the worked example and the reason this
    function exists. With #17502 reverted, its only requirers are
    `opentelemetry-exporter-otlp-proto-grpc` and `-proto-common`, and both say
    `opentelemetry-proto==1.44.0` -- which reads as a cap, so a per-requirement
    test calls it structurally bounded and reports nothing.

    It is not bounded. `==1.44.0` is what grpc 1.44.0's metadata says; grpc itself
    is unpinned in the reverted CI plane, so pip takes grpc 1.45.0, whose metadata
    says `opentelemetry-proto==1.45.0`, and proto moves with it. The cap is real
    and it travels. Reading a requirement string without asking which release of
    the requirer produced it is `MEASUREMENT_DISCIPLINE.md` family F: a correct
    answer to "does this requirement have an upper bound" read as an answer to
    "can this package's version climb".

    A package is HELD when the CI plane declares it with an upper bound; otherwise
    it floats as soon as any requirer either leaves it unbounded or floats itself.
    Computed to a fixed point because the property is transitive -- `floating`
    only ever grows, so the loop terminates in at most one pass per package.

    Measured blast radius when this replaced the per-requirement test: the tree's
    reported set was `['protobuf']` before and after, and the #17502 revert fixture
    went from three of #17557's four packages to all four.
    """
    floating: set[str] = set()

    def held(name: str) -> bool:
        declared = ci.get(name)
        if declared is not None and bounds_above(declared):
            return True
        return name in closure and name not in floating

    changed = True
    while changed:
        changed = False
        for name, requirers in closure.items():
            if name in floating:
                continue
            declared = ci.get(name)
            if declared is not None and bounds_above(declared):
                continue
            if any(not bounds_above(specifier_of(spec)) or not held(who) for who, spec in requirers):
                floating.add(name)
                changed = True
    return floating


def unenforced_pairs(
    production: dict[str, str],
    ci: dict[str, str],
    closure: dict[str, list[tuple[str, str]]],
) -> list[UnenforcedPair]:
    """Production upper bounds the CI plane neither declares nor structurally keeps."""
    floating = floating_packages(ci, closure)
    found: list[UnenforcedPair] = []
    for name, specifier in sorted(production.items()):
        if name in ci or name not in closure or not bounds_above(specifier):
            continue
        # Structural agreement: if every requirer caps it AND every requirer is
        # itself held at a version, the resolution cannot climb past the cap and
        # the planes cannot diverge. A cap stated by a floating requirer floats
        # with it -- see `floating_packages`.
        if name not in floating:
            continue
        found.append(UnenforcedPair(name=name, production=specifier, requirers=tuple(closure[name])))
    return found


def installed_requires() -> dict[str, list[str]]:
    """``{distribution: its requirement strings}`` from THIS interpreter.

    Extras are dropped: an optional dependency is not dragged in by declaring
    the package, so counting it would invent pairs nothing installs.
    """
    from importlib.metadata import distributions  # noqa: PLC0415

    out: dict[str, list[str]] = {}
    for dist in distributions():
        name = dist.metadata["Name"] if dist.metadata else None
        if not name:
            continue
        keep = [requirement for requirement in (dist.requires or []) if not is_optional(requirement)]
        out[_normalize(name)] = keep
    return out


def audit(root: pathlib.Path | None = None) -> tuple[list[str], list[str], list[UnenforcedPair]]:
    """``(problems, notes, pairs)``: what FAILS, what could not be judged, what is known.

    `problems` gate; `notes` do not. A pair this interpreter cannot evaluate is
    neither -- printing it as a problem would block every push from a leaner
    environment, and dropping it would be the silence this guard exists to
    prevent. Same gate-versus-report split as the floor reporter in this branch.

    THIS CHECK IS ENVIRONMENT-DEPENDENT AND SAYS SO. The closure comes from
    installed distributions, so an interpreter lacking a requirer cannot see the
    pair that requirer creates. Calling a baseline entry stale there would be
    this guard committing the defect it exists to catch: *did not look* rendered
    as *nothing found*.

    Caught the hard way. The pre-push hook runs a leaner interpreter than the one
    this was written against (#16715); `torchmetrics` was absent, and the
    bidirectional contract fired a confident "torch is no longer an unenforced
    pair". The contract was right about its data; the data was the problem. A
    plane-coverage threshold was the first fix attempted and is the wrong
    instrument -- that interpreter held most of the plane and still lacked the
    one requirer that mattered. Evaluability is per ENTRY, not per plane.
    """
    production = production_requirement_names(root)
    ci = ci_requirement_names(root)
    requires = installed_requires()
    closure = ci_transitive_closure(set(ci), requires)
    pairs = unenforced_pairs(production, ci, closure)
    names = {pair.name for pair in pairs}

    problems = [f"{pair.describe()} (#17557's shape; not in BASELINE)" for pair in pairs if pair.name not in BASELINE]
    notes: list[str] = []
    for entry, requirer in sorted(BASELINE.items()):
        if entry in names:
            continue
        if requirer not in requires:
            # Stated, never silent: an unevaluated entry is a gap in the run, not
            # a clean result, and the reader is told which entry and why.
            notes.append(
                f"NOT EVALUATED: {entry} is baselined because {requirer} requires it unbounded, and "
                f"{requirer} is not installed in this interpreter -- so whether the pair still "
                "exists cannot be judged here. Not a pass and not a failure; run it where the CI "
                "plane is installed."
            )
            continue
        problems.append(
            f"{entry}: in BASELINE but no longer an unenforced pair -- delete the entry. "
            "A stranded baseline entry exempts nothing while looking authoritative."
        )
    return problems, notes, pairs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--audit", action="store_true", help="report and exit non-zero on a new pair")
    args = parser.parse_args(argv)
    problems, notes, pairs = audit()
    for note in notes:
        print(f"  {note}")  # noqa: print
    if problems:
        print("CI-plane pins nothing enforces (#17558):")  # noqa: print
        for problem in problems:
            print(f"  {problem}")  # noqa: print
        return 1 if args.audit else 0
    print(  # noqa: print
        f"CI-plane unenforced-pin audit clean [gate]: {len(pairs)} known pair(s), "
        f"{len(notes)} not evaluated here, "
        f"closure taken from the interpreter running this check (python {sys.version.split()[0]})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
