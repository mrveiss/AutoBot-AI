#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14550 — system packages ansible installs on hosts are absent from CI runners.

``autobot-slm-backend/ansible/roles/backend/tasks/main.yml`` installs a set of
apt packages on every backend host because some feature does not work without
them (GUI/VNC automation, audio/voice processing, TTS, OCR, matplotlib's Tk
backend, ``pg_dump``). ``setup-python-suite`` installs Python dependencies
only, so a test gated on one of those binaries being on ``PATH`` — via
``shutil.which(...)`` inside a ``pytest.mark.skipif`` or an in-body
``pytest.skip`` — has been silently skipping in CI, and a skip is
indistinguishable from a pass in the job summary.

As of this guard landing, every existing ``tesseract`` call site in the test
tree is fully mocked (``sys.modules`` stubs), so no CURRENT test needs the
real binary — not a bug on its own, but the *pattern* generalises to any
capability whose real-binary test lands without the matching apt install
already in place. #14550 found one live instance: ``media/audio/
ffmpeg_service_test.py::test_real_audio_extraction`` skips "FFmpeg not
installed" on every CI run because ffmpeg was never provisioned — fixed in
the same PR that added this guard, by installing ffmpeg in
``.github/actions/setup-python-suite/action.yml``. A real ``tesseract``
call-site gate landing later (tracked separately; not yet merged as of this
writing) will be caught by this same guard the day it appears, since
:data:`BINARY_TO_PACKAGE` already maps ``tesseract`` to ``tesseract-ocr``.

Design, deliberately narrow:

* Only the FEATURE packages ansible installs are in scope
  (:data:`FEATURE_PACKAGES`) — the Python-build toolchain
  (``build-essential``, ``libssl-dev``, ``git``, ``curl``, ...) is excluded on
  purpose: ``actions/setup-python`` ships a prebuilt interpreter so CI never
  compiles Python from source, and ``git``/``curl`` are already present on
  every GitHub-hosted runner image, so flagging them would be a false
  positive, not a finding.
* Only :data:`BINARY_TO_PACKAGE` binaries are matched — a ``shutil.which()``
  call naming some other tool (``bash``, ``node``, ``rsync``, ...) is out of
  this ansible role's scope entirely and is left alone.
* A binary is "gated" when ``shutil.which("name")`` is followed within a few
  lines by ``skipif`` or ``pytest.skip(`` — covering both the decorator and
  the in-body-skip style already used in this repo.

WHY THIS IS A SCRIPT AND NOT ONLY A TEST. The failure direction needs a
REQUIRED check: a test file moving, or the ansible task being renamed, both
make the scan find fewer gated binaries, so this reports FEWER problems and
goes GREENER. ``.github/workflows/code-quality.yml`` calls this module with
``--audit``, the same shape as ``check_flake8_exclude_anchoring.py
--audit-excludes``. ``repo_tests/ci_system_package_provisioning_test.py``
imports these functions rather than restating the rule.
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import re
import sys

# Plain stdlib logging (matching check_flake8_exclude_anchoring.py and
# check_requirements_ci_drift.py): this runs inside `code-quality`, which
# installs linters only, never the application's own dependencies.
logger = logging.getLogger(__name__)


_ANSIBLE_BACKEND_TASKS = "autobot-slm-backend/ansible/roles/backend/tasks/main.yml"
_ANSIBLE_TASK_NAME = "Backend | Install backend-specific system dependencies"
_SETUP_ACTION = ".github/actions/setup-python-suite/action.yml"

#: Every repo-relative path this checker reads. code-quality.yml's
#: dorny/paths-filter `backend` list must cover each of these, or a PR that
#: touches only one of them skips the required check entirely -- verified by
#: tools/lint/check_code_quality_guard_reach.py and
#: repo_tests/code_quality_guard_reach_test.py.
GUARD_INPUT_PATHS = (_ANSIBLE_BACKEND_TASKS, _SETUP_ACTION)

#: Python-build toolchain packages ansible installs so pyenv/deadsnakes can
#: compile CPython from source, plus baseline tools every GitHub-hosted
#: runner image already ships. Out of scope for this guard — see module
#: docstring. THIS SET IS DELIBERATELY FIXED, not derived, because widening
#: it is exactly the failure direction this guard exists to catch: an entry
#: added here silently exempts a real feature package from provisioning.
TOOLCHAIN_PACKAGES = frozenset(
    {
        "build-essential",
        "libssl-dev",
        "zlib1g-dev",
        "libbz2-dev",
        "libreadline-dev",
        "libsqlite3-dev",
        "libncursesw5-dev",
        "xz-utils",
        "tk-dev",
        "libxml2-dev",
        "libxmlsec1-dev",
        "libffi-dev",
        "liblzma-dev",
        "git",
        "curl",
    }
)

#: Binaries this guard knows to look for, mapped to the apt package that
#: provides them. Only binaries ansible installs via the backend role belong
#: here — add an entry when a new feature package gains a real-binary test.
BINARY_TO_PACKAGE = {
    "ffmpeg": "ffmpeg",
    "ffprobe": "ffmpeg",
    "tesseract": "tesseract-ocr",
    "Xvfb": "xvfb",
    "espeak-ng": "espeak-ng",
    "espeak": "espeak-ng",
    "pg_dump": "postgresql-client",
}

#: Function calls that indirectly probe for a binary WITHOUT ever calling
#: ``shutil.which`` -- e.g. a library's own version check raises when the
#: underlying binary is missing. A guard that only matched the literal
#: ``shutil.which("x")`` shape would keep reporting a binary "no real test,
#: out of scope" the day a gate using one of these lands instead. Mapped to
#: the same package namespace as BINARY_TO_PACKAGE, keyed by binary name.
PROBE_CALL_TO_BINARY = {
    "get_tesseract_version(": "tesseract",
}

#: Floor for the ansible package enumeration. A parse that resolved to fewer
#: than this many packages means the task moved or was renamed, not that the
#: role shrank — the pre-guard baseline has 13 feature packages.
FEATURE_PACKAGE_FLOOR = 10

_APT_LIST_ITEM_RE = re.compile(r"^\s*-\s*([A-Za-z0-9][A-Za-z0-9.+-]*)\s*$")
_SHUTIL_WHICH_RE = re.compile(r"""shutil\.which\(\s*["']([^"']+)["']\s*\)""")
_PROBE_CALL_RE = re.compile("|".join(re.escape(call) for call in PROBE_CALL_TO_BINARY))
_APT_INSTALL_LINE_RE = re.compile(r"apt(?:-get)?\s+install[^\n]*")


def repo_root() -> pathlib.Path:
    """Repo root derived from this file, never from the caller's cwd."""
    return pathlib.Path(__file__).resolve().parents[2]


def ansible_feature_packages(root: pathlib.Path | None = None) -> set[str]:
    """Packages the backend ansible role installs, minus the build toolchain."""
    base = root if root is not None else repo_root()
    path = base / _ANSIBLE_BACKEND_TASKS
    if not path.is_file():
        return set()
    text = path.read_text(encoding="utf-8")
    idx = text.find(_ANSIBLE_TASK_NAME)
    if idx == -1:
        return set()
    block = text[idx:]
    end = block.find("state: present")
    if end != -1:
        block = block[:end]
    packages = set()
    for line in block.splitlines():
        match = _APT_LIST_ITEM_RE.match(line)
        if match:
            packages.add(match.group(1))
    return packages - TOOLCHAIN_PACKAGES


def ci_installed_packages(root: pathlib.Path | None = None) -> set[str]:
    """Packages installed by an `apt-get install` / `apt install` line in the CI action."""
    base = root if root is not None else repo_root()
    path = base / _SETUP_ACTION
    if not path.is_file():
        return set()
    packages: set[str] = set()
    for install_line in _APT_INSTALL_LINE_RE.findall(path.read_text(encoding="utf-8")):
        for token in install_line.split():
            if token in ("apt", "apt-get", "install", "-y", "--yes", "-qq", "sudo"):
                continue
            packages.add(token)
    return packages


def _test_files(root: pathlib.Path) -> list[pathlib.Path]:
    """Tracked test files, matching pytest.ini's own collection patterns exactly.

    ``pytest.ini`` sets ``python_files = test_*.py *_test.py`` — BOTH prefix
    and suffix conventions are collected (``transcriber/tests/test_export_api.py``
    is prefix-style). Globbing only the suffix form would under-scan relative
    to what pytest itself actually runs, the same "guard narrower than its own
    subject" shape this guard exists to close.

    Filters on the path RELATIVE to `root`, not the absolute path — `root`
    itself commonly sits inside a `.worktrees/<branch>/` checkout, and an
    absolute-path check would exclude every file it found (#14550 caught
    this against its own guard before it ever reached CI).
    """
    candidates = set(root.glob("**/*_test.py"))
    candidates.update(root.glob("**/test_*.py"))
    candidates.update(p for p in root.glob("**/tests/**/*.py") if p.is_file())
    excluded = {"node_modules", "__pycache__"}
    return [p for p in candidates if not excluded & set(p.relative_to(root).parts)]


def _match_gated_binary(line: str) -> str | None:
    """The binary a line's ``shutil.which(...)`` or a known probe call names.

    Two independent shapes reach the same binary: a direct PATH lookup, or a
    library call that raises unless the underlying binary works (e.g.
    ``pytesseract.get_tesseract_version()``, which calls ``tesseract``
    without ever touching ``shutil.which``). Missing the second shape would
    keep reporting that binary "no real test, out of scope" the day a gate
    using it lands.
    """
    which_match = _SHUTIL_WHICH_RE.search(line)
    if which_match and which_match.group(1) in BINARY_TO_PACKAGE:
        return which_match.group(1)
    probe_match = _PROBE_CALL_RE.search(line)
    if probe_match:
        return PROBE_CALL_TO_BINARY[probe_match.group(0)]
    return None


#: Substrings whose presence within a few lines of a matched binary marks it
#: "gated" -- pytest's three shapes for making a test conditional. Checked as
#: plain substrings, not `importorskip(` alone, so `pytest.skip(` does not
#: accidentally match inside a longer `pytest.importorskip(` call (it does
#: NOT: "skip(" is a substring of "importorskip(", but "pytest.skip(" is not,
#: since "importor" sits between them -- kept as three explicit, disjoint
#: markers instead of relying on that overlap not mattering by accident).
_SKIP_MARKERS = ("skipif", "pytest.skip(", "importorskip(")


def gated_binaries(root: pathlib.Path | None = None) -> list[tuple[str, str, int]]:
    """Every ``(binary, relative_file, lineno)`` where a known binary is skip-gated.

    "Gated" means :func:`_match_gated_binary` matches within a few lines of
    one of :data:`_SKIP_MARKERS` — covering the decorator style
    (ffmpeg_service_test.py), the in-body ``pytest.skip(`` style, an indirect
    probe, and ``pytest.importorskip(`` (the style scikit-learn/ldap3/etc. use).
    """
    base = root if root is not None else repo_root()
    findings: list[tuple[str, str, int]] = []
    for path in _test_files(base):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(lines, start=1):
            binary = _match_gated_binary(line)
            if binary is None:
                continue
            window = "\n".join(lines[max(0, lineno - 4) : lineno + 2])
            if any(marker in window for marker in _SKIP_MARKERS):
                findings.append((binary, str(path.relative_to(base)), lineno))
    return findings


def audit_provisioning(root: pathlib.Path | None = None) -> tuple[int, list[str]]:
    """Apply the invariant. Returns ``(gated_binaries_found, problems)``."""
    base = root if root is not None else repo_root()
    problems: list[str] = []

    packages = ansible_feature_packages(base)
    if len(packages) < FEATURE_PACKAGE_FLOOR:
        return 0, [
            f"{_ANSIBLE_BACKEND_TASKS} yielded only {len(packages)} feature package(s) "
            f"(floor {FEATURE_PACKAGE_FLOOR}) — the task moved or was renamed, so the "
            "guard checked nothing."
        ]

    ci_packages = ci_installed_packages(base)
    findings = gated_binaries(base)

    if not findings:
        return 0, [
            "found zero shutil.which(...) skip-gates on a tracked binary across the test "
            "tree — either the pattern changed shape or the test files moved; the guard "
            "would otherwise report a comfortable zero having checked nothing."
        ]

    for binary, rel_path, lineno in sorted(findings):
        pkg = BINARY_TO_PACKAGE[binary]
        if pkg not in packages:
            continue  # ansible does not install this one; out of this guard's scope
        if pkg in ci_packages:
            continue  # provisioned — the test genuinely runs
        problems.append(
            f"{rel_path}:{lineno} skip-gates on `{binary}` (package `{pkg}`), which "
            f"ansible installs on every backend host but {_SETUP_ACTION} does not "
            "install on the CI runner — this test has been silently skipping, not "
            "passing (#14550). Add the package to the CI action's apt install step."
        )

    return len(findings), problems


def configure_logging() -> None:
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def run_audit() -> int:
    reached, problems = audit_provisioning()
    if problems:
        logger.error("%s", "\n\n".join(problems))
        logger.error("\nCI system-package provisioning audit FAILED over %d gated binary/ies (#14550).", reached)
        return 1
    logger.info("CI system-package provisioning audit clean over %d gated binary/ies (#14550).", reached)
    return 0


def main(argv: list[str]) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--audit",
        action="store_true",
        help="verify every shutil.which()-gated test's package is installed in CI",
    )
    args = parser.parse_args(argv)
    if not args.audit:
        parser.error("nothing to do — pass --audit")
    return run_audit()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
