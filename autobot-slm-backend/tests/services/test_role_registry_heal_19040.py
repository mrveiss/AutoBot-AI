# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A stored role row holding the retired slm-agent playbook path heals at seed time (#19040).

test_role_registry.py is at its size ceiling, so this lives beside it and loads that module by
path to reuse its sqlalchemy/models shims (it restores sys.modules itself, #11478).
"""

from __future__ import annotations

import asyncio
import importlib.util
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

_PATH = Path(__file__).with_name("test_role_registry.py")
_SPEC = importlib.util.spec_from_file_location("_role_registry_shims_19040", _PATH)
_shims = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_shims)

_rr = _shims._rr
DEFAULT_ROLES = _shims.DEFAULT_ROLES


def test_seed_default_roles_heals_the_old_slm_agent_playbook_path():
    idx, target = next((i, r) for i, r in enumerate(DEFAULT_ROLES) if r["name"] == "slm-agent")
    existing = types.SimpleNamespace(**dict(target))
    existing.ansible_playbook = "deploy-slm-agent.yml"

    results = [_shims._Result(existing if i == idx else None) for i in range(len(DEFAULT_ROLES))]
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=results)
    db.commit = AsyncMock()
    db.add = MagicMock()

    asyncio.run(_rr.seed_default_roles(db))

    assert existing.ansible_playbook == "playbooks/deploy-slm-agent.yml"
    db.commit.assert_awaited()
