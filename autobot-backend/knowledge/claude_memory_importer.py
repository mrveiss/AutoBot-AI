# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Import Claude Code auto-memory files into the knowledge_facts store (#16642).

Claude Code sessions maintain a curated per-project memory store on disk —
``<memory_dir>/*.md``, each with YAML frontmatter (``name``, ``description``,
``metadata.type``) plus a body — see :func:`get_claude_memory_dir`.

This module reads that store and upserts each memory file as one
``knowledge_facts`` entry through the existing ``FactsMixin`` write path
(``store_fact`` / ``update_fact``) — the write path declared as
``knowledge_facts``'s system of record in ``autobot_shared/store_authority.py``.
No new store, no bypass.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator

import yaml

from autobot_shared.logging_manager import get_logger
from autobot_shared.paths import project_root

logger = get_logger(__name__)

CATEGORY = "claude_code_memory"

# #16642: ssot_config.py and ssot_constants.py are both at their frozen
# python-file-size-ratchet ceilings (#14236) — a grandfathered file may not
# grow, so this configurable path lives here instead, following the same
# env-var-backed module constant pattern as chat_history/cache.py's TTL.
_MEMORY_DIR_ENV_VAR = "AUTOBOT_CLAUDE_MEMORY_DIR"


def get_claude_memory_dir() -> Path:
    """Return this checkout's Claude Code auto-memory directory.

    Override via ``AUTOBOT_CLAUDE_MEMORY_DIR``. Default is computed lazily
    from :func:`project_root` — Claude Code stores per-project memory under
    ``~/.claude/projects/<absolute-checkout-path-with-/-replaced-by-->/memory/``
    — so the default follows the checkout rather than freezing one
    developer's machine-specific path.
    """
    override = os.environ.get(_MEMORY_DIR_ENV_VAR)
    if override:
        return Path(override)
    slug = str(project_root()).replace("/", "-")
    return Path.home() / ".claude" / "projects" / slug / "memory"


_FRONTMATTER_RE = re.compile(r"\A---\n(.*?\n)---\n(.*)\Z", re.DOTALL)
_INDEX_FILENAME = "MEMORY.md"


class MemoryParseError(ValueError):
    """Raised when a memory file has no valid frontmatter block."""


class MemoryWriteError(RuntimeError):
    """Raised when the knowledge_facts write path rejects a memory file."""


@dataclass(frozen=True)
class ParsedMemory:
    """One parsed Claude Code memory file."""

    slug: str
    description: str
    memory_type: str
    body: str
    source_file: str


@dataclass
class ImportResult:
    """Outcome of one import_claude_memory() run."""

    created: int = 0
    updated: int = 0
    duplicate: int = 0
    failed: int = 0
    errors: Dict[str, str] = field(default_factory=dict)


def parse_memory_file(path: Path) -> ParsedMemory:
    """Parse one ``*.md`` memory file's YAML frontmatter + body.

    Raises MemoryParseError if the file has no ``---``-delimited frontmatter
    block, or the frontmatter is missing ``name``.
    """
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise MemoryParseError(f"{path.name}: no frontmatter block")

    front_raw, body = match.groups()
    front = yaml.safe_load(front_raw) or {}
    slug = front.get("name")
    if not slug:
        raise MemoryParseError(f"{path.name}: frontmatter missing 'name'")

    metadata = front.get("metadata") or {}
    return ParsedMemory(
        slug=str(slug),
        description=str(front.get("description", "")),
        memory_type=str(metadata.get("type", "unknown")),
        body=body.strip(),
        source_file=path.name,
    )


def iter_memory_files(memory_dir: Path) -> Iterator[Path]:
    """Yield the top-level memory files in *memory_dir*.

    Excludes the master index (``MEMORY.md``) — a navigation aid over the
    real memory files, not a memory itself. Does not recurse into
    ``topics/``, which holds per-topic indexes of the same kind.
    """
    if not memory_dir.is_dir():
        return
    for path in sorted(memory_dir.glob("*.md")):
        if path.name == _INDEX_FILENAME:
            continue
        yield path


def fact_id_for(slug: str) -> str:
    """Deterministic knowledge_facts id for a memory slug — makes re-import idempotent."""
    return f"{CATEGORY}:{slug}"


def _fact_content(memory: ParsedMemory) -> str:
    if memory.description:
        return f"{memory.description}\n\n{memory.body}"
    return memory.body


def _fact_metadata(memory: ParsedMemory) -> Dict[str, Any]:
    return {
        "category": CATEGORY,
        "memory_type": memory.memory_type,
        "source_name": memory.slug,
        "source_file": memory.source_file,
    }


async def import_memory_file(kb: Any, path: Path) -> str:
    """Upsert one memory file into knowledge_facts.

    Returns "created", "updated", or "duplicate" (near-identical content
    already tracked under a different fact — the shared KB dedup guard,
    not specific to this importer).

    Raises MemoryParseError on a malformed file, MemoryWriteError if the
    knowledge_facts write path itself rejects the write.
    """
    memory = parse_memory_file(path)
    fact_id = fact_id_for(memory.slug)
    content = _fact_content(memory)
    metadata = _fact_metadata(memory)

    if kb.get_fact(fact_id) is not None:
        result = await kb.update_fact(fact_id, content=content, metadata=metadata)
        if result.get("status") != "success":
            raise MemoryWriteError(f"{path.name}: update_fact failed: {result.get('message')}")
        return "updated"

    result = await kb.store_fact(content, metadata=metadata, fact_id=fact_id)
    status = result.get("status")
    if status == "duplicate":
        return "duplicate"
    if status != "success":
        raise MemoryWriteError(f"{path.name}: store_fact failed: {result.get('message')}")
    return "created"


async def import_claude_memory(kb: Any, memory_dir: Path) -> ImportResult:
    """Import every memory file under *memory_dir* into knowledge_facts.

    Idempotent: re-running updates existing facts (keyed by the memory
    file's frontmatter ``name`` via :func:`fact_id_for`) instead of
    duplicating them.
    """
    outcome = ImportResult()
    for path in iter_memory_files(memory_dir):
        try:
            action = await import_memory_file(kb, path)
        except (MemoryParseError, MemoryWriteError) as exc:
            outcome.failed += 1
            outcome.errors[path.name] = str(exc)
            logger.warning("Skipped Claude Code memory file: %s", exc)
            continue

        if action == "created":
            outcome.created += 1
        elif action == "updated":
            outcome.updated += 1
        else:
            outcome.duplicate += 1

    logger.info(
        "Claude Code memory import: %d created, %d updated, %d duplicate, %d failed",
        outcome.created,
        outcome.updated,
        outcome.duplicate,
        outcome.failed,
    )
    return outcome
