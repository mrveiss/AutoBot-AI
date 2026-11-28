# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one man-page ingestion path (#22272).

Man pages used to reach the knowledge base through four writers that disagreed on
metadata and on which host a fact belongs to. This is the canonical one: every fact it
writes carries the host that owns the page (``utils.system_context.get_machine_id``) and a
``unique_key`` from ``generate_unique_key``, so the same command on two hosts is two facts
and a re-run on one host overwrites its own.

Callers: ``index_all_man_pages()`` below (the CLI script and the Celery refresh), and the
``/populate_man_pages`` endpoint, which passes its curated command list.
"""

import asyncio
import os
from typing import NamedTuple, Optional, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.subprocess_reap import kill_and_reap
from knowledge.ingestion_visibility import INGESTED_DOCUMENT_VISIBILITY
from utils.system_context import generate_unique_key, get_compatible_os_list, get_system_context

logger = get_logger(__name__)

#: Commands indexed per progress report; man page extraction is subprocess-bound, not memory-bound.
MAN_PAGE_BATCH_SIZE = 50

#: Seconds each ``man`` subprocess may run: the full listing, one description, one page.
MAN_LIST_TIMEOUT_SECONDS = 30
MAN_DESCRIPTION_TIMEOUT_SECONDS = 5
MAN_CONTENT_TIMEOUT_SECONDS = 10

#: Seconds ``man -w`` may run to resolve which section a bare command name belongs to.
MAN_RESOLVE_TIMEOUT_SECONDS = 5


async def _communicate(process, timeout: float) -> Tuple[bytes, bytes]:
    """``process.communicate()`` bounded by ``timeout``; the child is killed and reaped on every abnormal exit.

    A timeout and an external cancellation both leave the child running otherwise (a child blocked
    on a full stdout pipe never exits). The exception is re-raised after the cleanup.
    """
    try:
        return await asyncio.wait_for(process.communicate(), timeout=timeout)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        await kill_and_reap(process, bounded=True)
        raise


class BatchOutcome(NamedTuple):
    """What one batch did: pages stored, and pages whose storage failed (not the same as no manual)."""

    indexed: int = 0
    storage_failed: int = 0


async def resolve_man_section(command: str) -> Optional[str]:
    """The section ``man`` resolves ``command`` to (``man -w`` path ``.../man8/x.8.gz`` gives ``"8"``), or None."""
    process = await asyncio.create_subprocess_exec(
        "man",
        "-w",
        "--",
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _ = await _communicate(process, MAN_RESOLVE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        return None
    if process.returncode != 0:
        return None
    directory = os.path.basename(os.path.dirname(stdout.decode().strip().split("\n")[0]))
    return directory[3:] or None if directory.startswith("man") else None


async def get_all_available_commands():
    """Get ALL commands with man pages on this system"""
    logger.info("Scanning for all available commands with man pages...")

    try:
        # Use man -k . to list ALL man pages (Issue #479: Use async subprocess)
        process = await asyncio.create_subprocess_exec(
            "man",
            "-k",
            ".",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await _communicate(process, MAN_LIST_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            logger.error("Timeout listing man pages")
            return []

        if process.returncode != 0:
            logger.error("Failed to list man pages")
            return []

        # Use decoded stdout
        output_text = stdout.decode()
        result_stdout = output_text

        commands = []
        for line in result_stdout.split("\n"):
            if not line.strip():
                continue

            # Parse format: command (section) - description
            parts = line.split("(")
            if len(parts) < 2:
                continue

            command_name = parts[0].strip()
            section_part = parts[1].split(")")[0]

            # Only index sections 1, 5, 8 (user commands, config files, admin commands)
            if section_part in ["1", "5", "8"]:
                commands.append((command_name, section_part))

        # Remove duplicates
        commands = list(set(commands))
        logger.info("Found %s commands to index", len(commands))

        return commands

    except Exception as e:
        logger.error("Error scanning commands: %s", e)
        return []


async def _get_man_page_description(command: str) -> str:
    """
    Get command description from man -k.

    Helper for index_command_batch (#825).

    Args:
        command: Command name

    Returns:
        Description string or empty string
    """
    desc_process = await asyncio.create_subprocess_exec(
        "man",
        "-k",
        "--",
        f"^{command}$",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        desc_stdout, _ = await _communicate(desc_process, MAN_DESCRIPTION_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        return ""

    if desc_process.returncode == 0:
        for line in desc_stdout.decode().split("\n"):
            if command in line and "-" in line:
                return line.split("-", 1)[1].strip()

    return ""


def build_man_page_metadata(command: str, section: str, system_ctx: dict, unique_key: str) -> dict:
    """
    Build metadata dict for man page fact.

    Helper for index_command_batch (#825).

    Args:
        command: Command name
        section: Man section
        system_ctx: System context dict
        unique_key: Unique key for deduplication

    Returns:
        Metadata dictionary
    """
    return {
        "type": "man_page",
        "command": command,
        "section": section,
        "title": f"man {command}({section})",
        "machine_id": system_ctx["machine_id"],
        "machine_ip": system_ctx["machine_ip"],
        "os_name": system_ctx["os_name"],
        "os_version": system_ctx["os_version"],
        "os_type": system_ctx["os_type"],
        "architecture": system_ctx["architecture"],
        "kernel_version": system_ctx["kernel_version"],
        "applies_to_machines": [system_ctx["machine_id"]],
        "applies_to_os": get_compatible_os_list(system_ctx["os_name"]),
        "unique_key": unique_key,
        # The category + machine_id pair is what marks a per-host man page an ingested document (#16693).
        "category": "system/manpages",
        "source": "comprehensive_man_pages",
        "visibility": INGESTED_DOCUMENT_VISIBILITY,
    }


async def _get_man_content(command: str, section: str) -> str:
    """
    Get man page content for a command.

    Helper for index_command_batch (#825).

    Args:
        command: Command name
        section: Man section

    Returns:
        Man page content string or empty string on error
    """
    env = os.environ.copy()
    env["MANWIDTH"] = "80"

    process = await asyncio.create_subprocess_exec(
        "man",
        "--",
        section,
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    try:
        stdout, stderr = await _communicate(process, MAN_CONTENT_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        return ""

    if process.returncode != 0:
        return ""

    return stdout.decode().strip()


def _format_man_content(command: str, section: str, description: str, man_content: str, system_ctx: dict) -> str:
    """
    Format man page content with system context.

    Helper for index_command_batch (#825).

    Args:
        command: Command name
        section: Man section
        description: Command description
        man_content: Raw man page content
        system_ctx: System context dict

    Returns:
        Formatted content string
    """
    section_name = (
        "User Commands" if section == "1" else "Configuration Files" if section == "5" else "System Administration"
    )

    return f"""# {command}({section}) - {description}

**Machine:** {system_ctx['machine_id']} ({system_ctx['machine_ip']})
**OS:** {system_ctx['os_name']} {system_ctx['os_version']} ({system_ctx['os_type']})
**Architecture:** {system_ctx['architecture']}
**Section:** {section} ({section_name})

{man_content[:5000]}

---
*Full manual: `man {section} {command}`*
"""


async def _store_page(kb_v2, command: str, section: str, system_ctx: dict) -> Optional[bool]:
    """Store one page. None: no manual to store; True: stored; False: storage failed."""
    man_content = await _get_man_content(command, section)
    if not man_content:
        return None
    description = await _get_man_page_description(command)
    content = _format_man_content(command, section, description, man_content, system_ctx)
    unique_key = generate_unique_key(system_ctx["machine_id"], system_ctx["os_name"], command, section)
    metadata = build_man_page_metadata(command, section, system_ctx, unique_key)
    try:
        result = await kb_v2.store_fact(content=content, metadata=metadata)
    except Exception as e:
        logger.warning("Storage failed for %s(%s): %s", command, section, e)
        return False
    return result.get("status") == "success"


async def index_command_batch(kb_v2, commands_batch, system_ctx=None) -> BatchOutcome:
    """Index a batch of ``(command, section)`` pairs with OS/machine context.

    A ``None`` section means "whichever section ``man`` resolves for the command"; the resolved
    section is what the fact's key, ``section`` and ``title`` record.
    """
    indexed = storage_failed = 0
    if system_ctx is None:
        system_ctx = get_system_context()

    for command, section in commands_batch:
        try:
            resolved = section or await resolve_man_section(command)
            stored = await _store_page(kb_v2, command, resolved, system_ctx) if resolved else None
        except Exception as e:
            logger.warning("Error indexing %s: %s", command, e)
            continue
        if stored is None:
            continue
        indexed += stored
        storage_failed += not stored

    return BatchOutcome(indexed, storage_failed)


async def index_commands_in_batches(kb_v2, all_commands, system_ctx: dict) -> BatchOutcome:
    """
    Index commands in batches and return how many pages were stored and how many failed to store.

    Raises ``ManPageIndexingError`` when pages had a manual but storage rejected every one of them,
    so a dead knowledge base is a failed run, not a successful run of zero. Partial storage failure
    keeps the successful writes and their count and is logged.

    Args:
        kb_v2: KnowledgeBase instance
        all_commands: List of (command, section-or-None) tuples
        system_ctx: System context dict
    """
    batch_size = MAN_PAGE_BATCH_SIZE
    total_indexed = total_failed = 0

    for i in range(0, len(all_commands), batch_size):
        batch = all_commands[i : i + batch_size]
        outcome = await index_command_batch(kb_v2, batch, system_ctx)
        total_indexed += outcome.indexed
        total_failed += outcome.storage_failed

        progress = min(i + batch_size, len(all_commands))
        logger.info("Progress: %s/%s (%s indexed)", progress, len(all_commands), total_indexed)

    if total_failed:
        logger.warning("Man page storage failed for %d pages (%d stored)", total_failed, total_indexed)
        if not total_indexed:
            raise ManPageIndexingError(f"Knowledge base rejected all {total_failed} man pages")
    return BatchOutcome(total_indexed, total_failed)


class ManPageIndexingError(RuntimeError):
    """The full man-page index could not run: no usable knowledge base, or nothing to index."""


async def _ready_knowledge_base():
    """The initialised knowledge base, or ``ManPageIndexingError``."""
    from knowledge_factory import get_knowledge_base_async  # noqa: PLC0415

    kb = await get_knowledge_base_async()
    if kb is None:
        raise ManPageIndexingError("Knowledge base unavailable: initialization failed or retry cooldown active")
    if not kb.initialized:
        raise ManPageIndexingError("Knowledge Base V2 initialization failed")
    return kb


def _log_system_context(system_ctx: dict) -> None:
    """Log the host the pages are indexed for."""
    logger.info("Machine: %s (%s)", system_ctx["machine_id"], system_ctx["machine_ip"])
    logger.info("OS: %s %s (%s)", system_ctx["os_name"], system_ctx["os_version"], system_ctx["architecture"])
    logger.info("Compatible with: %s", ", ".join(get_compatible_os_list(system_ctx["os_name"])))


async def index_all_man_pages() -> dict:
    """Index every available man page into the knowledge base and return the counts (#22272).

    The one entry for the CLI script and the Celery refresh: callers use this return value,
    never the output of a subprocess. Keys: ``commands_scanned``, ``commands_indexed``,
    ``storage_failed``, ``total_facts``, ``total_vectors``.
    """
    kb = await _ready_knowledge_base()
    try:
        commands = await get_all_available_commands()
        if not commands:
            raise ManPageIndexingError("No commands found")
        system_ctx = get_system_context()
        _log_system_context(system_ctx)
        outcome = await index_commands_in_batches(kb, commands, system_ctx)
        stats = await kb.get_stats()
        return {
            "commands_scanned": len(commands),
            "commands_indexed": outcome.indexed,
            "storage_failed": outcome.storage_failed,
            "total_facts": stats.get("total_facts", 0),
            "total_vectors": stats.get("total_vectors", 0),
        }
    finally:
        # Facts stored before a failure still count; this process's loop would cancel a waiting recompute (#19726).
        await kb._get_keyword_searcher().flush_refresh()
