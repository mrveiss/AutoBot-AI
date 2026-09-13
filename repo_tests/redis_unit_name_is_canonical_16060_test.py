# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every path that manages Redis names the unit the role installs (#16060).

The fleet runs **Redis Stack** — `roles/redis` installs `redis-stack-server`,
and a live node confirms it: `/opt/redis-stack/bin/redis-server`, modules
`ReJSON`, `timeseries`, `search`. Neither `redis` nor `redis-server` is a unit
on a provisioned node; `systemctl show` reports `LoadState=not-found` for both.

Two hardcoded copies had drifted from that:

* `services/reconciler.py` looked for `["redis-server", "redis"]`, so it could
  not find the service it is responsible for reconciling.
* `services/backup.py` issued `systemctl stop redis-server` before a restore
  and **discarded the result**, so the stop failed silently and the RDB was
  replaced under a live server that then overwrote it on its next save.

The second is the reason this is a correctness fix rather than a naming one:
`systemctl stop` against a nonexistent unit fails, and an unchecked failure on
a restore path is indistinguishable from success.

These assertions read the SOURCE. A behavioural test would need a node, and
what is being pinned is that no third copy of the name appears — which is a
property of the tree, not of a run.
"""

from __future__ import annotations

import re

from repo_tests._paths import repo_root

_SLM = repo_root() / "autobot-slm-backend"

#: The unit `roles/redis` installs. Read from the role registry in the test
#: below rather than trusted from here; this is only the expected answer.
_CANONICAL = "redis-stack-server"

#: Units that do NOT exist on a provisioned node. Measured with
#: `systemctl show -p LoadState`: both report `not-found`.
_ABSENT = ("redis-server", "redis")


def _registry_unit() -> str | None:
    """The redis role's `systemd_service`, parsed from the registry source.

    Parsed rather than imported: `role_registry.py` imports `models.database`,
    which needs the package and its dependencies. What is being pinned is the
    declaration, and the declaration is what every caller resolves against.
    """
    import ast

    tree = ast.parse((_SLM / "services" / "role_registry.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        entry = {
            k.value: v.value
            for k, v in zip(node.keys, node.values)
            if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)
        }
        if entry.get("name") == "redis" and "systemd_service" in entry:
            return entry["systemd_service"]
    return None


def test_the_registry_names_the_stack_unit():
    """The single source. Everything else is asserted against this, not a literal."""
    assert _registry_unit() == _CANONICAL


def test_the_reconciler_looks_for_the_unit_that_exists():
    """It was looking for two units that are not on any provisioned node.

    Order matters: the canonical name must come first, so a node carrying both
    a legacy and a Stack unit resolves to the one the role installs.
    """
    source = (_SLM / "services" / "reconciler.py").read_text(encoding="utf-8")
    match = re.search(r'"redis":\s*\[([^\]]*)\]', source)
    assert match, "ROLE_SERVICE_MAP has no redis entry"
    candidates = [c.strip().strip('"') for c in match.group(1).split(",") if c.strip()]
    assert candidates[0] == _CANONICAL, (
        f"the reconciler tries {candidates} in order; {_CANONICAL} must be first "
        "because the others do not exist on a provisioned node (#16060)"
    )


def test_no_service_management_path_hardcodes_an_absent_unit():
    """The contrast that makes this a sweep rather than two edits.

    Keeping the legacy names as *fallbacks* is fine — a node provisioned before
    the Stack move still has them. Naming one in a `systemctl` command is not.
    """
    offenders = []
    for rel in ("services/backup.py", "services/reconciler.py", "api/services.py"):
        for line in (_SLM / rel).read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            # A comment naming the old unit is documentation, not a command.
            # The first draft of this guard flagged its own explanation of the
            # bug -- #16011's blindness, in the guard written to catch it.
            if stripped.startswith("#"):
                continue
            if "systemctl" in line and any(f" {absent}" in line for absent in _ABSENT):
                offenders.append(f"{rel}: {stripped}")
    assert not offenders, (
        "these issue systemctl against a unit that does not exist on a "
        f"provisioned node: {offenders}"
    )


def test_the_restore_refuses_to_proceed_when_the_stop_fails():
    """The defect that made this urgent.

    `await self._run_command(stop_cmd, timeout=30)` discarded its result, so a
    failed stop was invisible and the restore continued against a running
    server. A restore that cannot stop the server is not a restore.
    """
    source = (_SLM / "services" / "backup.py").read_text(encoding="utf-8")
    start = source.index("_stop_redis_for_restore")
    body = source[start : start + 1400]
    assert "raise" in body, (
        "the restore path does not fail when Redis cannot be stopped — it will "
        "replace the RDB under a live server (#16060)"
    )
