#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for check_no_kb_aioredis_access (#5225 / #14181).

Written while waking the hook, which had never run because its exec bit was
not tracked (#14181). Nothing had ever exercised it, which is why a typo in
its own ALLOWLIST went unnoticed.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404  # git plumbing, fixed argv, no shell
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_no_kb_aioredis_access import ALLOWLIST, _scan  # noqa: E402

_REPO = Path(__file__).resolve().parents[2]


def _write(tmp: Path, name: str, body: str) -> Path:
    path = tmp / name
    path.write_text(body, encoding="utf-8")
    return path


def test_every_allowlist_entry_names_a_file_that_exists() -> None:
    """An allowlist entry that names a moved file exempts nothing, silently.

    #14181: the entry for the KB integration test read
    `knowledge_base.integration_test.py`. It was correct when written
    (d67a6574f, #5330); `3302e3f7f` renamed 44 dotted test filenames to the
    underscore form (#7082) and left this reference behind. Six init-state
    assertions the allowlist was written to exempt were reported as
    violations instead.

    A stale path is indistinguishable from a correct one until something
    runs, and this hook never had. Bulk renames are exactly when references
    like this go stale, which is why the invariant is asserted rather than
    the one instance.
    """
    listing = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "ls-files"], cwd=str(_REPO), capture_output=True, text=True
    )
    assert listing.returncode == 0, "git ls-files failed — refusing to report clean"
    tracked = set(listing.stdout.split())
    assert tracked, "git ls-files listed nothing — refusing to report clean"

    missing = sorted(entry for entry in ALLOWLIST if entry not in tracked)
    assert not missing, f"ALLOWLIST names paths that do not exist: {missing}"


def test_the_allowlist_is_enforced_not_just_declared() -> None:
    """Membership and enforcement are independent; only the second matters."""
    for name in sorted(ALLOWLIST):
        path = _REPO / name
        if not path.is_file() or path.suffix != ".py":  # pragma: no cover
            continue
        assert _scan(path, _REPO) == [], f"{name} is allowlisted but still reported violations"


def test_an_external_read_of_the_private_client_is_blocked() -> None:
    """The defect #5225 actually banned: a caller reaching into KB internals."""
    body = "async def go(kb):\n    await kb._aioredis_client.get('x')\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "caller.py", body)
        assert len(_scan(f, Path(d))) == 1


def test_the_public_accessor_passes() -> None:
    """A rule that flagged `kb.redis()` would block the fix it recommends."""
    body = "async def go(kb):\n    await kb.redis().get('x')\n"
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "ok.py", body)
        assert _scan(f, Path(d)) == []


def test_the_fake_kb_helper_is_exempt_for_a_stated_reason() -> None:
    """`fake_kb.py` *defines* the attribute on its stubs so their own `redis()`
    has something to return — it does not reach into a real KnowledgeBase.

    Pinned because the distinction is the whole basis for exempting it, and a
    future reader deleting the entry would reintroduce three violations that
    are not violations.
    """
    assert "autobot-backend/tests/helpers/fake_kb.py" in ALLOWLIST
    source = (_REPO / "autobot-backend/tests/helpers/fake_kb.py").read_text(encoding="utf-8")
    assert re.search(r"def redis\(self\)", source), "the fake must expose the public accessor it stands in for"
