# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
MCP Subprocess Manager

Manages skill.py MCP server subprocesses. Each active skill runs as
a persistent subprocess communicating via stdin/stdout MCP protocol.
"""

import asyncio
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

from autobot_shared.fire_and_forget import run_redis_write
from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from autobot_shared.ssot_config import config
from skills.mcp_trace import MCPSpan, new_span, write_span

logger = get_logger(__name__)

STARTUP_TIMEOUT: float = config.timeout.mcp_startup
CALL_TIMEOUT: float = config.timeout.mcp_call


@dataclass
class _MCPProcess:
    """Internal record for a running MCP skill subprocess."""

    name: str
    proc: asyncio.subprocess.Process
    tmpfile: str
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)


class MCPProcessManager:
    """Manages lifecycle of skill MCP server subprocesses.

    Each active skill.py runs as a persistent subprocess. Tool calls
    are proxied via JSON-RPC over stdin/stdout.
    """

    def __init__(self) -> None:
        """Initialize with empty process registry."""
        self._processes: Dict[str, _MCPProcess] = {}

    async def start(self, name: str, skill_py: str) -> int:
        """Write skill.py to a temp file and start it as an MCP subprocess.

        Returns the PID of the started process.
        Raises RuntimeError if the process fails to start or initialize.
        """
        if name in self._processes:
            await self.stop(name)

        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8")
        tmp.write(skill_py)
        tmp.close()

        proc = await self._spawn(name, tmp.name)
        entry = _MCPProcess(name=name, proc=proc, tmpfile=tmp.name)
        self._processes[name] = entry

        await self._handshake(name, entry)
        logger.info("MCP skill started: %s (pid=%d)", name, proc.pid)
        return proc.pid

    async def _spawn(self, name: str, script_path: str) -> asyncio.subprocess.Process:
        """Launch a Python subprocess for the skill script.

        Helper for start() — raises RuntimeError on launch failure.
        """
        try:
            return await asyncio.create_subprocess_exec(
                sys.executable,
                script_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except Exception as exc:
            os.unlink(script_path)
            raise RuntimeError(f"Skill '{name}' failed to start: {exc}") from exc

    async def _handshake(self, name: str, entry: _MCPProcess) -> None:
        """Send MCP initialize and await success response.

        Helper for start() — raises RuntimeError on timeout, EOF, or error.
        """
        try:
            await self._send(
                entry,
                {
                    "jsonrpc": "2.0",
                    "id": 0,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "autobot"},
                    },
                },
            )
            resp = await asyncio.wait_for(self._recv(entry), timeout=STARTUP_TIMEOUT)
            if "error" in resp:
                raise RuntimeError(f"Skill '{name}' failed to start: {resp['error']}")
        except asyncio.TimeoutError as exc:
            await self.stop(name)
            raise RuntimeError(f"Skill '{name}' failed to start: timeout") from exc
        except RuntimeError:
            await self.stop(name)
            raise

    def is_running(self, name: str) -> bool:
        """Return True if the named skill subprocess is alive."""
        entry = self._processes.get(name)
        if not entry:
            return False
        return entry.proc.returncode is None

    async def list_tools(self, name: str) -> List[Dict[str, Any]]:
        """Call tools/list on the skill server and return tool descriptors."""
        entry = self._get_entry(name)
        async with entry._lock:
            await self._send(
                entry,
                {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            )
            resp = await asyncio.wait_for(self._recv(entry), timeout=CALL_TIMEOUT)
        return resp.get("result", {}).get("tools", [])

    async def call_tool(self, name: str, tool: str, args: Dict[str, Any]) -> Any:
        """Call a named tool on the skill server and return its result.

        Raises RuntimeError if the tool call returns an error.
        Each call produces an MCPSpan written to Redis fire-and-forget (Issue #4413).
        """
        entry = self._get_entry(name)
        span: MCPSpan = new_span(
            skill_name=name,
            tool_name=tool,
            input_params=args,
            pid=entry.proc.pid,
        )
        logger.debug("mcp_trace: starting trace_id=%s", span.trace_id)

        result = None
        error_str: str | None = None
        try:
            async with entry._lock:
                await self._send(
                    entry,
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {"name": tool, "arguments": args},
                    },
                )
                resp = await asyncio.wait_for(self._recv(entry), timeout=CALL_TIMEOUT)
            if "error" in resp:
                error_str = str(resp["error"])
                raise RuntimeError(f"Tool call failed: {resp['error']}")
            result = resp.get("result")
            return result
        except RuntimeError:
            raise
        except Exception as exc:
            error_str = str(exc)
            raise
        finally:
            span.ended_at = time.time()
            span.output = result if isinstance(result, dict) else ({"value": result} if result is not None else None)
            span.error = error_str
            run_redis_write(write_span(span), label="mcp_trace")

    async def stop(self, name: str) -> None:
        """Terminate the skill subprocess and remove its temp file."""
        entry = self._processes.pop(name, None)
        if not entry:
            return
        try:
            entry.proc.terminate()
            await asyncio.wait_for(entry.proc.wait(), timeout=config.timeout.subprocess_short)
        except asyncio.TimeoutError:
            try:
                entry.proc.kill()
            except ProcessLookupError:
                pass
        except ProcessLookupError:
            pass  # Process already exited
        finally:
            if os.path.exists(entry.tmpfile):
                os.unlink(entry.tmpfile)
        logger.info("MCP skill stopped: %s", name)

    async def stop_all(self) -> None:
        """Stop all running skill subprocesses (called on shutdown)."""
        for name in list(self._processes.keys()):
            await self.stop(name)

    def _get_entry(self, name: str) -> _MCPProcess:
        """Return process entry or raise RuntimeError if not running."""
        if not self.is_running(name):
            raise RuntimeError(f"Skill '{name}' is not running")
        return self._processes[name]

    @staticmethod
    async def _send(entry: _MCPProcess, msg: Dict[str, Any]) -> None:
        """Write a JSON-RPC message to the subprocess stdin."""
        data = json.dumps(msg).encode() + b"\n"
        entry.proc.stdin.write(data)
        await entry.proc.stdin.drain()

    @staticmethod
    async def _recv(entry: _MCPProcess) -> Dict[str, Any]:
        """Read one JSON-RPC response line from subprocess stdout.

        Raises RuntimeError when the subprocess closes stdout (EOF).
        """
        line = await entry.proc.stdout.readline()
        if not line:
            raise RuntimeError(f"Skill '{entry.name}' subprocess closed stdout (EOF)")
        return json.loads(line.decode())


get_mcp_manager = lazy_singleton(MCPProcessManager)
