# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20761: secrets are compared through ``secure_compare`` only.

A raw ``compare_digest`` on ``str`` raises ``TypeError`` for non-ASCII input,
which was a 500 on a hostile header. One helper, no second copy.

Out of scope: ``docker/docker-proxy/proxy.py`` (outside the three trees; it
already compares encoded bytes, so it is safe).
"""

import re
from pathlib import Path

from repo_tests._reach import declare

_ROOT = Path(__file__).resolve().parent.parent
_TREES = ("autobot-backend", "autobot-slm-backend", "autobot_shared")
_HELPER = Path("autobot_shared/security/constant_time.py")
# Files another open PR owns; each entry is removed when that PR lands and the
# file is routed through secure_compare. A stale entry fails the test below.
_DEFERRED = {
    "autobot-backend/services/secrets_coordinator.py": "#21011 owns this file; route through secure_compare after it lands",
    "autobot_shared/auth/internal_api_key.py": "#20777 owns this file; it already compares UTF-8 bytes, route through secure_compare after it lands",
}
_CALL = re.compile(r"(?<!\w)(?:hmac|secrets)\.compare_digest\(|(?<![\w.])compare_digest\(")


def _production_files(root: Path = _ROOT):
    for tree in _TREES:
        for path in (root / tree).rglob("*.py"):
            rel = path.relative_to(root)
            name = path.name
            if rel == _HELPER or "tests" in rel.parts or name.startswith("test_") or name.endswith("_test.py"):
                continue
            yield rel, path


def _discover(root: Path) -> list[Path]:
    return [rel for rel, _ in _production_files(root)]


#: Measured at the time of writing: ~3500 production ``.py`` files under the three trees; the floor
#: leaves room for moves without letting an empty enumeration pass.
REACH = declare(
    "single-constant-time-compare",
    discover=_discover,
    floor=3556,  # mid-window: population 3556, window (3556, 3556)
    what="production python files",
    roots=_TREES,
)


def _offenders(text: str) -> list[int]:
    return [
        n for n, line in enumerate(text.splitlines(), 1) if _CALL.search(line) and not line.lstrip().startswith("#")
    ]


def test_no_raw_compare_digest_outside_the_helper() -> None:
    reached = REACH.examined(_ROOT)
    found = []
    for rel in reached:
        if rel.as_posix() in _DEFERRED:
            continue
        text = (_ROOT / rel).read_text(encoding="utf-8", errors="replace")
        found.extend(f"{rel}:{n}" for n in _offenders(text))
    REACH.completed(len(reached), _ROOT)
    assert found == [], f"use autobot_shared.security.constant_time.secure_compare: {found}"


def test_the_detector_sees_a_planted_call() -> None:
    assert _offenders("ok = hmac.compare_digest(a, b)") == [1]
    assert _offenders("ok = secrets.compare_digest(a, b)") == [1]
    assert _offenders("ok = secure_compare(a, b)") == []


def test_every_deferred_entry_still_has_a_raw_call() -> None:
    for name, reason in _DEFERRED.items():
        text = (_ROOT / name).read_text(encoding="utf-8")
        assert _offenders(text), f"{name} no longer has a raw compare_digest call; drop it from _DEFERRED ({reason})"
