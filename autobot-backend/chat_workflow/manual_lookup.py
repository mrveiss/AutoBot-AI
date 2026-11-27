# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Command manuals before a command runs: the ``command_manual`` tool and the pre-iteration fetch (#22253).

``step_guidance`` already adds a failed step's manual synopsis to the next prompt. This is the other half: the
model can ask for any command's manual (a read-only tool), and the manuals of the commands the user's message or
the current plan step name are put in the prompt before the model has tried them. Both read the one
``CommandManualManager`` through ``step_guidance.manual_synopsis``; there is no second manual store.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, AsyncIterator, Dict, List, Mapping, Optional

from async_chat_workflow import WorkflowMessage
from autobot_shared.logging_manager import get_logger
from chat_workflow.step_guidance import command_names, has_manual, manual_synopsis

logger = get_logger(__name__)

COMMAND_MANUAL_TOOL = "command_manual"

COMMAND_MANUAL_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "command": {
            "type": "string",
            "description": "The program name whose manual to read (e.g. 'ping'). Read-only; no approval needed.",
        },
    },
    "required": ["command"],
}

#: The names a pre-iteration fetch looks up, and how many manuals it puts in one prompt.
PRELOAD_TOKEN_LIMIT = 30
PRELOAD_MANUAL_LIMIT = 3

_PROGRAM_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_.+-]{0,31}")
_WORD = re.compile(r"[a-z][a-z0-9_.+-]{1,24}")


async def handle_command_manual(
    tool_call: Dict[str, Any], execution_results: List[Dict[str, Any]]
) -> AsyncIterator[WorkflowMessage]:
    """Answer a ``command_manual`` call with the command's bounded synopsis (or a line saying there is none)."""
    name = str((tool_call.get("params") or {}).get("command", "")).strip()
    if not _PROGRAM_NAME.fullmatch(name):
        text = "command_manual takes a program name (letters, digits, '_', '.', '+', '-'), e.g. 'ping'."
        execution_results.append({"tool": COMMAND_MANUAL_TOOL, "status": "error", "error": text})
        yield WorkflowMessage(type="error", content=text, metadata={"tool": COMMAND_MANUAL_TOOL, "error": True})
        return
    text = await asyncio.to_thread(manual_synopsis, name)
    execution_results.append({"tool": COMMAND_MANUAL_TOOL, "status": "success", "output": text})
    yield WorkflowMessage(
        type="command_output", content=text, metadata={"tool": COMMAND_MANUAL_TOOL, "status": "success"}
    )


def _already_worked(history: List[Dict[str, Any]]) -> set:
    """Program names a step in *history* already ran successfully: their manual is not needed up front."""
    done: set = set()
    for step in history or []:
        if step.get("return_code") == 0:
            done.update(command_names(str(step.get("command") or "")))
    return done


def _named_with_manual(text: str, skip: set) -> List[str]:
    """Words of *text* that name a command with a stored manual, in order of appearance and bounded."""
    seen: List[str] = []
    for word in _WORD.findall(text):
        if word not in seen and word not in skip:
            seen.append(word)
    found: List[str] = []
    try:
        for word in seen[:PRELOAD_TOKEN_LIMIT]:
            if has_manual(word):
                found.append(word)
            if len(found) == PRELOAD_MANUAL_LIMIT:
                break
    except Exception as exc:  # noqa: BLE001 - an unreadable store must not stop the turn; the tool still answers
        logger.warning("Command manual preload skipped: %s", exc)
    return found


def with_command_manuals(prompt: str, state: Mapping[str, Any], history: List[Dict[str, Any]] | None = None) -> str:
    """*prompt* plus the manuals of the commands this turn's message or current plan step name (#22253)."""
    block = manuals_for_prompt(
        str(state.get("user_message") or ""), (state.get("plan_progress") or {}).get("block", ""), history or []
    )
    return f"{prompt}\n\n{block}" if block else prompt


def manuals_for_prompt(user_message: str, plan_block: str, history: List[Dict[str, Any]]) -> Optional[str]:
    """Manual synopses of the commands the user's message or the current plan step name, else ``None`` (#22253).

    Commands a step already ran successfully are left out. Bounded: ``PRELOAD_MANUAL_LIMIT`` manuals of at most
    ``MANUAL_SYNOPSIS_CHARS`` each. A name with no stored manual is not mentioned (most words are not commands).
    """
    names = _named_with_manual(f"{user_message or ''}\n{plan_block or ''}", _already_worked(history))
    if not names:
        return None
    return "**Manuals for the commands this task names:**\n" + "\n".join(manual_synopsis(n) for n in names)
