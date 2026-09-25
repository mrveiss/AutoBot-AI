#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14551 — production and CI Python dependency sets are hand-mirrored; catch silent drift.

``autobot-backend/requirements.txt`` and ``autobot-slm-backend/requirements.txt``
declare what production installs. ``requirements-ci.txt`` (which pulls in
``requirements-ci/*.txt``) is a SEPARATE, hand-maintained mirror that
``setup-python-suite`` actually installs — it never installs the backends' own
requirements files. A package declared in production and forgotten in the
mirror produces no error: the tests that need it simply never run, and any
that do exercise it fall back to a mocked/stubbed import instead.

That is exactly what happened to ``pytesseract`` (#13885): declared in
``autobot-backend/requirements.txt``, absent from every ``requirements-ci/*``
file, and every end-to-end OCR test skipped for months while the suite stayed
green throughout.

What this guard does NOT do: merge the two dependency sets. The role-based CI
split is deliberate (#1655) and CI legitimately omits some heavy production
deps (torch arrives transitively via sentence-transformers, per the CPU-index
resolution documented in ``requirements-ci/ai-ml.txt`` and #13316). The
allowlist at ``repo_tests/requirements_ci_drift_baseline.txt`` records those
deliberate omissions explicitly, so the diff is expected to be **exactly** that
list — any package missing from CI that is NOT on the list is a new,
undeclared drift and fails this check. The allowlist only ever shrinks: an
entry that no longer describes a real omission (the package was added to CI,
or removed from production) is a hard error too, in the style of
``sys_modules_leak_baseline.txt`` and ``extension_import_baseline.txt`` — a
stale allowlist entry exempts nothing while looking authoritative.

WHY THIS IS A SCRIPT AND NOT ONLY A TEST. The failure direction is what makes
this need a REQUIRED check, not documentation: shrinking the allowlist by
hand-adding a stale entry, or a requirements file silently resolving to zero
entries (a rename, a moved role), both make this check report FEWER problems,
i.e. go GREENER. Nothing about a merely-informational pytest run would notice.
``.github/workflows/code-quality.yml`` therefore calls this module with
``--audit``, mirroring ``check_flake8_exclude_anchoring.py --audit-excludes``
and ``check_python_file_size.py --audit-ceilings``.
``repo_tests/requirements_ci_drift_test.py`` imports these functions rather
than restating the rule, so there is one definition of "drift".
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import re
import sys

# Plain stdlib logging, deliberately (#1082, matching check_flake8_exclude_anchoring.py
# and check_python_file_size.py): this runs inside `code-quality`, which installs
# linters only — never the application's own dependencies — so
# `autobot_shared.logging_manager` is not importable here.
logger = logging.getLogger(__name__)


#: Production requirement files that declare what is actually deployed.
#: Deliberately excludes autobot-tts-worker/requirements.txt: its tests are
#: written to need neither torch nor pocket_tts (pytest.ini), so nothing in
#: the CI-scoped suite needs its deps mirrored — recorded here, not silently
#: dropped.
_PRODUCTION_REQUIREMENTS = ("autobot-backend/requirements.txt", "autobot-slm-backend/requirements.txt")

#: The CI mirror's entry point — pulls in requirements-ci/*.txt via -r includes.
_CI_REQUIREMENTS = "requirements-ci.txt"

#: One package name per (non-comment, non-blank) line. THIS LIST ONLY SHRINKS.
_ALLOWLIST_FILE = "repo_tests/requirements_ci_drift_baseline.txt"

#: Every repo-relative path/glob this checker reads. code-quality.yml's
#: dorny/paths-filter `backend` list must cover each of these, or a PR that
#: touches only one of them skips the required check entirely -- verified by
#: tools/lint/check_code_quality_guard_reach.py and
#: repo_tests/code_quality_guard_reach_test.py.
GUARD_INPUT_PATHS = (*_PRODUCTION_REQUIREMENTS, _CI_REQUIREMENTS, "requirements-ci/*.txt", _ALLOWLIST_FILE)

_NAME_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


def repo_root() -> pathlib.Path:
    """Repo root derived from this file, never from the caller's cwd."""
    return pathlib.Path(__file__).resolve().parents[2]


def _normalize(name: str) -> str:
    """PEP 503 style normalisation so `python_dotenv` and `python-dotenv` match."""
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_requirements(path: pathlib.Path, _seen: set[pathlib.Path] | None = None) -> dict[str, str]:
    """Parse a requirements file, following ``-r`` includes; skip ``-e``/``-c``/options.

    Returns ``{normalized_name: raw_line}``. A later declaration of the same
    package overwrites an earlier one, matching pip's own last-wins behaviour.
    """
    seen = _seen if _seen is not None else set()
    resolved = path.resolve()
    if resolved in seen or not resolved.is_file():
        return {}
    seen.add(resolved)

    out: dict[str, str] = {}
    for raw in resolved.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("-r "):
            out.update(parse_requirements((resolved.parent / line[3:].strip()), seen))
            continue
        if line.startswith("-e ") or line.startswith("-c ") or line.startswith("--"):
            continue
        match = _NAME_RE.match(line)
        if match:
            out[_normalize(match.group(1))] = line
    return out


def production_requirement_names(root: pathlib.Path | None = None) -> dict[str, str]:
    base = root if root is not None else repo_root()
    combined: dict[str, str] = {}
    for rel in _PRODUCTION_REQUIREMENTS:
        combined.update(parse_requirements(base / rel))
    return combined


def ci_requirement_names(root: pathlib.Path | None = None) -> dict[str, str]:
    base = root if root is not None else repo_root()
    return parse_requirements(base / _CI_REQUIREMENTS)


def load_allowlist(root: pathlib.Path | None = None) -> set[str]:
    base = root if root is not None else repo_root()
    path = base / _ALLOWLIST_FILE
    if not path.is_file():
        return set()
    names = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.split("#", 1)[0].strip()
        if stripped:
            names.add(_normalize(stripped))
    return names


def compute_drift(production: dict[str, str], ci: dict[str, str], allowlist: set[str]) -> tuple[list[str], list[str]]:
    """Return ``(new_drift, stale_allowlist_entries)``.

    ``new_drift`` — production packages missing from CI and NOT on the
    allowlist: an undeclared, silent omission.

    ``stale_allowlist_entries`` — allowlisted names that no longer describe a
    real omission, either because CI now installs them (the drift was fixed
    but the entry was never removed) or production no longer declares them
    (the package was dropped entirely). Both cases exempt nothing while
    looking authoritative, so both are hard errors, never a silent no-op.
    """
    missing = set(production) - set(ci)
    new_drift = sorted(missing - allowlist)
    stale = sorted(entry for entry in allowlist if entry not in missing)
    return new_drift, stale


#: Pairs whose CI and service constraints can already resolve differently.
#: One ``<service file>::<package>`` per line. **ONLY SHRINKS.**
_CONSTRAINT_BASELINE_FILE = "repo_tests/requirements_constraint_drift_baseline.txt"

#: A specifier that cannot float to the newest release. Two constraints that can
#: BOTH reach latest resolve to the same version however their floors differ, so
#: `>=2.0.52` vs `>=2.0.54` is not a divergence -- both take whatever is newest.
#: Divergence needs at least one side pinned or capped.
_BOUNDED = re.compile(r"(==|~=|<)")

_SPECIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:\[[^\]]*\])?\s*(.*)$")


def constraint_of(raw: str) -> str:
    """The version specifier from a raw requirement line; extras and markers dropped."""
    body = raw.split(";", 1)[0].strip()
    match = _SPECIFIER.match(body)
    return (match.group(1) or "").replace(" ", "") if match else ""


def can_resolve_differently(one: str, other: str) -> bool:
    """True when two specifiers for one package can install different releases."""
    if one == other:
        return False
    return bool(_BOUNDED.search(one) or _BOUNDED.search(other))


def load_constraint_baseline(root: pathlib.Path | None = None) -> set[str]:
    base = root if root is not None else repo_root()
    path = base / _CONSTRAINT_BASELINE_FILE
    if not path.is_file():
        return set()
    out: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            out.add(line)
    return out


def compute_constraint_drift(root: pathlib.Path | None = None) -> tuple[list[str], int]:
    """``(["<file>::<package>", ...], pairs compared)`` -- PER SERVICE FILE.

    Deliberately not against a merged "service plane". ``production_requirement_names``
    flattens both backends with last-wins, and they are allowed to disagree:
    ``websockets`` is capped ``<16`` in autobot-backend (langgraph-sdk needs it)
    and floored ``>=17.1`` in autobot-slm-backend, each with its own venv since
    #16394, each documented at its own site. Comparing a flattened plane would
    report that deliberate split as a conflict and train people to ignore this
    guard -- while still missing the real thing, because last-wins had already
    discarded one of the two constraints before the comparison ran.
    """
    base = root if root is not None else repo_root()
    ci = ci_requirement_names(base)
    found: list[str] = []
    compared = 0
    for rel in _PRODUCTION_REQUIREMENTS:
        service = parse_requirements(base / rel)
        for name in sorted(set(service) & set(ci)):
            compared += 1
            if can_resolve_differently(constraint_of(ci[name]), constraint_of(service[name])):
                found.append(f"{rel}::{name}")
    return found, compared


def audit_constraint_drift(root: pathlib.Path | None = None) -> tuple[int, list[str]]:
    """#17448: the two planes may declare a package, and still install different releases.

    #14551 above checks PRESENCE -- is the package mirrored into CI at all. It
    says so itself: "What this guard does NOT do: merge the two dependency
    sets." A package declared on both planes as ``==2.0.54`` and ``>=2.0.54``
    passes it cleanly, and that is exactly how the SLM test venv took SQLAlchemy
    2.1.0 while CI's own venv stayed on 2.0.54 -- 2.1 dropped ``greenlet`` as a
    hard dependency, nothing declared it directly, and every SLM test module
    failed at import (#17433). The migration gates hit the identical resolution
    from the identical cause a day later (#17499). Two point fixes, one
    unguarded mechanism, 50 more candidate pairs.
    """
    base = root if root is not None else repo_root()
    drift, compared = compute_constraint_drift(base)
    problems: list[str] = []
    if not compared:
        return 0, ["no package appears on both planes -- the constraint check compared nothing."]

    baseline = load_constraint_baseline(base)
    new = sorted(set(drift) - baseline)
    stale = sorted(baseline - set(drift))

    if new:
        problems.append(
            f"{len(new)} package(s) whose CI and service constraints can resolve to "
            f"different releases and are not recorded in {_CONSTRAINT_BASELINE_FILE}:\n"
            + "\n".join(f"  {entry}" for entry in new)
            + "\n\nCI pins what production runs; an unbounded service constraint takes "
            "whatever published last. Make the two agree, or record the pair with its reason "
            "(#17448)."
        )
    if stale:
        problems.append(
            f"stale entries in {_CONSTRAINT_BASELINE_FILE} (the pair now agrees, or the "
            f"package left a plane): {stale}. This list only shrinks -- delete these lines."
        )
    return compared, problems


def audit_drift(root: pathlib.Path | None = None) -> tuple[int, list[str]]:
    """Apply the invariant. Returns ``(packages_reached, problems)``.

    ``packages_reached`` is the size of the production set, counted from the
    parse so a requirements file that resolved to zero entries (a rename, a
    moved role) cannot report a clean scan of nothing.
    """
    base = root if root is not None else repo_root()
    production = production_requirement_names(base)
    ci = ci_requirement_names(base)
    problems: list[str] = []

    if not production:
        return 0, [f"{', '.join(_PRODUCTION_REQUIREMENTS)} parsed to zero packages — the guard checked nothing."]
    if not ci:
        return len(production), [f"{_CI_REQUIREMENTS} parsed to zero packages — the guard checked nothing."]

    allowlist = load_allowlist(base)
    new_drift, stale = compute_drift(production, ci, allowlist)

    if new_drift:
        lines = "\n".join(f"  {name}  ({production[name]})" for name in new_drift)
        problems.append(
            f"{len(new_drift)} package(s) declared in production but missing from "
            f"{_CI_REQUIREMENTS} / requirements-ci/*.txt, and not recorded in "
            f"{_ALLOWLIST_FILE}:\n{lines}\n"
            "Either mirror the package into the matching requirements-ci/*.txt file, "
            "or — if CI genuinely should not install it — add it to the allowlist with "
            "a comment explaining why (#14551)."
        )
    if stale:
        problems.append(
            f"stale entries in {_ALLOWLIST_FILE} (fixed or removed, but not deleted): "
            f"{stale}. The allowlist only shrinks — remove these lines (#14551)."
        )

    return len(production), problems


def configure_logging() -> None:
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def run_audit() -> int:
    reached, problems = audit_drift()
    pairs, constraint_problems = audit_constraint_drift()
    problems = [*problems, *constraint_problems]
    if problems:
        logger.error("%s", "\n\n".join(problems))
        logger.error(
            "\nrequirements-ci drift audit FAILED over %d production package(s) (#14551) "
            "and %d shared pair(s) (#17448).",
            reached,
            pairs,
        )
        return 1
    logger.info(
        "requirements-ci drift audit clean: %d production package(s) mirrored (#14551), "
        "%d shared pair(s) constraint-checked (#17448).",
        reached,
        pairs,
    )
    return 0


def main(argv: list[str]) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--audit",
        action="store_true",
        help="compare production requirements against requirements-ci and the allowlist",
    )
    args = parser.parse_args(argv)
    if not args.audit:
        parser.error("nothing to do — pass --audit")
    return run_audit()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
