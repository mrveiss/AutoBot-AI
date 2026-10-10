# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SLM backend's SQLAlchemy cap must survive an automated bump (#17445).

`autobot-slm-backend/requirements.txt` caps SQLAlchemy `<2.1` because 2.1.0 kills
27 tests inside SQLAlchemy's own cache-key machinery -- `TypeError:
'InternalTraversal' object is not callable`, raised in `sql/_cache_key_cy.py` with
no project frame in the failing call. The cap is a **deferral**, recorded on
#17445, and its paragraph says not to raise the bound without running the SLM
suite against 2.1.x first.

**A comment did not hold it.** #17706 proposed `sqlalchemy>=2.1.0,<2.2` and left
that paragraph in place directly above the line it contradicted. The existing
`update-types: ["version-update:semver-major"]` ignore did not stop it either,
because 2.0 -> 2.1 is a **minor** -- the same shape as openai (#14431) and
protobuf (#14727), where a grouped `all-dependencies` bump walked past
`update-types`.

So the freeze is asserted here, in the two places that together make it hold: the
pin itself, and a `versions` range in the dependabot config that a grouped bump
cannot route around.

**What this cannot assert:** that dependabot's next run does not propose it
anyway. That is observable only in the run. A test over config shape is evidence
about the config, not about the bot's behaviour, and must not be read as the
second thing.
"""

from __future__ import annotations

import re

import pytest

yaml = pytest.importorskip("yaml")

from repo_tests._paths import repo_root  # noqa: E402

_CONFIG = repo_root() / ".github" / "dependabot.yml"
_REQUIREMENTS = repo_root() / "autobot-slm-backend" / "requirements.txt"
_CEILING = "2.1"


def _slm_pip_block() -> dict:
    document = yaml.safe_load(_CONFIG.read_text(encoding="utf-8"))
    blocks = [
        update
        for update in document["updates"]
        if update.get("package-ecosystem") == "pip" and update.get("directory") == "/autobot-slm-backend"
    ]
    assert len(blocks) == 1, f"expected exactly one pip block for /autobot-slm-backend, found {len(blocks)}"
    return blocks[0]


def _sqlalchemy_ignore() -> dict:
    entries = [i for i in _slm_pip_block().get("ignore", []) if i.get("dependency-name") == "sqlalchemy"]
    assert entries, (
        "no dependabot ignore entry for sqlalchemy in the /autobot-slm-backend block. "
        "Without it a grouped all-dependencies bump re-proposes the cap raise every week (#17706)."
    )
    assert len(entries) == 1, f"{len(entries)} sqlalchemy ignore entries; one of them is dead config"
    return entries[0]


def _excludes_the_ceiling(versions: list[str]) -> bool:
    """True when *versions* bars everything at or above the ceiling."""
    for spec in versions:
        match = re.fullmatch(r"\s*>=\s*([0-9][0-9.]*)\s*", spec)
        if match and _le(match.group(1), _CEILING):
            return True
    return False


def _le(left: str, right: str) -> bool:
    """Numeric version comparison, zero-padded to equal length.

    Padding is the whole point: bare tuple comparison makes `(2, 1, 0) <= (2, 1)`
    False, because a prefix sorts first. That read `>=2.1.0` as NOT barring 2.1 --
    caught by this module's own contrast pair rather than in review.
    """

    def parts(v: str) -> list[int]:
        return [int(p) for p in v.split(".") if p.isdigit()]

    a, b = parts(left), parts(right)
    width = max(len(a), len(b))
    a += [0] * (width - len(a))
    b += [0] * (width - len(b))
    return a <= b


def test_the_cap_is_still_in_the_requirements_file() -> None:
    text = _REQUIREMENTS.read_text(encoding="utf-8")
    pin = re.search(r"^sqlalchemy\s*([^\s#]+)", text, re.M | re.I)
    assert pin, "no sqlalchemy pin found in the SLM requirements at all"
    assert "<2.1" in pin.group(1), (
        f"the SQLAlchemy cap is gone -- the pin now reads `{pin.group(1)}`. "
        "2.1.x kills 27 tests in this service (#17445). Raising this bound requires running "
        "the SLM suite against 2.1.x, which is #17445's work, not a dependency bump's."
    )


def test_the_pin_tells_the_reader_why_it_is_capped() -> None:
    """A bare `<2.1` invites deletion by the next person who sees it as stale."""
    text = _REQUIREMENTS.read_text(encoding="utf-8")
    assert "#17445" in text, "the cap does not cite the issue that records why it exists"


def test_dependabot_excludes_the_minor_not_merely_the_major() -> None:
    entry = _sqlalchemy_ignore()
    versions = entry.get("versions") or []
    assert versions, (
        "the sqlalchemy ignore has no `versions` range. `update-types: semver-major` alone "
        "does NOT stop a grouped all-dependencies bump, and 2.0 -> 2.1 is a MINOR anyway -- "
        "which is exactly how #17706 rewrote the cap."
    )
    assert _excludes_the_ceiling(
        versions
    ), f"the ignore range {versions} does not bar >= {_CEILING}, so a 2.1 bump can still be proposed"


def test_the_exclusion_still_admits_patch_releases() -> None:
    """Bounded on purpose: 2.0.x security patches must keep arriving.

    The contrast with `ansible-core`, which is frozen outright. Reading one freeze
    as the template for every freeze is how a security patch gets silently barred.
    """
    versions = _sqlalchemy_ignore().get("versions") or []
    assert not any(
        re.fullmatch(r"\s*>=\s*0[.0]*\s*", v) or v.strip() in {"*", ">=0"} for v in versions
    ), f"the range {versions} bars everything, including 2.0.x security patches"


@pytest.mark.parametrize(
    ("versions", "expected"),
    [
        ([">=2.1"], True),
        ([">=2.1.0"], True),
        ([">=2.0"], True),  # stricter than needed, still bars 2.1
        ([">=2.2"], False),  # lets 2.1 through -- the bug this guards
        ([">=3.0.0"], False),
        ([], False),
    ],
)
def test_the_range_check_itself(versions: list[str], expected: bool) -> None:
    """Contrast pairs. A check that always returned True would pass the test above."""
    assert _excludes_the_ceiling(versions) is expected
