# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for the autobot_app DB credential source (#12883).

The .env regen in PLAY 2 was unreachable until #12871 was fixed. The first time
it ran it rendered a value PostgreSQL rejects, because it read the app DB
password from /etc/autobot/autobot-db-credentials.env — a file observed a month
stale on a live host. The value that actually authenticates lives in
/etc/autobot/db-credentials.env, which PLAY 1 already treats as canonical.

Two properties have to hold, and the second is the subtle one:

  1. the canonical store is read first, legacy only as a fallback;
  2. the LAST occurrence of the key wins. db-credentials.env is appended to
     rather than rewritten, so the key can appear twice with the current value
     last. `set -a; . file` resolves that to the last assignment, so a `head -1`
     here would silently pick the stale copy and reintroduce the outage.

Test 2 executes the extraction snippet rather than pattern-matching it, so the
behaviour is pinned even if the shell is rewritten.
"""

import re
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_PLAYBOOK = (
    Path(__file__).resolve().parents[1] / "ansible" / "playbooks" / "update-all-nodes.yml"
)
_CANONICAL = "/etc/autobot/db-credentials.env"
_LEGACY = "/etc/autobot/autobot-db-credentials.env"


def _read_task_cmd() -> str:
    """Return the shell body of the task that reads the app DB password."""
    plays = yaml.safe_load(_PLAYBOOK.read_text(encoding="utf-8"))
    for play in plays:
        for task in play.get("tasks") or []:
            name = task.get("name", "")
            if "autobot_app DB password" in name:
                return task["ansible.builtin.shell"]["cmd"]
    raise AssertionError("no task reading the autobot_app DB password found")


def test_prefers_canonical_store_over_legacy() -> None:
    """The canonical store must be consulted before the legacy file (#12883)."""
    cmd = _read_task_cmd()

    assert _CANONICAL in cmd, f"canonical store {_CANONICAL} is not read at all"
    assert cmd.index(_CANONICAL) < cmd.index(
        _LEGACY
    ), "legacy store is read before the canonical one — that is the #12883 outage"


def test_takes_the_last_occurrence_not_the_first() -> None:
    """Guard the last-wins requirement against a `head -1` regression (#12883)."""
    cmd = _read_task_cmd()

    assert "tail -n 1" in cmd, "extraction must take the LAST match (append-only file)"
    assert not re.search(r"\bhead\b", cmd), "head would select the stale first copy"


def test_extraction_resolves_duplicate_keys_to_the_current_value(tmp_path) -> None:
    """Run the real snippet against an append-style file with a duplicated key."""
    canonical = tmp_path / "db-credentials.env"
    canonical.write_text(
        "AUTOBOT_DB_USER=autobot_app\n"
        "AUTOBOT_DB_PASSWORD=stale-first-copy\n"
        "AUTOBOT_DB_USER=autobot_app\n"
        "AUTOBOT_DB_PASSWORD=current-last-copy\n",
        encoding="utf-8",
    )
    legacy = tmp_path / "autobot-db-credentials.env"
    legacy.write_text("AUTOBOT_DB_PASSWORD=legacy-should-not-be-used\n", encoding="utf-8")

    snippet = _read_task_cmd().replace(_CANONICAL, str(canonical)).replace(_LEGACY, str(legacy))
    out = subprocess.run(
        ["bash", "-c", snippet], capture_output=True, text=True, check=True, timeout=30
    )

    assert out.stdout == "current-last-copy", (
        f"expected the last occurrence, got {out.stdout!r} — "
        "a head/first-match read reintroduces #12883"
    )


def test_falls_back_to_legacy_when_canonical_absent(tmp_path) -> None:
    """Hosts provisioned before the canonical store still resolve a value."""
    canonical = tmp_path / "db-credentials.env"  # deliberately not created
    legacy = tmp_path / "autobot-db-credentials.env"
    legacy.write_text("AUTOBOT_DB_PASSWORD=legacy-value\n", encoding="utf-8")

    snippet = _read_task_cmd().replace(_CANONICAL, str(canonical)).replace(_LEGACY, str(legacy))
    out = subprocess.run(
        ["bash", "-c", snippet], capture_output=True, text=True, check=True, timeout=30
    )

    assert out.stdout == "legacy-value", f"fallback did not resolve, got {out.stdout!r}"
