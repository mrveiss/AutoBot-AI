# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Co-located managed-role ansible procedure runner, split out of
``api/code_sync.py`` (#16640).

``api/code_sync.py`` sits at its #14236 ceiling: #16640 needs this function to
REPORT which roles failed, not just log it, and a grandfathered file may not
grow. Moved here rather than raising the ceiling, the same #15881 precedent as
``api/_resume_plan.py`` (see its module docstring).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:  # pragma: no cover - typing only
    from api.code_sync import UpdateAllStage

logger = logging.getLogger(__name__)


def _log(stage: "UpdateAllStage", msg: str) -> None:
    """Mirrors ``code_sync._stage_log`` -- too small to justify importing it
    back and risking a cycle for four lines."""
    stage.log_lines.append(msg)
    if len(stage.log_lines) > 200:
        stage.log_lines = stage.log_lines[-200:]
    logger.info("[update-all:%s] %s", stage.name, msg)


async def run_colocated_role_procedures(stage: "UpdateAllStage", roles: list, slm_node_id: str) -> List[str]:
    """Run the full ansible procedure for each role (#12083); per-role
    failures are non-fatal, returned as "<name>: <reason>" lines (#16640)."""
    from api.roles import run_role_full_procedure

    failed: List[str] = []
    for role in roles:
        try:
            result = await run_role_full_procedure(role, slm_node_id)
        except Exception as exc:
            _log(stage, f"co-located {role.name}: resolve error: {exc} (#12083)")
            failed.append(f"{role.name}: resolve error: {exc}")
            continue
        if result.get("error") == "no_playbook":
            _log(stage, f"co-located {role.name}: no ansible_playbook configured — skipped (#12083)")
            continue
        ok = result.get("success")
        outcome = "ok" if ok else f"FAILED ({result.get('error', 'see output')})"
        if not ok:
            failed.append(f"{role.name}: {result.get('error', 'see output')}")
        _log(stage, f"co-located {role.name}: {outcome} via {role.ansible_playbook} (#12083)")
    return failed
