# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Population API - Endpoints for populating knowledge base with system data.

This module contains all population-related API endpoints for the knowledge base.
Extracted from knowledge.py for better maintainability (Issue #185, #209).

Endpoints:
- POST /populate_system_commands - Add common system commands
- POST /populate_man_pages - Add manual pages (background)
- POST /refresh_system_knowledge - Refresh all system knowledge (Celery)
- GET /job_status/{task_id} - Poll background job status
- POST /populate_autobot_docs - Add AutoBot documentation

Related Issues: #185 (Split), #209 (Knowledge split)
"""

import asyncio
import logging
import re
from pathlib import Path as PathLib

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Request

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from backend.constants.threshold_constants import TimingConstants
from backend.knowledge_factory import get_or_create_knowledge_base
from backend.utils.template_loader import knowledge_data_exists, load_knowledge_data

logger = logging.getLogger(__name__)

# Issue #380: Pre-compiled regex for ANSI escape sequence removal
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")

# Create router for population endpoints
router = APIRouter(tags=["knowledge-population"])


# ===== HELPER FUNCTIONS =====


def _format_command_content(cmd_info: dict) -> str:
    """Format system command info into structured content string."""
    examples_text = "\n".join(f"  {ex}" for ex in cmd_info["examples"])
    options_text = "\n".join(f"  {opt}" for opt in cmd_info["options"])
    return f"""Command: {cmd_info['command']}

Description: {cmd_info['description']}

Usage: {cmd_info['usage']}

Examples:
{examples_text}

Common Options:
{options_text}

Category: System Command
Type: Command Reference
"""


def _get_command_metadata(cmd_info: dict) -> dict:
    """Create metadata dict for system command storage."""
    return {
        "title": f"{cmd_info['command']} command",
        "source": "system_commands_population",
        "category": "commands",
        "command": cmd_info["command"],
        "type": "system_command",
    }


async def _store_system_command(kb_to_use, cmd_info: dict) -> bool:
    """Store a single system command in knowledge base, returns success status."""
    content = _format_command_content(cmd_info)
    metadata = _get_command_metadata(cmd_info)

    try:
        if hasattr(kb_to_use, "store_fact"):
            result = await kb_to_use.store_fact(content=content, metadata=metadata)
        else:
            result = await kb_to_use.store_fact(text=content, metadata=metadata)

        if result and result.get("fact_id"):
            logger.info("Added command: %s", cmd_info["command"])
            return True

        logger.warning("Failed to add command: %s", cmd_info["command"])
        return False

    except Exception as e:
        logger.error("Error adding command %s: %s", cmd_info["command"], e)
        return False


def _get_system_commands_data() -> list:
    """
    Return common system commands with descriptions and examples.

    Issue #281: Extracted from populate_system_commands to reduce function
    length and separate data from logic.
    Issue #515: Data externalized to data/knowledge/system_commands.yaml

    Returns:
        List of command info dictionaries with keys:
        command, description, usage, examples, options
    """
    # Issue #515: Try loading from YAML first
    if knowledge_data_exists("system_commands"):
        try:
            return load_knowledge_data("system_commands", key="commands")
        except Exception as e:
            logger.warning("Failed to load system commands from YAML: %s", e)

    # Fallback to inline data for backwards compatibility
    return _get_fallback_system_commands()


def _get_network_commands() -> list:
    """
    Return network-related system commands (curl, ssh).

    Issue #665: Extracted from _get_fallback_system_commands to reduce function length.
    """
    return [
        {
            "command": "curl",
            "description": "Command line tool for transferring data with URLs",
            "usage": "curl [options] <url>",
            "examples": [
                "curl https://api.example.com/data",
                "curl -X POST -d 'data' https://api.example.com",
                "curl -H 'Authorization: Bearer token' https://api.example.com",
                "curl -o output.html https://example.com",
            ],
            "options": [
                "-X: HTTP method (GET, POST, PUT, DELETE)",
                "-H: Add header",
                "-d: Data to send",
                "-o: Output to file",
                "-v: Verbose output",
                "--json: Send JSON data",
            ],
        },
        {
            "command": "ssh",
            "description": "Secure Shell for remote login and command execution",
            "usage": "ssh [options] [user@]hostname [command]",
            "examples": [
                "ssh user@remote-server",
                "ssh -i ~/.ssh/key user@server",
                "ssh -p 2222 user@server",
                "ssh user@server 'ls -la'",
            ],
            "options": [
                "-i: Identity file (private key)",
                "-p: Port number",
                "-v: Verbose output",
                "-X: Enable X11 forwarding",
                "-L: Local port forwarding",
            ],
        },
    ]


def _get_text_processing_commands() -> list:
    """
    Return text processing commands (grep).

    Issue #665: Extracted from _get_fallback_system_commands to reduce function length.
    """
    return [
        {
            "command": "grep",
            "description": "Search text patterns in files",
            "usage": "grep [options] pattern [file...]",
            "examples": [
                "grep 'error' /var/log/syslog",
                "grep -r 'function' /path/to/code/",
                "grep -i 'warning' *.log",
                "ps aux | grep python",
            ],
            "options": [
                "-r: Recursive search",
                "-i: Case insensitive",
                "-n: Line numbers",
                "-v: Invert match",
                "-l: Files with matches only",
            ],
        },
    ]


def _get_container_commands() -> list:
    """
    Return container-related commands (docker).

    Issue #665: Extracted from _get_fallback_system_commands to reduce function length.
    """
    return [
        {
            "command": "docker",
            "description": (
                "Container platform for building, running and managing applications"
            ),
            "usage": "docker [options] COMMAND",
            "examples": [
                "docker run -it ubuntu bash",
                "docker build -t myapp .",
                "docker ps -a",
                "docker exec -it container_name bash",
            ],
            "options": [
                "run: Create and run container",
                "build: Build image from Dockerfile",
                "ps: List containers",
                "exec: Execute command in container",
                "logs: View container logs",
            ],
        },
    ]


def _get_version_control_commands() -> list:
    """
    Return version control commands (git).

    Issue #665: Extracted from _get_fallback_system_commands to reduce function length.
    """
    return [
        {
            "command": "git",
            "description": "Distributed version control system",
            "usage": "git [options] COMMAND [args]",
            "examples": [
                "git clone https://github.com/user/repo.git",
                "git add .",
                "git commit -m 'message'",
                "git push origin main",
            ],
            "options": [
                "clone: Clone repository",
                "add: Stage changes",
                "commit: Create commit",
                "push: Upload changes",
                "pull: Download changes",
            ],
        },
    ]


def _get_file_commands() -> list:
    """
    Return file operation commands (find, tar, chmod).

    Issue #665: Extracted from _get_fallback_system_commands to reduce function length.
    """
    return [
        {
            "command": "find",
            "description": "Search for files and directories",
            "usage": "find [path] [expression]",
            "examples": [
                "find /path -name '*.py'",
                "find . -type f -mtime -7",
                "find /var -size +100M",
                "find . -perm 755",
            ],
            "options": [
                "-name: File name pattern",
                "-type: File type (f=file, d=directory)",
                "-size: File size",
                "-mtime: Modification time",
                "-exec: Execute command on results",
            ],
        },
        {
            "command": "tar",
            "description": "Archive files and directories",
            "usage": "tar [options] archive-file files...",
            "examples": [
                "tar -czf archive.tar.gz folder/",
                "tar -xzf archive.tar.gz",
                "tar -tzf archive.tar.gz",
                "tar -xzf archive.tar.gz -C /destination/",
            ],
            "options": [
                "-c: Create archive",
                "-x: Extract archive",
                "-z: Gzip compression",
                "-f: Archive filename",
                "-t: List contents",
            ],
        },
        {
            "command": "chmod",
            "description": "Change file permissions",
            "usage": "chmod [options] mode file...",
            "examples": [
                "chmod 755 script.sh",
                "chmod +x program",
                "chmod -R 644 /path/to/files/",
                "chmod u+w,g-w file.txt",
            ],
            "options": [
                "755: rwxr-xr-x (executable)",
                "644: rw-r--r-- (readable)",
                "+x: Add execute permission",
                "-R: Recursive",
                "u/g/o: user/group/others",
            ],
        },
    ]


def _get_system_admin_commands() -> list:
    """
    Return system administration commands (systemctl, ps).

    Issue #665: Extracted from _get_fallback_system_commands to reduce function length.
    """
    return [
        {
            "command": "systemctl",
            "description": "Control systemd services",
            "usage": "systemctl [options] COMMAND [service]",
            "examples": [
                "systemctl status nginx",
                "systemctl start redis-server",
                "systemctl enable docker",
                "systemctl restart apache2",
            ],
            "options": [
                "start: Start service",
                "stop: Stop service",
                "restart: Restart service",
                "status: Check status",
                "enable: Auto-start on boot",
            ],
        },
        {
            "command": "ps",
            "description": "Display running processes",
            "usage": "ps [options]",
            "examples": [
                "ps aux",
                "ps -ef",
                "ps aux | grep python",
                "ps -u username",
            ],
            "options": [
                "aux: All processes with details",
                "-ef: Full format listing",
                "-u: Processes by user",
                "-C: Processes by command",
            ],
        },
    ]


def _get_fallback_system_commands() -> list:
    """
    Fallback system commands data if YAML file is not available.

    Issue #515: Preserved for backwards compatibility during data migration.
    Issue #665: Refactored to use helper functions per command category
    to reduce function length from 190 lines to under 50 lines.
    """
    commands = []
    commands.extend(_get_network_commands())
    commands.extend(_get_text_processing_commands())
    commands.extend(_get_container_commands())
    commands.extend(_get_version_control_commands())
    commands.extend(_get_file_commands())
    commands.extend(_get_system_admin_commands())
    return commands


async def _store_autobot_config_info(kb_to_use) -> bool:
    """
    Generate and store AutoBot system configuration in knowledge base.

    Issue #281: Extracted helper for config info generation and storage.
    Issue #398: Refactored to use _store_system_config (DRY principle).

    Args:
        kb_to_use: Knowledge base instance

    Returns:
        True if stored successfully, False otherwise
    """
    # Delegate to the consolidated implementation (Issue #398)
    return await _store_system_config(kb_to_use)


# ===== POPULATION ENDPOINTS =====


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="populate_system_commands",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/populate_system_commands")
async def populate_system_commands(request: dict, req: Request):
    """
    Populate knowledge base with common system commands and usage examples.

    Issue #281: Data definitions extracted to _get_system_commands_data() helper
    to reduce function length from 221 to ~35 lines.
    """
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        return {
            "status": "error",
            "message": "Knowledge base not initialized - please check logs for errors",
            "items_added": 0,
        }

    logger.info("Starting system commands population...")

    # Issue #281: Use extracted data function instead of inline definition
    system_commands = _get_system_commands_data()

    items_added = 0

    # Process commands in batches to avoid timeouts
    batch_size = 5
    for i in range(0, len(system_commands), batch_size):
        batch = system_commands[i : i + batch_size]
        for cmd_info in batch:
            if await _store_system_command(kb_to_use, cmd_info):
                items_added += 1
        # Small delay between batches to prevent overload
        await asyncio.sleep(TimingConstants.MICRO_DELAY)

    logger.info("System commands population completed. Added %s commands.", items_added)

    return {
        "status": "success",
        "message": f"Successfully populated {items_added} system commands",
        "items_added": items_added,
        "total_commands": len(system_commands),
    }


def _get_man_page_metadata(command: str) -> dict:
    """Create metadata dict for man page storage."""
    return {
        "title": f"man {command}",
        "source": "manual_pages_population",
        "category": "manpages",
        "command": command,
        "type": "manual_page",
    }


def _format_man_page_content(command: str, man_content: str) -> str:
    """Format man page content for storage."""
    return f"""Manual Page: {command}

{man_content}

Source: System Manual Pages
Category: Manual Page
Command: {command}
"""


async def _fetch_man_page(command: str) -> str | None:
    """Fetch man page content for a command, returns None on failure."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "man",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            logger.warning("Timeout getting man page for: %s", command)
            return None

        if proc.returncode != 0 or not stdout.strip():
            logger.warning("No man page found for command: %s", command)
            return None

        man_content = stdout.decode("utf-8").strip()
        # Remove ANSI escape sequences
        return _ANSI_ESCAPE_RE.sub("", man_content)

    except Exception as e:
        logger.error("Error fetching man page for %s: %s", command, e)
        return None


async def _store_man_page(kb_to_use, command: str, content: str) -> bool:
    """Store a man page in knowledge base, returns success status."""
    metadata = _get_man_page_metadata(command)
    try:
        if hasattr(kb_to_use, "store_fact"):
            store_result = await kb_to_use.store_fact(
                content=content, metadata=metadata
            )
        else:
            store_result = await kb_to_use.store_fact(text=content, metadata=metadata)

        if store_result and store_result.get("fact_id"):
            logger.info("Added man page: %s", command)
            return True
        logger.warning("Failed to store man page: %s", command)
        return False
    except Exception as e:
        logger.error("Error storing man page for %s: %s", command, e)
        return False


async def _process_single_man_page(kb_to_use, command: str) -> bool:
    """Process a single man page: fetch and store."""
    man_content = await _fetch_man_page(command)
    if not man_content:
        return False
    content = _format_man_page_content(command, man_content)
    return await _store_man_page(kb_to_use, command, content)


# Common commands for man pages
COMMON_MAN_PAGE_COMMANDS = [
    "ls",
    "cd",
    "cp",
    "mv",
    "rm",
    "mkdir",
    "rmdir",
    "chmod",
    "chown",
    "find",
    "grep",
    "sed",
    "awk",
    "sort",
    "uniq",
    "head",
    "tail",
    "cat",
    "less",
    "more",
    "ps",
    "top",
    "kill",
    "jobs",
    "nohup",
    "crontab",
    "systemctl",
    "service",
    "curl",
    "wget",
    "ssh",
    "scp",
    "rsync",
    "tar",
    "zip",
    "unzip",
    "gzip",
    "gunzip",
    "git",
    "docker",
    "npm",
    "pip",
    "python",
    "node",
    "java",
    "gcc",
    "make",
]


async def _populate_man_pages_background(kb_to_use):
    """Background task to populate man pages"""
    try:
        logger.info("Starting manual pages population in background...")
        items_added = 0

        batch_size = 5
        for i in range(0, len(COMMON_MAN_PAGE_COMMANDS), batch_size):
            batch = COMMON_MAN_PAGE_COMMANDS[i : i + batch_size]

            for command in batch:
                if await _process_single_man_page(kb_to_use, command):
                    items_added += 1

            # Batch processing delay
            await asyncio.sleep(TimingConstants.MICRO_DELAY)

        logger.info(
            "Manual pages population completed. Added %s man pages.", items_added
        )
        return items_added

    except Exception as e:
        logger.error("Error populating manual pages in background: %s", str(e))
        return 0


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="populate_man_pages",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/populate_man_pages")
async def populate_man_pages(
    request: dict, req: Request, background_tasks: BackgroundTasks
):
    """Populate knowledge base with common manual pages (runs in background)"""
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        return {
            "status": "error",
            "message": "Knowledge base not initialized - please check logs for errors",
            "items_added": 0,
        }

    # Start background task
    background_tasks.add_task(_populate_man_pages_background, kb_to_use)

    return {
        "status": "success",
        "message": "Man pages population started in background",
        "items_added": 0,  # Will be updated as background task runs
        "background": True,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="refresh_system_knowledge",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/refresh_system_knowledge")
async def refresh_system_knowledge(request: dict, req: Request):
    """
    Refresh ALL system knowledge (man pages + AutoBot docs) - BACKGROUND JOB

    This endpoint starts a background Celery task that can take up to 10 minutes.
    Returns immediately with a task_id that can be used to poll job status.

    Use this after system updates, package installations, or documentation changes.

    Returns:
        {
            "task_id": "uuid-string",
            "status": "PENDING",
            "message": "Knowledge refresh started in background",
            "poll_url": "/api/knowledge_base/job_status/{task_id}"
        }
    """
    logger.info("Starting comprehensive system knowledge refresh (background)...")

    # Import here to avoid circular dependency
    from backend.tasks.knowledge_tasks import refresh_system_knowledge as refresh_task

    # Start background Celery task
    task = refresh_task.apply_async()

    logger.info("Knowledge refresh task started: %s", task.id)

    return {
        "task_id": task.id,
        "status": "PENDING",
        "message": "Knowledge refresh started in background",
        "poll_url": f"/api/knowledge_base/job_status/{task.id}",
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_job_status",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/job_status/{task_id}")
async def get_job_status(task_id: str, req: Request):
    """
    Get status of a background knowledge base job.

    Polls Celery task status for long-running operations like:
    - System knowledge refresh
    - Knowledge base reindexing
    - Bulk vectorization

    Args:
        task_id: Celery task ID returned from job start endpoint

    Returns:
        {
            "task_id": "uuid",
            "status": "PENDING|PROGRESS|SUCCESS|FAILURE",
            "result": {...},  # Only present when SUCCESS
            "error": "...",   # Only present when FAILURE
            "meta": {...}     # Progress info when PROGRESS
        }
    """
    from celery.result import AsyncResult

    # Get task status from Celery
    task_result = AsyncResult(task_id)

    response = {
        "task_id": task_id,
        "status": task_result.state,
    }

    if task_result.state == "PENDING":
        response["message"] = "Task is queued and waiting to start"
    elif task_result.state == "PROGRESS":
        response["meta"] = task_result.info
        response["message"] = task_result.info.get("status", "In progress...")
    elif task_result.state == "SUCCESS":
        response["result"] = task_result.result
        response["message"] = task_result.result.get(
            "message", "Task completed successfully"
        )
    elif task_result.state == "FAILURE":
        response["error"] = str(task_result.info)
        response["message"] = f"Task failed: {str(task_result.info)}"
    else:
        response["message"] = f"Task status: {task_result.state}"

    return response


def extract_category_from_path(doc_file: str) -> str:
    """Extract category from document file path

    Examples:
        docs/api/file.md -> "api"
        docs/architecture/file.md -> "architecture"
        CLAUDE.md -> "root"
    """
    path_parts = str(doc_file).split("/")
    if len(path_parts) > 1 and path_parts[0] == "docs":
        # docs/api/file.md -> "api"
        return path_parts[1] if len(path_parts) > 2 else "docs"
    # Root files like CLAUDE.md
    return "root"


def _format_doc_content(doc_file: str, file_path, content: str, category: str) -> str:
    """Format documentation content for storage."""
    return f"""AutoBot Documentation: {doc_file}

File Path: {file_path}

Content:
{content}

Source: AutoBot Documentation
Category: {category}
Type: Documentation
"""


def _get_doc_metadata(doc_file: str, file_path, category: str) -> dict:
    """Create metadata dict for documentation storage."""
    return {
        "title": f"AutoBot: {doc_file}",
        "source": "autobot_docs_population",
        "category": category,
        "filename": doc_file,
        "type": f"{category}_documentation",
        "file_path": str(file_path),
    }


async def _store_doc_file(
    kb_to_use, doc_file: str, file_path, content: str, category: str
) -> dict | None:
    """Store a documentation file in knowledge base, returns result or None."""
    structured_content = _format_doc_content(doc_file, file_path, content, category)
    metadata = _get_doc_metadata(doc_file, file_path, category)

    try:
        if hasattr(kb_to_use, "store_fact"):
            return await kb_to_use.store_fact(
                content=structured_content, metadata=metadata
            )
        return await kb_to_use.store_fact(text=structured_content, metadata=metadata)
    except Exception as e:
        logger.error("Error storing doc %s: %s", doc_file, e)
        return None


async def _read_doc_file_content(file_path) -> str | None:
    """
    Read documentation file content asynchronously.

    Issue #398: Extracted from _process_doc_file to reduce method length.

    Returns:
        File content string, or None if file doesn't exist or is empty.
    """
    file_exists = await asyncio.to_thread(file_path.exists)
    is_file = await asyncio.to_thread(file_path.is_file) if file_exists else False
    if not file_exists or not is_file:
        return None

    try:
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()
        return content if content.strip() else None
    except OSError:
        return None


async def _process_doc_file(
    kb_to_use, tracker, autobot_base_path, doc_file: str
) -> tuple[int, int, int]:
    """
    Process a single documentation file.

    Issue #398: Refactored to extract file reading logic.

    Returns:
        Tuple of (added, skipped, failed) counts
    """
    file_path = autobot_base_path / doc_file
    content = await _read_doc_file_content(file_path)

    if content is None:
        logger.warning("File not found or empty: %s", doc_file)
        return (0, 1, 0)

    category = extract_category_from_path(doc_file)
    result = await _store_doc_file(kb_to_use, doc_file, file_path, content, category)

    if result and result.get("fact_id"):
        tracker.mark_imported(
            file_path=str(file_path),
            category=category,
            facts_count=1,
            metadata={
                "fact_id": result.get("fact_id"),
                "title": f"AutoBot: {doc_file}",
            },
        )
        logger.info("Added AutoBot doc: %s", doc_file)
        return (1, 0, 0)

    tracker.mark_failed(str(file_path), "Failed to store in knowledge base")
    return (0, 0, 1)


def _build_system_config_info() -> str:
    """Build system configuration info string."""
    from constants.network_constants import NetworkConstants
    from constants.path_constants import PATH

    return f"""AutoBot System Configuration

Network Layout:
- Main Machine (WSL): {NetworkConstants.MAIN_MACHINE_IP} - Backend API
  (port {NetworkConstants.BACKEND_PORT}) + NPU Worker (port 8082) +
  Desktop/Terminal VNC (port 6080)
- VM1 Frontend: {NetworkConstants.FRONTEND_VM_IP}:5173 - Web interface
  (SINGLE FRONTEND SERVER)
- VM2 NPU Worker: {NetworkConstants.NPU_WORKER_VM_IP}:8081 - Secondary NPU worker (Linux)
- VM3 Redis: {NetworkConstants.REDIS_VM_IP}:{NetworkConstants.REDIS_PORT} - Data layer
- VM4 AI Stack: {NetworkConstants.AI_STACK_VM_IP}:{NetworkConstants.AI_STACK_PORT} - AI processing
- VM5 Browser: {NetworkConstants.BROWSER_VM_IP}:{NetworkConstants.BROWSER_SERVICE_PORT} -
  Web automation (Playwright)

Key Commands:
- Setup: bash setup.sh [--full|--minimal|--distributed]
- Run: SLM GUI (https://172.16.168.19/orchestration) or scripts/start-services.sh

Critical Rules:
- NEVER edit code directly on remote VMs (VM1-VM5)
- ALL code edits MUST be made locally in {PATH.PROJECT_ROOT}/
- Use ./sync-frontend.sh or sync scripts to deploy changes
- Frontend ONLY runs on VM1 ({NetworkConstants.FRONTEND_VM_IP}:5173)
- NO temporary fixes or workarounds allowed

Source: AutoBot System Configuration
Category: AutoBot
Type: System Configuration
"""


async def _store_system_config(kb_to_use) -> bool:
    """Store AutoBot system configuration in knowledge base."""
    try:
        config_info = _build_system_config_info()
        metadata = {
            "title": "AutoBot System Configuration",
            "source": "autobot_docs_population",
            "category": "configuration",
            "type": "system_configuration",
        }

        if hasattr(kb_to_use, "store_fact"):
            result = await kb_to_use.store_fact(content=config_info, metadata=metadata)
        else:
            result = await kb_to_use.store_fact(text=config_info, metadata=metadata)

        if result and result.get("fact_id"):
            logger.info("Added AutoBot system configuration")
            return True
        return False
    except Exception as e:
        logger.error("Error adding AutoBot configuration: %s", e)
        return False


async def _scan_doc_files(
    autobot_base_path: PathLib, tracker, force_reindex: bool
) -> tuple[list[str], int]:
    """
    Scan for documentation files that need processing.

    Issue #398: Extracted from populate_autobot_docs to reduce method length.

    Args:
        autobot_base_path: Base path of the AutoBot project.
        tracker: Import tracker instance.
        force_reindex: Whether to force reindex all files.

    Returns:
        Tuple of (doc_files list, items_skipped count).
    """
    doc_files = []
    items_skipped = 0

    docs_path = autobot_base_path / "docs"
    if not await asyncio.to_thread(docs_path.exists):
        return doc_files, items_skipped

    md_files = await asyncio.to_thread(lambda: list(docs_path.rglob("*.md")))
    for md_file in md_files:
        rel_path = md_file.relative_to(autobot_base_path)
        if not force_reindex and not tracker.needs_reimport(str(md_file)):
            logger.info("Skipping unchanged file: %s", rel_path)
            items_skipped += 1
            continue
        doc_files.append(str(rel_path))

    return doc_files, items_skipped


async def _process_all_doc_files(
    kb_to_use, tracker, autobot_base_path: PathLib, doc_files: list[str]
) -> tuple[int, int, int]:
    """
    Process all documentation files.

    Issue #398: Extracted from populate_autobot_docs to reduce method length.

    Args:
        kb_to_use: Knowledge base instance.
        tracker: Import tracker instance.
        autobot_base_path: Base path of the AutoBot project.
        doc_files: List of doc file paths to process.

    Returns:
        Tuple of (items_added, items_skipped, items_failed).
    """
    items_added = 0
    items_skipped = 0
    items_failed = 0

    for doc_file in doc_files:
        try:
            added, skipped, failed = await _process_doc_file(
                kb_to_use, tracker, autobot_base_path, doc_file
            )
            items_added += added
            items_skipped += skipped
            items_failed += failed
        except Exception as e:
            items_failed += 1
            tracker.mark_failed(str(autobot_base_path / doc_file), str(e))
            logger.error("Error processing AutoBot doc %s: %s", doc_file, e)

        await asyncio.sleep(TimingConstants.MICRO_DELAY)

    return items_added, items_skipped, items_failed


def _build_population_response(
    items_added: int,
    items_skipped: int,
    items_failed: int,
    doc_count: int,
    force_reindex: bool,
) -> dict:
    """Build response dict for populate_autobot_docs. Issue #398: Extracted helper."""
    mode = "Force reindex" if force_reindex else "Incremental update"
    return {
        "status": "success",
        "message": f"{mode}: Successfully imported {items_added} AutoBot documents "
        f"({items_skipped} skipped, {items_failed} failed)",
        "items_added": items_added,
        "items_skipped": items_skipped,
        "items_failed": items_failed,
        "total_files": doc_count + 1,
        "force_reindex": force_reindex,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="populate_autobot_docs",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/populate_autobot_docs")
async def populate_autobot_docs(request: dict, req: Request):
    """
    Populate knowledge base with AutoBot-specific documentation.

    Issue #281: Refactored from 145 lines to use extracted helper method.
    Issue #398: Further refactored to extract scanning, processing, and response logic.
    """
    from backend.models.knowledge_import_tracking import ImportTracker

    force_reindex = request.get("force", False) if request else False
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb_to_use is None:
        return {
            "status": "error",
            "message": "Knowledge base not initialized",
            "items_added": 0,
        }

    logger.info("Starting AutoBot documentation population with import tracking...")

    tracker = ImportTracker()
    autobot_base_path = PathLib(__file__).parent.parent.parent

    doc_files, scan_skipped = await _scan_doc_files(
        autobot_base_path, tracker, force_reindex
    )
    items_added, proc_skipped, items_failed = await _process_all_doc_files(
        kb_to_use, tracker, autobot_base_path, doc_files
    )
    items_skipped = scan_skipped + proc_skipped

    if await _store_autobot_config_info(kb_to_use):
        items_added += 1

    logger.info(
        "AutoBot docs completed: %s added, %s skipped, %s failed",
        items_added,
        items_skipped,
        items_failed,
    )
    return _build_population_response(
        items_added, items_skipped, items_failed, len(doc_files), force_reindex
    )


# =========================================================================
# Issue #423: Scan Man Pages Endpoint with Structured Parsing
# =========================================================================


async def _store_single_man_page(kb_to_use, man_page: dict) -> bool:
    """Store a single man page in knowledge base (Issue #398: extracted)."""
    content = man_page.get("content", "")
    if not content:
        return False

    try:
        result = await kb_to_use.store_fact(
            content=content,
            metadata=man_page.get("metadata", {}),
        )
        return result and result.get("status") == "success"
    except Exception as e:
        logger.error("Error storing man page %s: %s", man_page.get("command"), e)
        return False


async def _store_man_pages_batch(kb_to_use, man_pages: list) -> tuple[int, int]:
    """Store batch of man pages, returns (added, failed) counts (Issue #398: extracted)."""
    items_added = 0
    items_failed = 0

    for man_page in man_pages:
        if await _store_single_man_page(kb_to_use, man_page):
            items_added += 1
        else:
            items_failed += 1
        await asyncio.sleep(TimingConstants.MICRO_DELAY)

    return items_added, items_failed


def _build_man_scan_result(
    items_added: int, items_failed: int, total: int, machine_id: str
) -> dict:
    """Build result dict for man page scan (Issue #398: extracted)."""
    return {
        "status": "success",
        "message": f"Indexed {items_added} man pages ({items_failed} failed)",
        "items_added": items_added,
        "items_failed": items_failed,
        "total_scanned": total,
        "machine_id": machine_id,
    }


async def _scan_and_store_man_pages(
    kb_to_use,
    machine_id: str,
    limit: int | None,
    sections: list[str] | None,
    system_context: dict | None,
) -> dict:
    """
    Background task to scan and store man pages (Issue #398: refactored).

    Issue #423: Uses ManPageParser for structured content extraction.
    """
    from autobot_shared.redis_client import get_redis_client
    from backend.services.fast_document_scanner import FastDocumentScanner

    try:
        redis_client = get_redis_client(async_client=False, database="main")
        scanner = FastDocumentScanner(redis_client)

        logger.info("Scanning man pages (limit=%s, sections=%s)...", limit, sections)
        # Issue #666: Wrap blocking scanner call in asyncio.to_thread to avoid event loop blocking
        man_pages = await asyncio.to_thread(
            scanner.get_all_man_pages_for_indexing,
            limit=limit,
            sections=sections,
            system_context=system_context,
        )

        if not man_pages:
            return {
                "status": "success",
                "message": "No man pages found to index",
                "items_added": 0,
                "items_failed": 0,
            }

        items_added, items_failed = await _store_man_pages_batch(kb_to_use, man_pages)
        logger.info(
            "Man page scan complete: %s added, %s failed", items_added, items_failed
        )
        return _build_man_scan_result(
            items_added, items_failed, len(man_pages), machine_id
        )

    except Exception as e:
        logger.error("Man page scan failed: %s", e)
        return {
            "status": "error",
            "message": str(e),
            "items_added": 0,
            "items_failed": 0,
        }


def _get_system_context_safe(machine_id: str) -> dict:
    """Get system context for metadata, fallback to machine_id (Issue #398: extracted)."""
    try:
        from utils.system_context import get_system_context

        return get_system_context()
    except ImportError:
        return {"machine_id": machine_id}


def _parse_scan_request(request: dict | None) -> tuple[int | None, list | None, bool]:
    """Parse scan request parameters (Issue #398: extracted)."""
    if not request:
        return None, None, True
    return (
        request.get("limit"),
        request.get("sections"),
        request.get("background", True),
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="scan_man_pages",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/scan_man_pages")
async def scan_man_pages(
    request: dict,
    req: Request,
    background_tasks: BackgroundTasks,
):
    """Scan and index system man pages (Issue #398: refactored)."""
    import socket

    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb_to_use is None:
        return {
            "status": "error",
            "message": "Knowledge base not initialized",
            "items_added": 0,
        }

    limit, sections, run_background = _parse_scan_request(request)
    machine_id = socket.gethostname()
    system_context = _get_system_context_safe(machine_id)

    if run_background:
        background_tasks.add_task(
            _scan_and_store_man_pages,
            kb_to_use,
            machine_id,
            limit,
            sections,
            system_context,
        )
        return {
            "status": "success",
            "message": "Man page scan started in background",
            "background": True,
            "machine_id": machine_id,
            "limit": limit,
            "sections": sections,
        }

    result = await _scan_and_store_man_pages(
        kb_to_use, machine_id, limit, sections, system_context
    )
    result["background"] = False
    return result


async def _store_parsed_man_pages(kb_to_use, parsed_content: list) -> int:
    """Store parsed man pages in knowledge base (Issue #398: extracted)."""
    items_added = 0
    for parsed in parsed_content:
        try:
            result = await kb_to_use.store_fact(
                content=parsed.get("content", ""),
                metadata=parsed.get("metadata", {}),
            )
            if result and result.get("status") == "success":
                items_added += 1
        except Exception as e:
            logger.error("Error storing parsed man page: %s", e)
    return items_added


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="scan_man_pages_changes",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/scan_man_pages_changes")
async def scan_man_pages_changes(
    request: dict,
    req: Request,
    background_tasks: BackgroundTasks,
):
    """Scan for changed man pages only (Issue #398: refactored)."""
    import socket

    from autobot_shared.redis_client import get_redis_client
    from backend.services.fast_document_scanner import FastDocumentScanner

    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb_to_use is None:
        return {"status": "error", "message": "Knowledge base not initialized"}

    limit = request.get("limit") if request else None
    machine_id = socket.gethostname()

    redis_client = get_redis_client(async_client=False, database="main")
    scanner = FastDocumentScanner(redis_client)
    system_context = _get_system_context_safe(machine_id)

    # Issue #666: Wrap blocking scanner call in asyncio.to_thread to avoid event loop blocking
    scan_result = await asyncio.to_thread(
        scanner.scan_and_parse_changes,
        machine_id=machine_id,
        limit=limit,
        system_context=system_context,
    )

    items_added = await _store_parsed_man_pages(
        kb_to_use, scan_result.get("parsed_content", [])
    )

    return {
        "status": "success",
        "machine_id": machine_id,
        "scan_duration_seconds": scan_result.get("scan_duration_seconds", 0),
        "summary": scan_result.get("summary", {}),
        "items_stored": items_added,
        "parsed_count": scan_result.get("parsed_count", 0),
    }
