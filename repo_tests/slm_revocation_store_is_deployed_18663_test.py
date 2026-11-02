# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The SLM's token-revocation store is one the SLM's own install always deploys (#18663 AC3).

SLM login fails closed when revocation cannot be checked (#16387). The store used to be Redis,
which nothing on a fresh SLM host deploys, so a completed install could not log in (#18663).
#18673 moved both stores -- the jti denylist and the password epoch -- into the SLM's own
PostgreSQL. This ties that dependency to the deploy, so neither side can move alone:
  1. both stores reach only the SLM database (``services.database.db_service``), never Redis;
  2. ``deploy-slm-manager.yml``'s SLM play applies the ``postgresql`` role;
  3. ``install.sh`` runs that playbook without skipping the role's tag.
A store moved to a backend the install does not deploy, or an install that stops deploying
PostgreSQL, fails here before it fails on a host.
"""

from __future__ import annotations

import ast
import re

import yaml
from repo_tests._paths import repo_root

_ROOT = repo_root()
_SLM = _ROOT / "autobot-slm-backend"
_STORES = (_SLM / "services" / "token_denylist.py", _SLM / "services" / "password_epoch_store.py")
_PLAYBOOK = _SLM / "ansible" / "playbooks" / "deploy-slm-manager.yml"


def store_backends(source: str) -> set[str]:
    """Which backends a store imports: 'slm-db' and/or 'redis' -- read from its imports, not its
    prose, since the docstrings explain the move away from Redis."""
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            module, names = node.module or "", {a.name for a in node.names}
        elif isinstance(node, ast.Import):
            module, names = "", {a.name for a in node.names}
        else:
            continue
        if module == "services.database" and "db_service" in names:
            found.add("slm-db")
        if "redis" in module.lower() or any("redis" in n.lower() for n in names):
            found.add("redis")
    return found


def test_both_revocation_stores_use_only_the_slm_database() -> None:
    for store in _STORES:
        assert store_backends(store.read_text(encoding="utf-8")) == {
            "slm-db"
        }, f"{store.name} no longer uses only the SLM database"


def test_the_slm_play_deploys_postgresql() -> None:
    plays = yaml.safe_load(_PLAYBOOK.read_text(encoding="utf-8"))
    slm_plays = [p for p in plays if isinstance(p, dict) and p.get("hosts") == "slm_server" and p.get("roles")]
    assert slm_plays, "deploy-slm-manager.yml has no slm_server play with roles"
    roles = [r["role"] if isinstance(r, dict) else r for r in slm_plays[0]["roles"]]
    assert "postgresql" in roles, f"the SLM play no longer deploys the revocation store's database: {roles}"


def _deploy_slm_manager_command(install: str) -> str:
    """The `ansible-playbook ... deploy-slm-manager.yml ...` command, joined from its continuation lines.

    A line scan, not a backtracking regex (CodeQL py/redos on the earlier pattern).
    """
    lines = install.splitlines()
    for start, line in enumerate(lines):
        if not line.strip().startswith("ansible-playbook"):
            continue
        end = start
        while lines[end].rstrip().endswith("\\") and end + 1 < len(lines):
            end += 1
        command = "\n".join(lines[start : end + 1])
        if "playbooks/deploy-slm-manager.yml" in command:
            return command
    return ""


def test_install_sh_does_not_skip_the_postgresql_role() -> None:
    install = (_ROOT / "install.sh").read_text(encoding="utf-8")
    run = _deploy_slm_manager_command(install)
    assert run, "install.sh no longer runs deploy-slm-manager.yml"
    assert '--skip-tags "${skip_tags}"' in run, "the run no longer takes its skip set from skip_tags"
    skipped = re.findall(r'skip_tags="([\w,]+)"', install)
    assert skipped, "skip_tags is not assigned a literal, so this test reads nothing"
    assert all("postgresql" not in s.split(",") for s in skipped), f"install.sh skips the database: {skipped}"


def test_contrast_the_detectors_fire() -> None:
    assert store_backends("from services.database import db_service\n") == {"slm-db"}
    assert store_backends("from autobot_shared.redis_client import get_redis_client\n") == {"redis"}
    assert store_backends('"""Moved off Redis."""\nfrom services.database import db_service\n') == {"slm-db"}
    assert re.findall(r'skip_tags="([\w,]+)"', 'local skip_tags="seed,postgresql"') == ["seed,postgresql"]
