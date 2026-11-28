# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Report missing ``requirements.txt`` deps in the pytest session header (#22259).

Moved out of ``conftest.py`` so that file stays within its size ratchet. The hook is imported
back into the conftest namespace, which is where pytest discovers it.
"""

from __future__ import annotations

from pathlib import Path

_REQUIREMENTS_FILE = Path(__file__).resolve().parent.parent / "requirements.txt"


# -- Requirements.txt enforcement (Issue #5032 / #5044) --------------------
# Tests that use optional parsers like bs4 declare `pytest.importorskip(...)`
# so they skip gracefully. But a silent skip of ~10% of the suite looks like
# a passing run to an inattentive reviewer. This session hook reads
# requirements.txt and reports which declared deps are not installed, so the
# developer sees a clear "run pip install -r requirements.txt" hint at the
# top of every test run instead of silent skip messages buried further down.
#
# Uses importlib.metadata.distribution() to check installed-ness by dist name
# (the exact name from requirements.txt) — no module-name translation needed,
# and no __init__.py side-effects like find_spec() would cause.


def _parse_requirements(path: Path) -> list[str]:
    """Return package names declared in a requirements.txt file."""
    names: list[str] = []
    if not path.exists():
        return names
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip().split("#", 1)[0].strip()
        if not line or line.startswith("-"):  # skip comments, blanks, -r/-e flags
            continue
        # Strip version specifiers and extras
        for sep in ("==", ">=", "<=", "~=", ">", "<", "!=", "["):
            if sep in line:
                line = line.split(sep, 1)[0].strip()
        if line:
            names.append(line)
    return names


def pytest_report_header(config) -> list[str]:
    """Report missing requirements.txt deps in the pytest session header.

    Does NOT fail the session — stubs in this conftest and `pytest.importorskip`
    calls in test files still handle graceful degradation. Purpose is to
    surface the root cause when tests silently skip due to missing deps.
    """
    from importlib import metadata as _im

    req_file = _REQUIREMENTS_FILE
    declared = _parse_requirements(req_file)
    if not declared:
        return []

    missing: list[str] = []
    for dist in declared:
        try:
            _im.distribution(dist)
        except _im.PackageNotFoundError:
            missing.append(dist)

    if not missing:
        return [f"requirements.txt: all {len(declared)} deps installed"]

    preview = ", ".join(missing[:8]) + ("..." if len(missing) > 8 else "")
    return [
        f"requirements.txt: {len(missing)}/{len(declared)} deps NOT installed ({preview})",
        "    Run: pip install -r autobot-backend/requirements.txt",
        "    Tests using these deps will skip; see importorskip messages below.",
    ]
