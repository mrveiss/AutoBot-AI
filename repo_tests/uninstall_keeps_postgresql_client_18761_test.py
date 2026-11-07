# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Removing PostgreSQL never purges its client, which KEPT_PACKAGES promises to keep (#18761).

`postgresql-*` also matches postgresql-client-NN. This runs the real plan_packages()
from scripts/uninstall.sh against a stubbed dpkg-query, both with and without the removal.
"""

from __future__ import annotations

import re
import subprocess

from repo_tests._paths import repo_root

_SCRIPT = repo_root() / "scripts/uninstall.sh"
_INSTALLED = [
    "postgresql-16",
    "postgresql-client-16",
    "postgresql-client-common",
    "postgresql-common",
    "postgresql-client",
    "postgresql-contrib-16",
    "redis-server",
]


def _plan(decision: str) -> set[str]:
    text = _SCRIPT.read_text(encoding="utf-8")
    consts = "\n".join(re.findall(r"^readonly POSTGRES_(?:PACKAGES|CLIENT_RE)=.*$", text, re.M))
    func = re.search(r"^plan_packages\(\) \{.*?^\}", text, re.M | re.S)
    assert len(consts.splitlines()) == 2 and func, "plan_packages or its constants moved -- update this test"
    installed = " ".join(_INSTALLED)
    stub = f"""
set -euo pipefail
INSTALLED="{installed}"
dpkg-query() {{  # -W -f=FMT PATTERN: every installed name matching the glob
    local pat="${{@: -1}}" n
    for n in $INSTALLED; do [[ "$n" == $pat ]] && echo "$n install ok installed"; done
    return 0
}}
record_values() {{ return 0; }}
PURGE_SHARED=false
SHARED_PACKAGES=()
POSTGRES_DECISION="{decision}"
{consts}
{func.group(0)}
plan_packages
"""
    out = subprocess.run(["bash", "-c", stub], capture_output=True, text=True, check=True, timeout=30)
    return set(out.stdout.split())


def test_removing_postgresql_purges_the_server_but_not_the_client() -> None:
    plan = _plan("remove")
    assert {"postgresql-16", "postgresql-common", "postgresql-contrib-16"} <= plan, plan
    assert not {p for p in plan if p.startswith("postgresql-client")}, plan


def test_contrast_keeping_postgresql_plans_none_of_it() -> None:
    assert not {p for p in _plan("keep") if p.startswith("postgresql")}
