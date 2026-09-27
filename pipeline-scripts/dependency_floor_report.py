# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""How a dependency-floor result is reported (#17558).

Separated from the checker because reporting is where this went wrong, not
measurement. Three readers in one day each misread a floor block: twice as a
build failure it was not, once as a clean environment it was not. Every one of
those readings was of correct data whose ROLE and SCOPE were unstated.

Also a size split: ``check_dependency_floors.py`` reached the 600-line ceiling,
and the ceiling is never raised. The seam is real rather than convenient --
nothing here measures anything, and nothing here imports the checker, so the
dependency runs one way and the banner can load the checker by file location
without a sibling import having to resolve.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from check_dependency_floors import Shortfall

#: The checker's sentinel for "declared, nothing installed". Written as a
#: literal rather than imported: this module must not import the checker (see
#: the module docstring), so the one duplicated constant is deliberate and the
#: test below pins it against the checker's own value.
ABSENT = "(absent)"

#: The checker's sentinel for "installed, version unreadable". Same duplication
#: rationale as ABSENT above.
UNREADABLE = "(version unreadable)"

#: Per-package detail lines before the report truncates and says it did.
MAX_REPORTED = 10


@dataclass(frozen=True)
class FloorAudit:
    """What a sweep compared, against which declarations, in which environment.

    #17558: the previous return was ``(shortfalls, declarations_read)``, and
    ``render`` printed the second number as though it were the number of
    comparisons. It is not. A package declared but not installed is dropped by
    ``installed_versions`` and compared against nothing, so "128 declarations
    checked, all satisfied" could be true of an environment holding 86 of them.
    Measured on one developer box: 128 declared, 42 never compared.

    ``roots`` and ``environment`` are carried because a floor result is
    meaningless without both. The same deployed venv reports ``22 of 216 NOT
    satisfied`` against every declaration root and ``94 ... all satisfied``
    against the root that actually builds it -- both true, answering different
    questions, and neither line said which.
    """

    shortfalls: tuple[Shortfall, ...]
    #: Declarations parsed out of ``roots``.
    declared: int
    #: Declarations that had an installed version to compare against.
    compared: int
    #: Declared names with nothing installed -- not compared, not satisfied.
    not_installed: tuple[str, ...]
    #: The declaration entry points swept, as given.
    roots: tuple[str, ...]
    #: The interpreter inspected, named.
    environment: str
    #: Declared names installed but with unreadable metadata. NOT compared and
    #: NOT below floor -- a third state, kept separate from both (#17610 review).
    unreadable: tuple[str, ...] = ()
    #: Declarations, not names, that produced no comparison. The complement of
    #: `compared` in the same unit so the two can be read together.
    not_compared_declarations: int = 0
    #: True when ``roots`` is every declaration entry point rather than a
    #: set chosen for this environment. Carried rather than re-derived so
    #: this module needs nothing from the checker -- the banner loads that
    #: module by file location, where a sibling import would not resolve.
    roots_are_the_union: bool = False


def render(
    result: FloorAudit,
    limit: int = MAX_REPORTED,
    *,
    in_ci: bool = False,
    gating: bool = False,
    deployed: bool = False,
) -> list[str]:
    """The report, one line per element; *limit* caps the per-package detail.

    #17558: every block states its ROLE and its SCOPE. Three readers in one day
    each misread a floor block -- twice as a build failure it was not, once as a
    clean environment it was not -- because an informational banner and a gating
    check print in the same shape, and neither names the declarations it
    compared against. So:

    * ``gating`` says whether a shortfall here fails the caller. A block that
      cannot fail anything says so, in the first line, where it is read.
    * ``roots`` and the environment are always printed. A number without them
      answers an unstated question.
    * a pass reports COMPARISONS, never declarations read, and names what it
      could not compare. "did not look" must never render as "nothing found".
    """
    role = "GATE" if gating else "report only (informational; nothing here fails this run)"
    scope = f"roots: {', '.join(result.roots)}"
    # #17610 review: `not_installed` is de-duplicated by package name, so the
    # old wording counted distinct PACKAGES while reading as declarations. Both
    # units are now named, and unreadable metadata is reported as its own state
    # rather than folded into either.
    parts = []
    if result.not_installed:
        parts.append(f"{len(result.not_installed)} distinct package(s) not installed")
    if result.unreadable:
        parts.append(f"{len(result.unreadable)} installed but version UNREADABLE, so unverified")
    if parts:
        uncompared = f"{result.not_compared_declarations} declaration(s) not compared -- " + "; ".join(parts)
    else:
        uncompared = "every declaration had a readable installed version to compare"

    # #17610 review: with `--require-present` an absent declaration becomes an
    # ABSENT shortfall, but `compared` excludes absent declarations -- so the
    # headline could read "12 of 5". Absences are counted on their own line
    # below; they must not also sit in the numerator of a comparison count.
    # #17610 review: UNREADABLE is excluded too. An installed package whose
    # metadata cannot be read was never compared, so calling it "below its
    # declared floor" states a verdict no measurement supports. It is reported
    # on its own line as unverified.
    below_floor = tuple(s for s in result.shortfalls if s.installed not in (ABSENT, UNREADABLE))

    if not result.shortfalls:
        return [
            f"dependency floors [{role}]: {result.compared} of {result.declared} "
            f"declarations compared against {result.environment}, all satisfied",
            f"  {uncompared}",
            f"  {scope}",
        ]

    lines = [
        f"dependency floors [{role}]: {len(below_floor)} of {result.compared} "
        f"compared versions are below their declared floor in {result.environment}.",
        f"  {result.declared} declarations read; {uncompared}",
        f"  {scope}",
    ]
    if deployed:
        lines.extend(f"  {shortfall.describe()}" for shortfall in result.shortfalls[:limit])
        if len(result.shortfalls) > limit:
            # Without this the deployed report silently truncated and never said
            # so -- a list that hides entries without admitting it (#17502).
            lines.append(f"  ... and {len(result.shortfalls) - limit} more; re-run with --all to list them")
        lines.append(
            "This is a DEPLOYED environment, not a local or CI one: these are the versions "
            "actually serving traffic. Changing them goes through the builtin updater, never "
            "an ad-hoc pip install."
        )
        if result.roots_are_the_union:
            # #17558: the union includes planes that do not build this venv, so
            # a shortfall here may be correct about a declaration that never
            # governed it. Advisory until the caller scopes it.
            lines.append(
                "  ADVISORY: compared against EVERY declaration root, including planes that "
                "may not build this environment. Pass --roots <the file that builds it> for a "
                "verdict about this venv rather than about the union."
            )
        return lines

    if in_ci:
        lines.append(
            "This IS the CI job's own environment -- these are the packages CI itself "
            "installed, below the floor it declares, not a stand-in for it."
        )
    else:
        lines.append("A pass here therefore carries no information about CI, which installs the declared set.")
    lines.extend(f"  {shortfall.describe()}" for shortfall in result.shortfalls[:limit])
    if len(result.shortfalls) > limit:
        remaining = len(result.shortfalls) - limit
        lines.append(f"  ... and {remaining} more; run pipeline-scripts/check_dependency_floors.py --all to list them")
    lines.append("Reproduce the declared environment: scripts/setup-ci-parity-env.sh")
    lines.append("Otherwise push and read CI. Known divergence: #15093 (include_router defers).")
    return lines
