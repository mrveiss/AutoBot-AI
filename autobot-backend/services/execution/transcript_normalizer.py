# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One pure normalizer for agent transcripts (#11137).

Decodes three on-disk/stream shapes into the same :class:`StepEvent`:

* Claude Code -- the ``--output-format stream-json`` CLI stream and the saved session
  JSONL (``user`` / ``assistant`` records whose ``message.content`` is a list of blocks);
* Codex / OpenAI -- ``response_item`` records (``message``, ``function_call``,
  ``function_call_output``), bare or wrapped in a ``payload``;
* prompt histories -- ``history.jsonl`` lines (prompt, project, timestamp) as
  :class:`EvidenceEntry`.

Everything except the file helpers at the bottom is pure: no I/O, no logging of content.
Transcripts carry private text; this module never logs a decoded line, only counts.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_constants import CategoryDefaults

logger = get_logger(__name__)

_USER = CategoryDefaults.ROLE_USER
_ASSISTANT = CategoryDefaults.ROLE_ASSISTANT
_GZIP_SUFFIX = ".gz"
_TRANSCRIPT_GLOBS = ("*.jsonl", "*.jsonl.gz")
_CODEX_TEXT_BLOCKS = frozenset({"input_text", "output_text", "text"})


@dataclass
class StepEvent:
    """A single decoded step: ``message`` | ``tool_use`` | ``tool_result`` | ``error`` | ``complete``."""

    kind: str
    content: Dict[str, Any] = field(default_factory=dict)
    tool_name: str = ""
    tool_id: str = ""
    role: str = ""  # set by the saved-transcript decoders; the spawned-run stream leaves it empty
    timestamp: str = ""


@dataclass(frozen=True)
class EvidenceEntry:
    """One ``history.jsonl`` prompt, as evidence (prompt + project + timestamp)."""

    prompt: str
    project: str
    timestamp: str  # ISO-8601 UTC, "" when the record had none
    session_id: str = ""


# ---------------------------------------------------------------------------
# Claude Code: block decoding (shared by the spawned-run stream and saved transcripts)
# ---------------------------------------------------------------------------


def _block_event(block: Dict[str, Any]) -> Optional[StepEvent]:
    """The StepEvent for one assistant content block, or None for kinds we do not surface."""
    btype = block.get("type", "")
    if btype == "text":
        return StepEvent(kind="message", content={"text": block.get("text", "")})
    if btype == "tool_use":
        return StepEvent(
            kind="tool_use",
            content={"input": block.get("input", {})},
            tool_name=block.get("name", ""),
            tool_id=block.get("id", ""),
        )
    return None


def first_assistant_event(blocks: Iterable[Dict[str, Any]]) -> Optional[StepEvent]:
    """The first text/tool_use block as an event -- the spawned-run stream's contract."""
    for block in blocks:
        event = _block_event(block)
        if event is not None:
            return event
    return None


def parse_cli_event(obj: Dict[str, Any]) -> Optional[StepEvent]:
    """Decode one ``stream-json`` object; None for an unrecognised ``type``."""
    ev_type = obj.get("type", "")
    if ev_type == _ASSISTANT:
        return first_assistant_event(obj.get("message", {}).get("content", []))
    if ev_type == "tool_result":
        return StepEvent(
            kind="tool_result",
            content={"output": obj.get("output", ""), "is_error": obj.get("is_error", False)},
            tool_id=obj.get("tool_use_id", ""),
        )
    if ev_type == "result":
        keys = ("subtype", "is_error", "result", "usage")
        defaults = ("", False, "", {})
        return StepEvent(kind="complete", content={k: obj.get(k, d) for k, d in zip(keys, defaults)})
    if ev_type == "error":
        return StepEvent(kind="error", content={"error": obj.get("error", obj)})
    return None


def parse_cli_line(raw: str) -> Optional[StepEvent]:
    """Parse one JSONL line from ``claude --output-format stream-json``; None to skip."""
    raw = raw.strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parse_cli_event(obj) if isinstance(obj, dict) else None


def _user_block_event(block: Dict[str, Any], stamp: str) -> Optional[StepEvent]:
    btype = block.get("type", "")
    if btype == "text":
        return StepEvent("message", {"text": block.get("text", "")}, role=_USER, timestamp=stamp)
    if btype == "tool_result":
        content = {"output": block.get("content", ""), "is_error": block.get("is_error", False)}
        return StepEvent("tool_result", content, tool_id=block.get("tool_use_id", ""), role=_USER, timestamp=stamp)
    return None


def _message_blocks(message: Any) -> List[Dict[str, Any]]:
    """``message.content`` as a block list (a bare string becomes one text block)."""
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return [b for b in content or [] if isinstance(b, dict)]


def normalize_claude_record(obj: Dict[str, Any]) -> List[StepEvent]:
    """Every surfaced event of one saved Claude Code transcript record (thinking is dropped)."""
    role = obj.get("type", "")
    if role not in (_USER, _ASSISTANT):
        return []
    stamp = str(obj.get("timestamp", ""))
    events: List[StepEvent] = []
    for block in _message_blocks(obj.get("message")):
        event = _block_event(block) if role == _ASSISTANT else _user_block_event(block, stamp)
        if event is not None:
            event.role, event.timestamp = role, stamp
            events.append(event)
    return events


# ---------------------------------------------------------------------------
# Codex / OpenAI response items
# ---------------------------------------------------------------------------


def _codex_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    parts = [b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") in _CODEX_TEXT_BLOCKS]
    return "\n".join(p for p in parts if p)


def _codex_arguments(raw: Any) -> Any:
    """Function-call arguments arrive as a JSON string; keep the raw string when it is not JSON."""
    if not isinstance(raw, str):
        return raw if raw is not None else {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _codex_item_event(item: Dict[str, Any], stamp: str) -> Optional[StepEvent]:
    itype = item.get("type", "")
    if itype == "message":
        role = item.get("role", "")
        return StepEvent("message", {"text": _codex_text(item.get("content"))}, role=role, timestamp=stamp)
    if itype in ("function_call", "custom_tool_call"):
        args = _codex_arguments(item.get("arguments", item.get("input")))
        return StepEvent(
            "tool_use",
            {"input": args},
            tool_name=item.get("name", ""),
            tool_id=item.get("call_id", ""),
            role=_ASSISTANT,
            timestamp=stamp,
        )
    if itype in ("function_call_output", "custom_tool_call_output"):
        content = {"output": item.get("output", ""), "is_error": False}
        return StepEvent("tool_result", content, tool_id=item.get("call_id", ""), role=_USER, timestamp=stamp)
    return None


def normalize_codex_record(obj: Dict[str, Any]) -> List[StepEvent]:
    """The event of one Codex rollout line: wrapped (``response_item``) or a bare item."""
    stamp = str(obj.get("timestamp", ""))
    if obj.get("type") == "response_item":
        item = obj.get("payload")
    elif obj.get("type") in ("message", "function_call", "function_call_output"):
        item = obj
    else:
        return []
    event = _codex_item_event(item, stamp) if isinstance(item, dict) else None
    return [event] if event is not None else []


# ---------------------------------------------------------------------------
# Format dispatch and prompt histories
# ---------------------------------------------------------------------------


def normalize_record(obj: Dict[str, Any]) -> List[StepEvent]:
    """Decode a saved-transcript record whichever agent wrote it."""
    if obj.get("type") in (_USER, _ASSISTANT):
        return normalize_claude_record(obj)
    return normalize_codex_record(obj)


def _iso_from_epoch_ms(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value) if isinstance(value, str) else ""
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()


def parse_history_line(raw: str) -> Optional[EvidenceEntry]:
    """One ``history.jsonl`` line as an evidence entry; None for blank/invalid/promptless lines."""
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    prompt = obj.get("display") if isinstance(obj, dict) else None
    if not isinstance(prompt, str) or not prompt.strip():
        return None
    return EvidenceEntry(
        prompt=prompt,
        project=str(obj.get("project", "")),
        timestamp=_iso_from_epoch_ms(obj.get("timestamp")),
        session_id=str(obj.get("sessionId", "")),
    )


# ---------------------------------------------------------------------------
# File helpers: gzip transparent, batches of files or directories
# ---------------------------------------------------------------------------


def iter_lines(path: Path) -> Iterator[str]:
    """Lines of ``path``, gunzipped when it ends in ``.gz``; always utf-8."""
    opener = gzip.open if path.suffix == _GZIP_SUFFIX else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield line


def expand_paths(paths: Iterable[Path]) -> List[Path]:
    """Files as given; a directory contributes its (sorted) ``*.jsonl`` / ``*.jsonl.gz`` files."""
    out: List[Path] = []
    for path in paths:
        path = Path(path)
        out.extend(sorted(f for pat in _TRANSCRIPT_GLOBS for f in path.glob(pat)) if path.is_dir() else [path])
    return out


def read_transcript(path: Path) -> List[StepEvent]:
    """Every event of one saved transcript; malformed lines are counted, never echoed."""
    events: List[StepEvent] = []
    skipped = 0
    for line in iter_lines(Path(path)):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        events.extend(normalize_record(obj) if isinstance(obj, dict) else [])
    if skipped:
        logger.warning("transcript %s: %d malformed line(s) skipped", Path(path).name, skipped)
    return events


def read_transcripts(paths: Iterable[Path]) -> Dict[str, List[StepEvent]]:
    """Batch read: ``{file path: events}`` for every file (directories expanded)."""
    return {str(p): read_transcript(p) for p in expand_paths(paths)}


def read_history(path: Path) -> List[EvidenceEntry]:
    """Every prompt of a ``history.jsonl`` (plain or gzipped) as evidence entries."""
    entries = (parse_history_line(line) for line in iter_lines(Path(path)))
    return [e for e in entries if e is not None]
