# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15298 -- the windows-npu-worker `transformers` pin must stay bounded.

Before #15298 this file carried a bare `transformers>=4.36.0`: a fresh resolve
could land on any 5.x release, including the one that dropped `resume_download`
(#15054, fixed everywhere else by pinning `>=5.15.1`/`>=5.16.1`). An unbounded
floor is not "not affected" -- it is one dependency bump away from being
affected, silently, on a file dependabot already reaches (#14562).

The fix pins this file to `transformers==5.16.1` -- the exact version
`requirements-ci/ai-ml.txt` already pins, i.e. this tree's own convention for a
reproducible, already-vetted version. This guard fails if the pin regresses to
a bare, unbounded `>=`.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_REQUIREMENTS = (
    _REPO_ROOT / "autobot-npu-worker" / "resources" / "windows-npu-worker" / "requirements.txt"
)

_TRANSFORMERS_LINE = re.compile(r"^transformers\s*(?P<spec>[^#\n]*)", re.M)
_HAS_UPPER_BOUND = re.compile(r"(<=|<|==)\s*\d")


def _transformers_spec() -> str:
    text = _REQUIREMENTS.read_text(encoding="utf-8")
    match = _TRANSFORMERS_LINE.search(text)
    assert match, f"{_REQUIREMENTS}: declares no transformers requirement — this test names the wrong file"
    return match.group("spec").strip()


def test_the_file_still_declares_transformers():
    """A guard over nothing is worth nothing -- the source must exist and parse."""
    assert _transformers_spec(), f"{_REQUIREMENTS}: transformers has no specifier at all"


def test_the_transformers_pin_is_bounded():
    """A bare `>=` admits any future major -- the exact defect #15298 fixed.

    Any of `==`, `<`, `<=` bounds the resolve; a spec containing only `>=`/`>`
    (or no operator) does not and must fail here.
    """
    spec = _transformers_spec()
    assert _HAS_UPPER_BOUND.search(spec), (
        f"{_REQUIREMENTS}: transformers{spec} has no upper bound or exact pin — a fresh "
        "resolve can land on any future major release (#15298)"
    )


def test_the_pin_matches_the_known_good_version():
    """Pinned to the exact version requirements-ci/ai-ml.txt already vetted (#15298).

    Not a floor comparison: this file deliberately exact-pins rather than
    tracking the `>=5.16.1` floor the docker/ai-stack/tts-worker siblings use,
    so drifting to a *different* exact version is itself worth catching even
    though it would still satisfy "bounded".
    """
    assert _transformers_spec() == "==5.16.1", (
        f"{_REQUIREMENTS}: transformers{_transformers_spec()} no longer matches the vetted "
        "==5.16.1 pin (#15298) — if this is a deliberate bump, update this test's expectation "
        "alongside it"
    )
