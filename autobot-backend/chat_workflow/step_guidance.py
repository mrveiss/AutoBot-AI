# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What the next continuation prompt tells the model about the step that just ran (#22252, #22253).

A step shows its return code. A step that failed, or printed a usage text, adds the command's manual synopsis
(from the existing ``CommandManualManager``; no second manual store) and, for a usage text, the instruction that
the arguments were wrong. A command with no manual says so, so the model reads ``--help`` instead of guessing.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Dict, List, Optional

from autobot_shared.logging_manager import get_logger
from chat_workflow.step_outcome import did_execute
from security.command_segments import command_segments

logger = get_logger(__name__)

#: How much of a manual one prompt carries, and for how many commands of a pipeline.
MANUAL_SYNOPSIS_CHARS = 600
MANUAL_OPTION_LIMIT = 6
MANUAL_COMMAND_LIMIT = 2

_USAGE_RE = re.compile(r"^\s*(usage|synopsis)\s*:", re.IGNORECASE | re.MULTILINE)
_ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_WRAPPERS = frozenset({"sudo", "env", "time", "nohup", "timeout"})

USAGE_GUIDANCE = (
    "**The last command printed a usage/help text: the arguments were wrong. Read the usage line above and "
    "correct the command before trying another tool.**"
)


def return_code_line(result: Dict[str, Any]) -> str:
    """``\\n- Return code: N`` for a step that carries an exit code; empty for one that never ran (#22252)."""
    code = result.get("return_code")
    return "" if code is None else f"\n- Return code: {code}"


def prints_usage(result: Dict[str, Any]) -> bool:
    """Whether the step's output is a usage/help text (a ``Usage:`` header)."""
    text = "\n".join(str(result.get(key) or "") for key in ("stdout", "stderr", "output"))
    return bool(_USAGE_RE.search(text))


def _failed(result: Dict[str, Any]) -> bool:
    code = result.get("return_code")
    return did_execute(result) and (str(result.get("status", "")).lower() == "error" or code not in (None, 0))


def command_names(command: str) -> List[str]:
    """The distinct program names a command line runs, in order and bounded; wrappers and assignments skipped."""
    names: List[str] = []
    for segment in command_segments(command or ""):
        words = [w for w in segment.split() if not _ENV_ASSIGNMENT_RE.match(w) and w not in _WRAPPERS]
        base = words[0].rsplit("/", 1)[-1] if words else ""
        if base and base not in names:
            names.append(base)
    return names[:MANUAL_COMMAND_LIMIT]


@lru_cache(maxsize=1)
def _manual_manager():
    """The one ``CommandManualManager``, on the configured knowledge-base database."""
    from command_manual_manager import CommandManualManager
    from utils.paths_manager import PathsManager

    return CommandManualManager(db_path=str(PathsManager.get_knowledge_base_db()))


def manual_synopsis(name: str) -> str:
    """A bounded synopsis of *name*'s stored manual, or a line saying there is none."""
    try:
        manual = _manual_manager().get_manual(name)
    except Exception as exc:  # noqa: BLE001 - an unreadable manual store is reported as such, never as "no manual"
        logger.warning("Command manual store unreadable for %s: %s", name, exc)
        return f"- `{name}`: the manual store could not be read; run `{name} --help`."
    if manual is None:
        return f"- `{name}`: no manual entry is available; run `{name} --help` to read its usage."
    parts = [manual.syntax or manual.description]
    if manual.common_options:
        parts.append("Options: " + "; ".join(manual.common_options[:MANUAL_OPTION_LIMIT]))
    return f"- `{name}`: " + " ".join(p for p in parts if p)[:MANUAL_SYNOPSIS_CHARS]


def latest_step_guidance(history: List[Dict[str, Any]]) -> Optional[str]:
    """Guidance for the next prompt after the most recent step, or ``None`` when it needs none (#22252, #22253)."""
    if not history:
        return None
    step = history[-1]
    usage = prints_usage(step)
    if not (usage or _failed(step)):
        return None
    lines = [USAGE_GUIDANCE] if usage else []
    names = command_names(str(step.get("command") or ""))
    if names:
        lines.append("**Manual for the command that just failed:**\n" + "\n".join(manual_synopsis(n) for n in names))
    return "\n".join(lines) if lines else None
