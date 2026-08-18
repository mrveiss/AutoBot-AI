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


def compute_drift(
    production: dict[str, str], ci: dict[str, str], allowlist: set[str]
) -> tuple[list[str], list[str]]:
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
    if problems:
        logger.error("%s", "\n\n".join(problems))
        logger.error("\nrequirements-ci drift audit FAILED over %d production package(s) (#14551).", reached)
        return 1
    logger.info("requirements-ci drift audit clean over %d production package(s) (#14551).", reached)
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
