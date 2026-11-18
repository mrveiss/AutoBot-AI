# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shape rules for a workflow's single trigger (#18390). Pure.

Only the keys this model itself needs are required. The shape of a schedule is
left to the scheduling work (#18432), and nothing here executes a trigger.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from llc.models.company_os_enums import WorkflowKind, WorkflowTriggerKind

from .errors import CompanyOsError

_REQUIRED_KEYS: Dict[WorkflowTriggerKind, Tuple[str, ...]] = {
    WorkflowTriggerKind.WORK_ITEM_STATUS: ("status",),
    WorkflowTriggerKind.FOLDER_FILE_ADDED: ("path",),
    WorkflowTriggerKind.PROCESS_RESULT: ("process_key", "result"),
}
_RESULTS = ("success", "failure")


def validate_trigger(
    kind: str, trigger_type: Optional[str], config: Optional[Dict[str, Any]]
) -> Tuple[Optional[str], Dict[str, Any]]:
    """Return the normalised ``(trigger_type, trigger_config)`` or raise."""
    config = dict(config or {})
    if kind == WorkflowKind.META_SKILL.value:
        if trigger_type is not None or config:
            raise CompanyOsError("a meta skill has no trigger")
        return None, {}
    try:
        trigger = WorkflowTriggerKind(trigger_type or WorkflowTriggerKind.MANUAL.value)
    except ValueError as exc:
        raise CompanyOsError(f"unknown trigger type {trigger_type!r}") from exc
    for key in _REQUIRED_KEYS.get(trigger, ()):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise CompanyOsError(f"a {trigger.value} trigger needs config.{key}")
    if trigger == WorkflowTriggerKind.PROCESS_RESULT and config["result"] not in _RESULTS:
        raise CompanyOsError(f"config.result must be one of {_RESULTS}")
    return trigger.value, config
