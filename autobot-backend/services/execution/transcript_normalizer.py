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
import os
import stat
import zlib
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.security.path_validator import validate_path
from autobot_shared.ssot_constants import CategoryDefaults

logger = get_logger(__name__)

_USER = CategoryDefaults.ROLE_USER
_ASSISTANT = CategoryDefaults.ROLE_ASSISTANT
#: Read bounds (env-backed): a hostile or corrupt file stops at these instead of exhausting memory.
MAX_DECOMPRESSED_BYTES: int = env_int_clamped("AUTOBOT_TRANSCRIPT_MAX_DECOMPRESSED_BYTES", 1 << 30, min_v=1)
MAX_LINE_BYTES: int = env_int_clamped("AUTOBOT_TRANSCRIPT_MAX_LINE_BYTES", 16 << 20, min_v=1)
MAX_EVENTS: int = env_int_clamped("AUTOBOT_TRANSCRIPT_MAX_EVENTS", 1_000_000, min_v=1)
MAX_RETAINED_BYTES: int = env_int_clamped("AUTOBOT_TRANSCRIPT_MAX_RETAINED_BYTES", 256 << 20, min_v=1)
#: Charged per retained event on top of its source bytes: the dataclass, its dicts and strings cost real memory.
EVENT_OVERHEAD_BYTES: int = env_int_clamped("AUTOBOT_TRANSCRIPT_EVENT_OVERHEAD_BYTES", 1024, min_v=0)
#: What a malformed line can raise from ``json.loads``: bad syntax, an oversized int, or recursion-deep nesting.
JSON_ERRORS = (ValueError, RecursionError)
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
    if not isinstance(block, dict):
        return None
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
        return first_assistant_event(_message_blocks(obj.get("message")))
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
    except JSON_ERRORS:
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
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


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
    if not isinstance(content, list):
        return ""
    blocks = (b for b in content if isinstance(b, dict) and b.get("type") in _CODEX_TEXT_BLOCKS)
    return "\n".join(t for t in (b.get("text") for b in blocks) if isinstance(t, str) and t)


def _codex_arguments(raw: Any) -> Any:
    """Function-call arguments arrive as a JSON string; keep the raw string when it is not JSON."""
    if not isinstance(raw, str):
        return raw if raw is not None else {}
    try:
        return json.loads(raw)
    except JSON_ERRORS:
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
    """ISO-8601 UTC for an epoch-ms number; ``ValueError`` when it is out of range, NaN or infinite."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value) if isinstance(value, str) else ""
    try:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError("timestamp out of range") from exc


def parse_history_line(raw: str) -> Optional[EvidenceEntry]:
    """One ``history.jsonl`` line as an evidence entry; None for blank/invalid/promptless lines."""
    try:
        obj = json.loads(raw)
    except JSON_ERRORS:
        return None
    prompt = obj.get("display") if isinstance(obj, dict) else None
    if not isinstance(prompt, str) or not prompt.strip():
        return None
    try:
        stamp = _iso_from_epoch_ms(obj.get("timestamp"))
    except ValueError:
        return None  # a malformed line: the caller counts it
    return EvidenceEntry(
        prompt=prompt,
        project=str(obj.get("project", "")),
        timestamp=stamp,
        session_id=str(obj.get("sessionId", "")),
    )


# ---------------------------------------------------------------------------
# File helpers: gzip transparent, batches of files or directories
# ---------------------------------------------------------------------------


@dataclass
class ReadResult:
    """What one bounded file read produced, and whether it is the whole file."""

    items: List[Any] = field(default_factory=list)
    truncated: bool = False
    truncated_reason: str = ""  # "decompressed_bytes" | "line_length" | "events" | "retained_bytes"
    skipped: int = 0  # malformed or undecodable lines, counted and never echoed
    retained_bytes: int = 0  # source bytes + per-event overhead behind ``items``; bounded by MAX_RETAINED_BYTES


@dataclass
class TranscriptBatchResult:
    """A batch read: the files that read (each possibly truncated) and the ones that failed."""

    results: Dict[str, ReadResult] = field(default_factory=dict)
    failed: Dict[str, str] = field(default_factory=dict)  # path -> exception class name only


def _lines_of(handle: Any, result: ReadResult) -> Iterator[str]:
    """Decoded non-blank lines of a binary handle, stopping (and saying so) at a size bound."""
    total = 0
    while True:
        raw = handle.readline(MAX_LINE_BYTES + 1)
        if not raw:
            return
        total += len(raw)
        if total > MAX_DECOMPRESSED_BYTES:
            result.truncated, result.truncated_reason = True, "decompressed_bytes"
            return
        if len(raw) > MAX_LINE_BYTES and not raw.endswith(b"\n"):
            result.truncated, result.truncated_reason = True, "line_length"
            return
        try:
            line = raw.decode("utf-8")
        except UnicodeDecodeError:
            result.skipped += 1
            continue
        if line.strip():
            yield line


def _checked(path: Path, allowed_roots: Sequence[str]) -> Path:
    """``path`` resolved (symlinks followed) and proven to lie under ``allowed_roots`` (canonical validator).

    The caller names the roots; ``ValueError`` when the path, or the target of a symlink, escapes them.
    """
    return validate_path(str(path), allowed_roots, must_exist=True)


def iter_lines(path: Path, result: ReadResult, allowed_roots: Sequence[str]) -> Iterator[str]:
    """Lines of the validated ``path`` (gunzipped for ``.gz``), bounded; limit hits are recorded on ``result``."""
    safe = _checked(path, allowed_roots)
    with _open_no_follow(safe) as handle:
        yield from _lines_of(handle, result)


@contextmanager
def _open_no_follow(safe: Path) -> Iterator[Any]:
    """Binary handle on the validated ``safe`` (gunzipped for ``.gz``), refusing a symlink swapped in since validation.

    ``O_NOFOLLOW`` makes the open fail (``OSError``, ELOOP) when the FINAL component is a symlink. It does not
    cover parent components: a directory swapped for a symlink between validation and open is still followed.
    """
    with os.fdopen(_open_regular_fd(safe), "rb") as raw:
        if safe.suffix != _GZIP_SUFFIX:
            yield raw
            return
        with gzip.GzipFile(fileobj=raw, mode="rb") as unzipped:
            yield unzipped


def _open_regular_fd(safe: Path) -> int:
    """A read-only descriptor on ``safe``, which must be a regular file; closed again on every failure path.

    ``O_NONBLOCK`` keeps a FIFO swapped in after validation from hanging the open; it has no effect on reads
    of a regular file. ``ValueError`` (like a validation failure) when the target is not a regular file.
    """
    fd = os.open(safe, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("not a regular file")
    except BaseException:
        os.close(fd)
        raise
    return fd


def _children(directory: Path) -> List[Path]:
    return sorted(f for pat in _TRANSCRIPT_GLOBS for f in directory.glob(pat))


def expand_paths(paths: Iterable[Path], allowed_roots: Sequence[str]) -> Tuple[List[Path], Dict[str, str]]:
    """``(files, rejected)``: validated files (a directory contributes its ``*.jsonl`` / ``*.jsonl.gz`` children).

    A path, or a child symlink, that fails validation lands in ``rejected`` as ``{path: exception class}``.
    """
    out: List[Path] = []
    rejected: Dict[str, str] = {}
    for path in paths:
        try:
            safe = _checked(path, allowed_roots)
        except ValueError as exc:
            rejected[str(path)] = type(exc).__name__
            continue
        for candidate in _children(safe) if safe.is_dir() else [safe]:
            try:
                out.append(_checked(candidate, allowed_roots))
            except ValueError as exc:
                rejected[str(candidate)] = type(exc).__name__
    return out, rejected


def _add_bounded(result: ReadResult, new_items: List[Any], cost: int) -> bool:
    """Append ``new_items`` (``cost`` source bytes plus per-event overhead); False once a bound is hit."""
    cost += EVENT_OVERHEAD_BYTES * len(new_items)
    room = MAX_EVENTS - len(result.items)
    if len(new_items) > room:
        result.items.extend(new_items[: max(room, 0)])
        result.truncated, result.truncated_reason = True, "events"
        return False
    if new_items and result.retained_bytes + cost > MAX_RETAINED_BYTES:
        result.truncated, result.truncated_reason = True, "retained_bytes"
        return False
    result.items.extend(new_items)
    result.retained_bytes += cost if new_items else 0
    return True


def read_transcript(path: Path, allowed_roots: Sequence[str]) -> ReadResult:
    """Events of one saved transcript under ``allowed_roots``. Bad lines are counted; a limit hit marks it truncated."""
    result = ReadResult()
    for line in iter_lines(Path(path), result, allowed_roots):
        try:
            obj = json.loads(line)
        except JSON_ERRORS:
            result.skipped += 1
            continue
        if isinstance(obj, dict) and not _add_bounded(result, normalize_record(obj), len(line)):
            break
    _log_read(path, result)
    return result


def _log_read(path: Path, result: ReadResult) -> None:
    name = Path(path).name
    if result.skipped:
        logger.warning("transcript %s: %d malformed line(s) skipped", name, result.skipped)
    if result.truncated:
        logger.warning("transcript %s: truncated (%s)", name, result.truncated_reason)


def read_transcripts(paths: Iterable[Path], allowed_roots: Sequence[str]) -> TranscriptBatchResult:
    """Batch read: one corrupt file is reported in ``failed`` (class name only), the rest still read."""
    batch = TranscriptBatchResult()
    files, batch.failed = expand_paths(paths, allowed_roots)
    for name in batch.failed:
        logger.warning("transcript %s: refused (outside the allowed roots or missing)", Path(name).name)
    for path in files:
        try:
            batch.results[str(path)] = read_transcript(path, allowed_roots)
        except (OSError, EOFError, zlib.error, ValueError, RecursionError) as exc:
            batch.failed[str(path)] = type(exc).__name__
            logger.warning("transcript %s: unreadable (%s)", Path(path).name, type(exc).__name__)
    return batch


def read_history(path: Path, allowed_roots: Sequence[str]) -> ReadResult:
    """Prompts of a ``history.jsonl`` (plain or gzipped) as evidence entries; bad lines are counted."""
    result = ReadResult()
    for line in iter_lines(Path(path), result, allowed_roots):
        entry = parse_history_line(line)
        if entry is None:
            result.skipped += 1
        elif not _add_bounded(result, [entry], len(line)):
            break
    _log_read(path, result)
    return result
