# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unified Log Viewer API
Provides endpoints to read and stream AutoBot logs from both files and Docker containers
"""

import asyncio
import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from backend.type_defs.common import Metadata

import aiofiles
from fastapi import APIRouter, HTTPException, Query, WebSocket
from fastapi.responses import StreamingResponse

from src.constants.path_constants import PATH
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

router = APIRouter(tags=["logs"])

# Log directory
LOG_DIR = Path(__file__).parent.parent.parent / "logs"

# Docker container names and their tags for log access
CONTAINER_LOGS = {
    "dns-cache": "autobot-dns-cache",
    "redis": "autobot-redis",
    "browser-service": "autobot-browser",
    "frontend": "autobot-frontend",
    "ai-stack": "autobot-ai-stack",
    "npu-worker": "autobot-npu-worker",
}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_log_sources",
    error_code_prefix="LOGS",
)
@router.get("/logs/sources")
async def get_log_sources():
    """Get all available log sources (files + Docker containers)"""
    try:
        sources = {"file_logs": [], "container_logs": [], "total_sources": 0}

        # List file logs
        log_dir_exists = await asyncio.to_thread(LOG_DIR.exists)
        if log_dir_exists:
            log_files = await asyncio.to_thread(list, LOG_DIR.glob("*.log"))
            for file_path in log_files:
                stat = await asyncio.to_thread(file_path.stat)
                sources["file_logs"].append(
                    {
                        "name": file_path.name,
                        "type": "file",
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "size_mb": round(stat.st_size / 1024 / 1024, 2),
                    }
                )

        # Check Docker containers
        for service, container_name in CONTAINER_LOGS.items():
            try:
                # Check if container exists and is running
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
                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), timeout=5
                    )
                    stdout_str = stdout.decode()

                    if process.returncode == 0 and container_name in stdout_str:
                        status = "running" if "Up" in stdout_str else "stopped"
                        sources["container_logs"].append(
                            {
                                "name": service,
                                "container_name": container_name,
                                "type": "container",
                                "status": status,
                            }
                        )
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout checking container {container_name}")
            except Exception as e:
                logger.error(f"Error checking container {container_name}: {e}")

        sources["total_sources"] = len(sources["file_logs"]) + len(
            sources["container_logs"]
        )

        # Sort file logs by modified time
        sources["file_logs"].sort(key=lambda x: x["modified"], reverse=True)

        return sources

    except Exception as e:
        logger.error(f"Error getting log sources: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_recent_logs",
    error_code_prefix="LOGS",
)
@router.get("/logs/recent")
async def get_recent_logs(limit: int = 100):
    """Get recent log entries across all log files"""
    try:
        log_dir = str(PATH.LOGS_DIR)
        recent_entries = []

        # Get the most recent log file
        log_dir_exists = await asyncio.to_thread(os.path.exists, log_dir)
        if log_dir_exists:
            all_files = await asyncio.to_thread(os.listdir, log_dir)
            log_files = [f for f in all_files if f.endswith(".log")]
            if log_files:
                # Sort by modification time and get the most recent
                def get_mtime(f):
                    return os.path.getmtime(os.path.join(log_dir, f))

                mtimes = {}
                for f in log_files:
                    mtimes[f] = await asyncio.to_thread(get_mtime, f)
                log_files.sort(key=lambda f: mtimes[f], reverse=True)
                most_recent = log_files[0]

                # Read the last N lines from the most recent log
                log_path = os.path.join(log_dir, most_recent)
                try:
                    async with aiofiles.open(log_path, "r") as f:
                        content = await f.read()
                        lines = content.splitlines(keepends=True)
                        recent_entries = lines[-limit:] if len(lines) > limit else lines
                except Exception as e:
                    logger.error(f"Error reading log file {most_recent}: {e}")

        return {
            "entries": recent_entries,
            "count": len(recent_entries),
            "limit": limit,
            "source": "file_logs",
        }
    except Exception as e:
        logger.error(f"Error getting recent logs: {e}")
        return {"entries": [], "count": 0, "limit": limit, "error": str(e)}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_logs",
    error_code_prefix="LOGS",
)
@router.get("/logs/list")
async def list_logs() -> List[Metadata]:
    """List all available log files (backward compatibility)"""
    try:
        sources = await get_log_sources()
        return sources["file_logs"]
    except Exception as e:
        logger.error(f"Error listing logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="read_log",
    error_code_prefix="LOGS",
)
@router.get("/logs/read/{filename}")
async def read_log(
    filename: str,
    lines: int = Query(100, description="Number of lines to read"),
    offset: int = Query(0, description="Line offset"),
    tail: bool = Query(False, description="Read from end of file"),
):
    """Read log file content"""
    try:
        file_path = LOG_DIR / filename
        file_exists = await asyncio.to_thread(file_path.exists)
        is_file = await asyncio.to_thread(file_path.is_file) if file_exists else False
        if not file_exists or not is_file:
            raise HTTPException(status_code=404, detail="Log file not found")

        # Security check - ensure file is within LOG_DIR
        resolved_path = await asyncio.to_thread(file_path.resolve)
        resolved_log_dir = await asyncio.to_thread(LOG_DIR.resolve)
        if not str(resolved_path).startswith(str(resolved_log_dir)):
            raise HTTPException(status_code=403, detail="Access denied")

        try:
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                if tail:
                    # Read last N lines
                    content = await f.read()
                    all_lines = content.splitlines()
                    start_idx = max(0, len(all_lines) - lines - offset)
                    end_idx = len(all_lines) - offset
                    selected_lines = all_lines[start_idx:end_idx]
                else:
                    # Read lines with offset
                    all_lines = []
                    async for line in f:
                        all_lines.append(line.rstrip())

                    start_idx = offset
                    end_idx = min(offset + lines, len(all_lines))
                    selected_lines = all_lines[start_idx:end_idx]
        except OSError as e:
            logger.error(f"Failed to read log file {file_path}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to read log file: {e}")

        return {
            "filename": filename,
            "lines": selected_lines,
            "total_lines": len(all_lines) if "all_lines" in locals() else 0,
            "offset": offset,
            "count": len(selected_lines),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading log {filename}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="read_container_logs",
    error_code_prefix="LOGS",
)
@router.get("/logs/container/{service}")
async def read_container_logs(
    service: str,
    lines: int = Query(100, ge=1, le=10000, description="Number of lines to read"),
    since: Optional[str] = Query(None, description="Duration like '1h', '30m', '1d'"),
    tail: bool = Query(True, description="Read from end of logs"),
):
    """Read logs from a Docker container"""
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
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=30
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise HTTPException(status_code=408, detail="Container log read timed out")

        if process.returncode != 0:
            raise HTTPException(
                status_code=500, detail=f"Failed to get container logs: {stderr.decode()}"
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
        logger.error(f"Error reading container logs for {service}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def parse_docker_log_line(line: str, service: str) -> Metadata:
    """Parse a Docker log line and extract structured information"""
    parsed = {
        "raw": line.strip(),
        "service": service,
        "timestamp": "",
        "level": "INFO",
        "message": line.strip(),
    }

    try:
        # Docker log format: 2024-01-01T12:00:00.000000000Z message
        if line.startswith("20") and "T" in line[:25]:
            parts = line.split(" ", 1)
            if len(parts) >= 2:
                parsed["timestamp"] = parts[0]
                message = parts[1]

                # Extract log level from message
                message_upper = message.upper()
                for level in ["CRITICAL", "ERROR", "WARN", "WARNING", "INFO", "DEBUG"]:
                    if level in message_upper:
                        parsed["level"] = "WARNING" if level == "WARN" else level
                        break

                parsed["message"] = message

        # Try to parse JSON logs
        if parsed["message"].strip().startswith("{"):
            try:
                json_data = json.loads(parsed["message"])
                if "level" in json_data:
                    parsed["level"] = json_data["level"].upper()
                if "message" in json_data:
                    parsed["message"] = json_data["message"]
                if "timestamp" in json_data:
                    parsed["timestamp"] = json_data["timestamp"]
            except json.JSONDecodeError:
                # JSON parsing failed - message is plain text, not JSON
                logger.debug("Log line is plain text, not JSON format")

    except Exception as e:
        logger.debug(f"Failed to parse Docker log line: {e}")

    return parsed


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_unified_logs",
    error_code_prefix="LOGS",
)
@router.get("/logs/unified")
async def get_unified_logs(
    lines: int = Query(
        100, ge=1, le=1000, description="Total number of lines to return"
    ),
    level: Optional[str] = Query(None, description="Filter by log level"),
    sources: Optional[str] = Query(None, description="Comma-separated list of sources"),
):
    """Get unified logs from all sources, merged by timestamp"""
    try:
        all_logs = []

        # Parse sources filter
        source_filter = set()
        if sources:
            source_filter = set(sources.split(","))

        # Get file logs
        log_dir_exists = await asyncio.to_thread(LOG_DIR.exists)
        if log_dir_exists:
            log_files = await asyncio.to_thread(list, LOG_DIR.glob("*.log"))
            for file_path in log_files:
                file_name = file_path.stem  # Remove .log extension
                if source_filter and file_name not in source_filter:
                    continue

                try:
                    # Read last portion of file
                    async with aiofiles.open(file_path, "r") as f:
                        content = await f.read()
                        file_lines = content.splitlines()
                        for line in file_lines[-50:]:  # Get recent lines from each file
                            if line.strip():
                                parsed = parse_file_log_line(line.strip(), file_name)
                                if (
                                    level
                                    and parsed.get("level", "").upper() != level.upper()
                                ):
                                    continue
                                parsed["source_type"] = "file"
                                all_logs.append(parsed)
                except Exception as e:
                    logger.debug(f"Error reading file log {file_path}: {e}")

        # Get container logs
        for service, container_name in CONTAINER_LOGS.items():
            if source_filter and service not in source_filter:
                continue

            try:
                process = await asyncio.create_subprocess_exec(
                    "docker", "logs", container_name, "--timestamps", "--tail=50",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), timeout=10
                    )
                    if process.returncode == 0:
                        for line in stdout.decode().split("\n"):
                            if line.strip():
                                parsed = parse_docker_log_line(line, service)
                                if (
                                    level
                                    and parsed.get("level", "").upper() != level.upper()
                                ):
                                    continue
                                parsed["source_type"] = "container"
                                all_logs.append(parsed)
                except asyncio.TimeoutError:
                    logger.debug(f"Timeout getting container logs for {service}")
            except Exception as e:
                logger.debug(f"Error getting container logs for {service}: {e}")

        # Sort by timestamp (newest first) and limit
        all_logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        return {
            "logs": all_logs[:lines],
            "total_count": len(all_logs),
            "sources_included": list(set(log.get("service", "") for log in all_logs)),
        }

    except Exception as e:
        logger.error(f"Error getting unified logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def parse_file_log_line(line: str, source: str) -> Metadata:
    """Parse a file log line and extract structured information"""
    parsed = {
        "raw": line,
        "service": source,
        "timestamp": "",
        "level": "INFO",
        "message": line,
    }

    try:
        # Try to extract timestamp and level from common log formats
        # Format: 2024-01-01 12:00:00,000 [logger] LEVEL: message
        parts = line.split(" ", 3)
        if len(parts) >= 3:
            # Check if first part looks like a date
            if parts[0] and len(parts[0]) >= 10 and "-" in parts[0]:
                parsed["timestamp"] = (
                    f"{parts[0]} {parts[1]}" if len(parts) > 1 else parts[0]
                )

                # Look for log level
                for level in ["CRITICAL", "ERROR", "WARN", "WARNING", "INFO", "DEBUG"]:
                    if level in line.upper():
                        parsed["level"] = "WARNING" if level == "WARN" else level
                        break
    except Exception as e:
        logger.debug(f"Failed to parse general log line: {e}")

    return parsed


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="stream_log",
    error_code_prefix="LOGS",
)
@router.get("/logs/stream/{filename}")
async def stream_log(filename: str):
    """Stream log file content"""
    try:
        file_path = LOG_DIR / filename
        file_exists = await asyncio.to_thread(file_path.exists)
        is_file = await asyncio.to_thread(file_path.is_file) if file_exists else False
        if not file_exists or not is_file:
            raise HTTPException(status_code=404, detail="Log file not found")

        # Security check
        resolved_path = await asyncio.to_thread(file_path.resolve)
        resolved_log_dir = await asyncio.to_thread(LOG_DIR.resolve)
        if not str(resolved_path).startswith(str(resolved_log_dir)):
            raise HTTPException(status_code=403, detail="Access denied")

        async def generate():
            try:
                async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                    async for line in f:
                        yield line
            except OSError as e:
                logger.error(f"Failed to stream log file {file_path}: {e}")
                # Yield error message to client and stop
                return

        return StreamingResponse(generate(), media_type="text/plain")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error streaming log {filename}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="tail_log",
    error_code_prefix="LOGS",
)
@router.websocket("/logs/tail/{filename}")
async def tail_log(websocket: WebSocket, filename: str):
    """WebSocket endpoint to tail log file in real-time"""
    await websocket.accept()

    try:
        file_path = LOG_DIR / filename
        file_exists = await asyncio.to_thread(file_path.exists)
        is_file = await asyncio.to_thread(file_path.is_file) if file_exists else False
        if not file_exists or not is_file:
            await websocket.send_json({"error": "Log file not found"})
            await websocket.close()
            return

        # Security check
        resolved_path = await asyncio.to_thread(file_path.resolve)
        resolved_log_dir = await asyncio.to_thread(LOG_DIR.resolve)
        if not str(resolved_path).startswith(str(resolved_log_dir)):
            await websocket.send_json({"error": "Access denied"})
            await websocket.close()
            return

        # Start tailing the file
        try:
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
                        await asyncio.sleep(0.1)
        except OSError as e:
            logger.error(f"Failed to tail log file {file_path}: {e}")
            await websocket.send_json({"error": f"Failed to read log file: {e}"})
            return

    except Exception as e:
        logger.error(f"WebSocket error for {filename}: {e}")
        try:
            await websocket.send_json({"error": str(e)})
        except Exception as send_err:
            logger.debug(f"Failed to send error to WebSocket: {send_err}")
    finally:
        try:
            await websocket.close()
        except Exception as close_err:
            logger.debug(f"Failed to close WebSocket: {close_err}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_logs",
    error_code_prefix="LOGS",
)
@router.get("/logs/search")
async def search_logs(
    query: str = Query(..., description="Search query"),
    filename: Optional[str] = Query(None, description="Specific file to search"),
    case_sensitive: bool = Query(False, description="Case sensitive search"),
    max_results: int = Query(100, description="Maximum results"),
):
    """Search across log files"""
    try:
        results = []
        files_to_search = []

        if filename:
            file_path = LOG_DIR / filename
            file_exists = await asyncio.to_thread(file_path.exists)
            if file_exists:
                files_to_search.append(file_path)
        else:
            files_to_search = await asyncio.to_thread(list, LOG_DIR.glob("*.log"))

        for file_path in files_to_search:
            try:
                async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                    line_num = 0
                    async for line in f:
                        line_num += 1
                        line_content = line.rstrip()

                        # Check if line matches query
                        if case_sensitive:
                            if query in line_content:
                                results.append(
                                    {
                                        "file": file_path.name,
                                        "line": line_num,
                                        "content": line_content,
                                        "timestamp": datetime.now().isoformat(),
                                    }
                                )
                        else:
                            if query.lower() in line_content.lower():
                                results.append(
                                    {
                                        "file": file_path.name,
                                        "line": line_num,
                                        "content": line_content,
                                        "timestamp": datetime.now().isoformat(),
                                    }
                                )

                        if len(results) >= max_results:
                            break
            except OSError as e:
                logger.error(f"Failed to search log file {file_path}: {e}")
                continue

            if len(results) >= max_results:
                break

        return {
            "query": query,
            "results": results,
            "count": len(results),
            "truncated": len(results) >= max_results,
        }

    except Exception as e:
        logger.error(f"Error searching logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_log",
    error_code_prefix="LOGS",
)
@router.delete("/logs/clear/{filename}")
async def clear_log(filename: str):
    """Clear a log file (truncate to 0 bytes)"""
    try:
        file_path = LOG_DIR / filename
        file_exists = await asyncio.to_thread(file_path.exists)
        is_file = await asyncio.to_thread(file_path.is_file) if file_exists else False
        if not file_exists or not is_file:
            raise HTTPException(status_code=404, detail="Log file not found")

        # Security check
        resolved_path = await asyncio.to_thread(file_path.resolve)
        resolved_log_dir = await asyncio.to_thread(LOG_DIR.resolve)
        if not str(resolved_path).startswith(str(resolved_log_dir)):
            raise HTTPException(status_code=403, detail="Access denied")

        # Don't delete critical logs
        protected_logs = ["system.log", "backend.log", "frontend.log"]
        if filename in protected_logs:
            raise HTTPException(
                status_code=403, detail="Cannot clear protected log files"
            )

        # Truncate file
        async with aiofiles.open(file_path, "w") as f:
            await f.write("")

        return {"message": f"Log file {filename} cleared successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing log {filename}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
