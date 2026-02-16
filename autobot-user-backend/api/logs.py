# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unified Log Viewer API
Provides endpoints to read and stream AutoBot logs from both files and Docker containers

Issue #718: Uses dedicated thread pool for log I/O to prevent blocking
when the main asyncio thread pool is saturated by indexing operations.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set

import aiofiles
from auth_middleware import check_admin_permission
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket
from fastapi.responses import StreamingResponse

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from backend.constants.path_constants import PATH
from backend.constants.threshold_constants import TimingConstants
from backend.type_defs.common import Metadata
from backend.utils.io_executor import run_in_log_executor

logger = logging.getLogger(__name__)

router = APIRouter(tags=["logs"])

# Performance optimization: O(1) lookup for log level detection (Issue #326)
LOG_LEVEL_KEYWORDS = {"CRITICAL", "ERROR", "WARN", "WARNING", "INFO", "DEBUG"}

# Issue #380: Module-level frozenset for protected log files
_PROTECTED_LOG_FILES = frozenset({"system.log", "backend.log", "frontend.log"})

# Log directory
LOG_DIR = Path(__file__).parent.parent.parent / "logs"

# Issue #514: Per-file locking to prevent concurrent write corruption
from typing import Dict

_log_file_locks: Dict[str, asyncio.Lock] = {}
_log_locks_lock = asyncio.Lock()


async def _get_log_file_lock(filepath: str) -> asyncio.Lock:
    """
    Get or create a lock for a specific log file path (Issue #514).

    Uses per-file locking to prevent concurrent writes to the same log file.

    Args:
        filepath: Path to the log file

    Returns:
        asyncio.Lock for the specified file
    """
    async with _log_locks_lock:
        if filepath not in _log_file_locks:
            _log_file_locks[filepath] = asyncio.Lock()
        return _log_file_locks[filepath]


# Docker container names and their tags for log access
CONTAINER_LOGS = {
    "dns-cache": "autobot-dns-cache",
    "redis": "autobot-redis",
    "browser-service": "autobot-browser",
    "frontend": "autobot-frontend",
    "ai-stack": "autobot-ai-stack",
    "npu-worker": "autobot-npu-worker",
}


# Forward declaration for parse functions (defined later in file)
def _parse_file_log_line_for_unified(line: str, source: str) -> Metadata:
    """Forward declaration - actual implementation uses parse_file_log_line."""
    pass  # Replaced at module load


def _parse_docker_log_line_for_unified(line: str, service: str) -> Metadata:
    """Forward declaration - actual implementation uses parse_docker_log_line."""
    pass  # Replaced at module load


def _parse_file_content_lines(
    content: str, file_name: str, level: Optional[str]
) -> List[Metadata]:
    """Parse file log content lines with optional level filter (Issue #315: extracted).

    Args:
        content: File content as string
        file_name: Source file name for log entries
        level: Optional log level filter

    Returns:
        List of parsed log entries
    """
    logs = []
    for line in content.splitlines()[-50:]:
        if not line.strip():
            continue
        parsed = parse_file_log_line(line.strip(), file_name)
        if level and parsed.get("level", "").upper() != level.upper():
            continue
        parsed["source_type"] = "file"
        logs.append(parsed)
    return logs


async def _tail_file_to_websocket(file_path: Path, websocket: WebSocket) -> None:
    """Tail a log file and send lines to WebSocket (Issue #315: extracted).

    Sends last 50 lines initially, then watches for new lines.
    """
    async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
        # Send last 50 lines initially
        content = await f.read()
        lines = content.splitlines()
        for line in lines[-50:]:
            await websocket.send_text(line)

        # Continue watching for new lines
        await f.seek(0, 2)  # Go to end of file
        while True:
            line = await f.readline()
            if line:
                await websocket.send_text(line.rstrip())
            else:
                # Brief delay while polling for new log lines
                await asyncio.sleep(TimingConstants.MICRO_DELAY)


async def _read_log_lines_from_file(
    file_path: Path, lines: int, offset: int, tail: bool
) -> tuple:
    """Read lines from log file with offset/tail support (Issue #315: extracted).

    Args:
        file_path: Path to log file
        lines: Number of lines to read
        offset: Line offset
        tail: If True, read from end of file

    Returns:
        Tuple of (selected_lines, total_lines)
    """
    async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
        if tail:
            content = await f.read()
            all_lines = content.splitlines()
            start_idx = max(0, len(all_lines) - lines - offset)
            end_idx = len(all_lines) - offset
            return all_lines[start_idx:end_idx], len(all_lines)
        else:
            all_lines = []
            async for line in f:
                all_lines.append(line.rstrip())
            start_idx = offset
            end_idx = min(offset + lines, len(all_lines))
            return all_lines[start_idx:end_idx], len(all_lines)


async def _collect_file_logs(
    source_filter: Set[str], level: Optional[str]
) -> List[Metadata]:
    """Collect logs from file sources (Issue #336 - extracted helper).

    Issue #370: Optimized to read files in parallel using asyncio.gather().

    Args:
        source_filter: Set of source names to include (empty = all)
        level: Optional log level filter

    Returns:
        List of parsed log entries
    """
    log_dir_exists = await run_in_log_executor(LOG_DIR.exists)
    if not log_dir_exists:
        return []

    # Issue #358 - use lambda for proper glob() execution in thread
    log_files = await run_in_log_executor(lambda: list(LOG_DIR.glob("*.log")))

    # Filter files first
    filtered_files = [
        (fp, fp.stem)
        for fp in log_files
        if not source_filter or fp.stem in source_filter
    ]

    if not filtered_files:
        return []

    # Issue #370: Read all files in parallel
    async def read_file_logs(file_path, file_name):
        """Read and parse log entries from a single file."""
        try:
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                content = await f.read()
                return _parse_file_content_lines(content, file_name, level)
        except OSError as e:
            logger.debug("Error reading file log %s: %s", file_path, e)
            return []

    results = await asyncio.gather(
        *[read_file_logs(fp, fn) for fp, fn in filtered_files], return_exceptions=True
    )

    # Flatten results
    logs = []
    for result in results:
        if isinstance(result, list):
            logs.extend(result)
    return logs


async def _get_container_output(container_name: str, service: str) -> Optional[bytes]:
    """Get stdout from a Docker container (Issue #315 - extracted helper)."""
    try:
        process = await asyncio.create_subprocess_exec(
            "docker",
            "logs",
            container_name,
            "--timestamps",
            "--tail=50",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=10)
        return stdout if process.returncode == 0 else None
    except asyncio.TimeoutError:
        logger.debug("Timeout getting container logs for %s", service)
        return None
    except OSError as e:
        logger.debug("Error getting container logs for %s: %s", service, e)
        return None


def _parse_container_log_lines(
    stdout: bytes, service: str, level: Optional[str]
) -> List[Metadata]:
    """Parse Docker container log lines (Issue #315 - extracted helper)."""
    logs = []
    for line in stdout.decode().split("\n"):
        if not line.strip():
            continue
        parsed = parse_docker_log_line(line, service)
        if level and parsed.get("level", "").upper() != level.upper():
            continue
        parsed["source_type"] = "container"
        logs.append(parsed)
    return logs


async def _collect_container_logs(
    source_filter: Set[str], level: Optional[str]
) -> List[Metadata]:
    """Collect logs from Docker containers (Issue #315 - refactored).

    Issue #370: Optimized to fetch container logs in parallel using asyncio.gather().

    Args:
        source_filter: Set of source names to include (empty = all)
        level: Optional log level filter

    Returns:
        List of parsed log entries
    """
    # Filter containers first
    filtered_containers = [
        (service, container_name)
        for service, container_name in CONTAINER_LOGS.items()
        if not source_filter or service in source_filter
    ]

    if not filtered_containers:
        return []

    # Issue #370: Fetch all container logs in parallel
    async def get_and_parse_container_logs(service, container_name):
        """Fetch and parse logs from a single container."""
        stdout = await _get_container_output(container_name, service)
        if stdout:
            return _parse_container_log_lines(stdout, service, level)
        return []

    results = await asyncio.gather(
        *[get_and_parse_container_logs(svc, cn) for svc, cn in filtered_containers],
        return_exceptions=True,
    )

    # Flatten results
    logs = []
    for result in results:
        if isinstance(result, list):
            logs.extend(result)
    return logs


async def _get_file_log_sources() -> List[Metadata]:
    """Get file log source information (Issue #315 - extracted helper).

    Issue #370: Optimized to stat files in parallel using asyncio.gather().
    """
    log_dir_exists = await run_in_log_executor(LOG_DIR.exists)
    if not log_dir_exists:
        return []

    # Issue #358 - use lambda for proper glob() execution in thread
    log_files = await run_in_log_executor(lambda: list(LOG_DIR.glob("*.log")))
    if not log_files:
        return []

    # Issue #370: Stat all files in parallel
    async def get_file_info(file_path):
        """Get metadata for a single log file."""
        stat = await run_in_log_executor(file_path.stat)
        return {
            "name": file_path.name,
            "type": "file",
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "size_mb": round(stat.st_size / 1024 / 1024, 2),
        }

    results = await asyncio.gather(
        *[get_file_info(fp) for fp in log_files], return_exceptions=True
    )

    return [r for r in results if isinstance(r, dict)]


async def _check_container_status(
    service: str, container_name: str
) -> Optional[Metadata]:
    """Check status of a single Docker container (Issue #315 - extracted helper)."""
    try:
        process = await asyncio.create_subprocess_exec(
            "docker",
            "ps",
            "-a",
            "--filter",
            f"name={container_name}",
            "--format",
            "{{.Names}}\t{{.Status}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=5)
        stdout_str = stdout.decode()

        if process.returncode == 0 and container_name in stdout_str:
            status = "running" if "Up" in stdout_str else "stopped"
            return {
                "name": service,
                "container_name": container_name,
                "type": "container",
                "status": status,
            }
    except asyncio.TimeoutError:
        logger.warning("Timeout checking container %s", container_name)
    except Exception as e:
        logger.error("Error checking container %s: %s", container_name, e)
    return None


async def _get_container_log_sources() -> List[Metadata]:
    """Get container log source information (Issue #315 - extracted helper)."""
    container_logs = []
    for service, container_name in CONTAINER_LOGS.items():
        result = await _check_container_status(service, container_name)
        if result:
            container_logs.append(result)
    return container_logs


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_log_sources",
    error_code_prefix="LOGS",
)
# Issue #552: Fixed duplicate /logs prefix - router already mounted at /api/logs
@router.get("/sources")
async def get_log_sources(admin_check: bool = Depends(check_admin_permission)):
    """Get all available log sources (files + Docker containers) (Issue #315 - refactored).

    Issue #744: Requires admin authentication.
    """
    try:
        # Issue #379: Parallelize independent log source collection
        file_logs, container_logs = await asyncio.gather(
            _get_file_log_sources(),
            _get_container_log_sources(),
        )

        # Sort file logs by modified time
        file_logs.sort(key=lambda x: x["modified"], reverse=True)

        return {
            "file_logs": file_logs,
            "container_logs": container_logs,
            "total_sources": len(file_logs) + len(container_logs),
        }
    except Exception as e:
        logger.error("Error getting log sources: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


async def _get_most_recent_log_file(log_dir: str) -> Optional[str]:
    """Get the most recently modified log file (Issue #315 - extracted helper)."""
    log_dir_exists = await run_in_log_executor(os.path.exists, log_dir)
    if not log_dir_exists:
        return None

    all_files = await run_in_log_executor(os.listdir, log_dir)
    log_files = [f for f in all_files if f.endswith(".log")]
    if not log_files:
        return None

    # Get modification times
    def get_mtime(f):
        """Get modification time of a file in the log directory."""
        return os.path.getmtime(os.path.join(log_dir, f))

    mtimes = {}
    for f in log_files:
        mtimes[f] = await run_in_log_executor(get_mtime, f)

    log_files.sort(key=lambda f: mtimes[f], reverse=True)
    return log_files[0]


async def _read_recent_log_lines(log_path: str, limit: int) -> List[str]:
    """Read recent lines from a log file (Issue #315 - extracted helper)."""
    try:
        async with aiofiles.open(log_path, "r") as f:
            content = await f.read()
            lines = content.splitlines(keepends=True)
            return lines[-limit:] if len(lines) > limit else lines
    except Exception as e:
        logger.error("Error reading log file %s: %s", log_path, e)
        return []


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_recent_logs",
    error_code_prefix="LOGS",
)
@router.get("/recent")
async def get_recent_logs(
    limit: int = 100,
    admin_check: bool = Depends(check_admin_permission),
):
    """Get recent log entries across all log files (Issue #315 - refactored).

    Issue #744: Requires admin authentication.
    """
    try:
        log_dir = str(PATH.LOGS_DIR)
        recent_entries = []

        most_recent = await _get_most_recent_log_file(log_dir)
        if most_recent:
            log_path = os.path.join(log_dir, most_recent)
            recent_entries = await _read_recent_log_lines(log_path, limit)

        return {
            "entries": recent_entries,
            "count": len(recent_entries),
            "limit": limit,
            "source": "file_logs",
        }
    except Exception as e:
        logger.error("Error getting recent logs: %s", e)
        return {"entries": [], "count": 0, "limit": limit, "error": str(e)}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_logs",
    error_code_prefix="LOGS",
)
@router.get("/list")
async def list_logs(
    admin_check: bool = Depends(check_admin_permission),
) -> List[Metadata]:
    """List all available log files (backward compatibility).

    Issue #744: Requires admin authentication.
    """
    try:
        sources = await get_log_sources()
        return sources["file_logs"]
    except Exception as e:
        logger.error("Error listing logs: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="read_log",
    error_code_prefix="LOGS",
)
@router.get("/read/{filename}")
async def read_log(
    filename: str,
    admin_check: bool = Depends(check_admin_permission),
    lines: int = Query(100, description="Number of lines to read"),
    offset: int = Query(0, description="Line offset"),
    tail: bool = Query(False, description="Read from end of file"),
):
    """Read log file content.

    Issue #744: Requires admin authentication.
    """
    try:
        file_path = LOG_DIR / filename
        file_exists = await run_in_log_executor(file_path.exists)
        is_file = await run_in_log_executor(file_path.is_file) if file_exists else False
        if not file_exists or not is_file:
            raise HTTPException(status_code=404, detail="Log file not found")

        # Security check - ensure file is within LOG_DIR
        resolved_path = await run_in_log_executor(file_path.resolve)
        resolved_log_dir = await run_in_log_executor(LOG_DIR.resolve)
        if not str(resolved_path).startswith(str(resolved_log_dir)):
            raise HTTPException(status_code=403, detail="Access denied")

        try:
            # Use extracted helper (Issue #315: reduced nesting)
            selected_lines, total_lines = await _read_log_lines_from_file(
                file_path, lines, offset, tail
            )
        except OSError as e:
            logger.error("Failed to read log file %s: %s", file_path, e)
            raise HTTPException(status_code=500, detail=f"Failed to read log file: {e}")

        return {
            "filename": filename,
            "lines": selected_lines,
            "total_lines": total_lines,
            "offset": offset,
            "count": len(selected_lines),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error reading log %s: %s", filename, e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="read_container_logs",
    error_code_prefix="LOGS",
)
@router.get("/container/{service}")
async def read_container_logs(
    service: str,
    admin_check: bool = Depends(check_admin_permission),
    lines: int = Query(100, ge=1, le=10000, description="Number of lines to read"),
    since: Optional[str] = Query(None, description="Duration like '1h', '30m', '1d'"),
    tail: bool = Query(True, description="Read from end of logs"),
):
    """Read logs from a Docker container.

    Issue #744: Requires admin authentication.
    """
    try:
        if service not in CONTAINER_LOGS:
            raise HTTPException(
                status_code=404, detail=f"Service '{service}' not found"
            )

        container_name = CONTAINER_LOGS[service]

        # Build docker logs command
        cmd = ["docker", "logs", container_name, "--timestamps"]

        if tail:
            cmd.append(f"--tail={lines}")
        else:
            cmd.append("--since=1d")  # Get recent logs if not tailing

        if since:
            cmd.extend(["--since", since])

        # Execute command asynchronously
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise HTTPException(status_code=408, detail="Container log read timed out")

        if process.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get container logs: {stderr.decode()}",
            )

        # Parse logs
        log_lines = []
        for line in stdout.decode().split("\n"):
            if line.strip():
                parsed_line = parse_docker_log_line(line, service)
                log_lines.append(parsed_line)

        # Limit results
        if not tail and len(log_lines) > lines:
            log_lines = log_lines[-lines:]

        return {
            "service": service,
            "container": container_name,
            "lines": log_lines,
            "count": len(log_lines),
            "source_type": "container",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error reading container logs for %s: %s", service, e)
        raise HTTPException(status_code=500, detail=str(e))


def _extract_log_level(message: str) -> str:
    """Extract log level from message text (Issue #315 - extracted helper)."""
    message_upper = message.upper()
    for level in LOG_LEVEL_KEYWORDS:
        if level in message_upper:
            return "WARNING" if level == "WARN" else level
    return "INFO"


def _parse_docker_timestamp_format(line: str, parsed: Metadata) -> str:
    """Parse Docker timestamp format (Issue #315 - extracted helper)."""
    # Docker log format: 2024-01-01T12:00:00.000000000Z message
    if not (line.startswith("20") and "T" in line[:25]):
        return line.strip()

    parts = line.split(" ", 1)
    if len(parts) < 2:
        return line.strip()

    parsed["timestamp"] = parts[0]
    message = parts[1]
    parsed["level"] = _extract_log_level(message)
    return message


def _parse_json_log_data(parsed: Metadata) -> None:
    """Parse JSON log data if present (Issue #315 - extracted helper)."""
    message = parsed.get("message", "").strip()
    if not message.startswith("{"):
        return

    try:
        json_data = json.loads(message)
        if "level" in json_data:
            parsed["level"] = json_data["level"].upper()
        if "message" in json_data:
            parsed["message"] = json_data["message"]
        if "timestamp" in json_data:
            parsed["timestamp"] = json_data["timestamp"]
    except json.JSONDecodeError:
        logger.debug("Log line is plain text, not JSON format")


def parse_docker_log_line(line: str, service: str) -> Metadata:
    """Parse a Docker log line and extract structured information (Issue #315 - refactored)."""
    parsed = {
        "raw": line.strip(),
        "service": service,
        "timestamp": "",
        "level": "INFO",
        "message": line.strip(),
    }

    try:
        parsed["message"] = _parse_docker_timestamp_format(line, parsed)
        _parse_json_log_data(parsed)
    except Exception as e:
        logger.debug("Failed to parse Docker log line: %s", e)

    return parsed


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_unified_logs",
    error_code_prefix="LOGS",
)
@router.get("/unified")
async def get_unified_logs(
    admin_check: bool = Depends(check_admin_permission),
    lines: int = Query(
        100, ge=1, le=1000, description="Total number of lines to return"
    ),
    level: Optional[str] = Query(None, description="Filter by log level"),
    sources: Optional[str] = Query(None, description="Comma-separated list of sources"),
):
    """Get unified logs from all sources, merged by timestamp.

    Issue #744: Requires admin authentication.
    """
    try:
        # Parse sources filter
        source_filter: Set[str] = set()
        if sources:
            source_filter = set(sources.split(","))

        # Issue #379: Parallelize independent log collection operations
        file_logs, container_logs = await asyncio.gather(
            _collect_file_logs(source_filter, level),
            _collect_container_logs(source_filter, level),
        )

        all_logs = file_logs + container_logs

        # Sort by timestamp (newest first) and limit
        all_logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        return {
            "logs": all_logs[:lines],
            "total_count": len(all_logs),
            "sources_included": list(set(log.get("service", "") for log in all_logs)),
        }

    except Exception as e:
        logger.error("Error getting unified logs: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _parse_file_timestamp(line: str) -> Optional[str]:
    """Extract timestamp from file log line (Issue #315 - extracted helper)."""
    # Format: 2024-01-01 12:00:00,000 [logger] LEVEL: message
    parts = line.split(" ", 3)
    if len(parts) < 3:
        return None

    # Check if first part looks like a date
    if not (parts[0] and len(parts[0]) >= 10 and "-" in parts[0]):
        return None

    return f"{parts[0]} {parts[1]}" if len(parts) > 1 else parts[0]


def parse_file_log_line(line: str, source: str) -> Metadata:
    """Parse a file log line and extract structured information (Issue #315 - refactored)."""
    parsed = {
        "raw": line,
        "service": source,
        "timestamp": "",
        "level": "INFO",
        "message": line,
    }

    try:
        timestamp = _parse_file_timestamp(line)
        if timestamp:
            parsed["timestamp"] = timestamp
            parsed["level"] = _extract_log_level(line)
    except Exception as e:
        logger.debug("Failed to parse general log line: %s", e)

    return parsed


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="stream_log",
    error_code_prefix="LOGS",
)
@router.get("/stream/{filename}")
async def stream_log(
    filename: str,
    admin_check: bool = Depends(check_admin_permission),
):
    """Stream log file content.

    Issue #744: Requires admin authentication.
    """
    try:
        file_path = LOG_DIR / filename
        file_exists = await run_in_log_executor(file_path.exists)
        is_file = await run_in_log_executor(file_path.is_file) if file_exists else False
        if not file_exists or not is_file:
            raise HTTPException(status_code=404, detail="Log file not found")

        # Security check
        resolved_path = await run_in_log_executor(file_path.resolve)
        resolved_log_dir = await run_in_log_executor(LOG_DIR.resolve)
        if not str(resolved_path).startswith(str(resolved_log_dir)):
            raise HTTPException(status_code=403, detail="Access denied")

        async def generate():
            """Generate log file content line by line for streaming response."""
            try:
                async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                    async for line in f:
                        yield line
            except OSError as e:
                logger.error("Failed to stream log file %s: %s", file_path, e)
                # Yield error message to client and stop
                return

        return StreamingResponse(generate(), media_type="text/plain")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error streaming log %s: %s", filename, e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="tail_log",
    error_code_prefix="LOGS",
)
@router.websocket("/tail/{filename}")
async def tail_log(websocket: WebSocket, filename: str):
    """WebSocket endpoint to tail log file in real-time"""
    await websocket.accept()

    try:
        file_path = LOG_DIR / filename
        file_exists = await run_in_log_executor(file_path.exists)
        is_file = await run_in_log_executor(file_path.is_file) if file_exists else False
        if not file_exists or not is_file:
            await websocket.send_json({"error": "Log file not found"})
            await websocket.close()
            return

        # Security check
        resolved_path = await run_in_log_executor(file_path.resolve)
        resolved_log_dir = await run_in_log_executor(LOG_DIR.resolve)
        if not str(resolved_path).startswith(str(resolved_log_dir)):
            await websocket.send_json({"error": "Access denied"})
            await websocket.close()
            return

        # Start tailing the file (Issue #315: uses extracted helper)
        try:
            await _tail_file_to_websocket(file_path, websocket)
        except OSError as e:
            logger.error("Failed to tail log file %s: %s", file_path, e)
            await websocket.send_json({"error": f"Failed to read log file: {e}"})
            return

    except Exception as e:
        logger.error("WebSocket error for %s: %s", filename, e)
        try:
            await websocket.send_json({"error": str(e)})
        except Exception as send_err:
            logger.debug("Failed to send error to WebSocket: %s", send_err)
    finally:
        try:
            await websocket.close()
        except Exception as close_err:
            logger.debug("Failed to close WebSocket: %s", close_err)


def _line_matches_query(line_content: str, query: str, case_sensitive: bool) -> bool:
    """Check if a line matches the search query with optional case sensitivity."""
    if case_sensitive:
        return query in line_content
    return query.lower() in line_content.lower()


def _create_search_result(file_name: str, line_num: int, line_content: str) -> dict:
    """Create a search result entry with file, line number, and timestamp."""
    return {
        "file": file_name,
        "line": line_num,
        "content": line_content,
        "timestamp": datetime.now().isoformat(),
    }


async def _search_single_log_file(
    file_path, query: str, case_sensitive: bool, max_results: int, current_count: int
) -> list:
    """Search a single log file for matching lines."""
    results = []
    async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
        line_num = 0
        async for line in f:
            line_num += 1
            line_content = line.rstrip()

            if not _line_matches_query(line_content, query, case_sensitive):
                continue

            results.append(
                _create_search_result(file_path.name, line_num, line_content)
            )

            if current_count + len(results) >= max_results:
                break

    return results


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_logs",
    error_code_prefix="LOGS",
)
@router.get("/search")
async def search_logs(
    admin_check: bool = Depends(check_admin_permission),
    query: str = Query(..., description="Search query"),
    filename: Optional[str] = Query(None, description="Specific file to search"),
    case_sensitive: bool = Query(False, description="Case sensitive search"),
    max_results: int = Query(100, description="Maximum results"),
):
    """Search across log files.

    Issue #744: Requires admin authentication.
    """
    try:
        results = []
        files_to_search = []

        if filename:
            file_path = LOG_DIR / filename
            file_exists = await run_in_log_executor(file_path.exists)
            if file_exists:
                files_to_search.append(file_path)
        else:
            # Issue #358 - use lambda for proper glob() execution in thread
            files_to_search = await run_in_log_executor(
                lambda: list(LOG_DIR.glob("*.log"))
            )

        for file_path in files_to_search:
            if len(results) >= max_results:
                break

            try:
                file_results = await _search_single_log_file(
                    file_path, query, case_sensitive, max_results, len(results)
                )
                results.extend(file_results)
            except OSError as e:
                logger.error("Failed to search log file %s: %s", file_path, e)
                continue

        return {
            "query": query,
            "results": results,
            "count": len(results),
            "truncated": len(results) >= max_results,
        }

    except Exception as e:
        logger.error("Error searching logs: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_log",
    error_code_prefix="LOGS",
)
@router.delete("/clear/{filename}")
async def clear_log(
    filename: str,
    admin_check: bool = Depends(check_admin_permission),
):
    """Clear a log file (truncate to 0 bytes).

    Issue #744: Requires admin authentication.
    """
    try:
        file_path = LOG_DIR / filename
        file_exists = await run_in_log_executor(file_path.exists)
        is_file = await run_in_log_executor(file_path.is_file) if file_exists else False
        if not file_exists or not is_file:
            raise HTTPException(status_code=404, detail="Log file not found")

        # Security check
        resolved_path = await run_in_log_executor(file_path.resolve)
        resolved_log_dir = await run_in_log_executor(LOG_DIR.resolve)
        if not str(resolved_path).startswith(str(resolved_log_dir)):
            raise HTTPException(status_code=403, detail="Access denied")

        # Don't delete critical logs (Issue #380: use module-level constant)
        if filename in _PROTECTED_LOG_FILES:
            raise HTTPException(
                status_code=403, detail="Cannot clear protected log files"
            )

        # Truncate file
        # Issue #514: Use per-file locking to prevent concurrent write corruption
        file_lock = await _get_log_file_lock(str(file_path))
        async with file_lock:
            async with aiofiles.open(file_path, "w") as f:
                await f.write("")

        return {"message": f"Log file {filename} cleared successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error clearing log %s: %s", filename, e)
        raise HTTPException(status_code=500, detail=str(e))
