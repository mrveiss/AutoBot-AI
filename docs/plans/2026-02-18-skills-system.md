# AutoBot Skills System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a self-improving skills system where AutoBot detects capability gaps, generates MCP-based skill packages, manages approval via SLM, and promotes skills to the codebase.

**Architecture:** Skill packages are SKILL.md (behavioral guide) + skill.py (MCP server). They live in DB as Draft/Installed/Active, promoted to disk as Builtin. Skill repos (git/local/MCP) are registered and synced. A governance layer (FULL_AUTO / SEMI_AUTO / LOCKED) gates skill activation through SLM admin approval.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Pydantic v2, `mcp` PyPI package, asyncio subprocesses, Vue 3 + TypeScript, existing `BaseSkill`/`SkillRegistry` (keep for builtins), Redis for pub/sub notifications.

---

## Existing Code to Preserve

- `autobot-backend/skills/base_skill.py` — keep as-is (builtins still use it)
- `autobot-backend/skills/registry.py` — keep as-is
- `autobot-backend/skills/manager.py` — extend, don't replace
- `autobot-backend/api/skills.py` — extend with new endpoints
- `autobot-slm-frontend/src/views/SkillsView.vue` — extend with new tabs
- `autobot-slm-frontend/src/composables/useSkills.ts` — extend

---

## Phase 1: DB Models + Migration

**Files:**
- Create: `autobot-backend/skills/models.py`
- Create: `autobot-backend/skills/models_test.py`
- Modify: `autobot-backend/initialization/lifespan.py` (import + init tables)

### Task 1.1: Write failing model tests

```python
# autobot-backend/skills/models_test.py
import pytest
from skills.models import SkillPackage, SkillRepo, SkillApproval, GovernanceConfig
from skills.models import SkillState, RepoType, GovernanceMode, TrustLevel

def test_skill_package_defaults():
    pkg = SkillPackage(name="test-skill", skill_md="# Test", state=SkillState.DRAFT)
    assert pkg.state == SkillState.DRAFT
    assert pkg.skill_py is None
    assert pkg.repo_id is None

def test_skill_repo_types():
    for t in [RepoType.GIT, RepoType.LOCAL, RepoType.HTTP, RepoType.MCP]:
        repo = SkillRepo(name="r", url="x", repo_type=t)
        assert repo.repo_type == t

def test_governance_config_defaults():
    cfg = GovernanceConfig()
    assert cfg.mode == GovernanceMode.SEMI_AUTO

def test_skill_approval_pending():
    appr = SkillApproval(skill_id="abc", requested_by="autobot-self", reason="gap")
    assert appr.status == "pending"
```

Run: `cd autobot-backend && python -m pytest skills/models_test.py -v`
Expected: ImportError (models.py doesn't exist yet)

### Task 1.2: Implement DB models

Create `autobot-backend/skills/models.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Skills System DB Models

Persistent storage for skill packages, repos, approvals, and governance config.
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class SkillsBase(DeclarativeBase):
    pass


class SkillState(str, Enum):
    DRAFT = "draft"           # self-generated, not yet approved
    INSTALLED = "installed"   # pulled from repo, not yet enabled
    ACTIVE = "active"         # enabled, MCP server running
    BUILTIN = "builtin"       # promoted to disk, ships with AutoBot


class RepoType(str, Enum):
    GIT = "git"
    LOCAL = "local"
    HTTP = "http"
    MCP = "mcp"


class GovernanceMode(str, Enum):
    FULL_AUTO = "full_auto"   # no approval needed
    SEMI_AUTO = "semi_auto"   # AutoBot proposes, admin approves
    LOCKED = "locked"         # only admin-approved skills, no self-generation


class TrustLevel(str, Enum):
    TRUSTED = "trusted"       # no per-call logging
    MONITORED = "monitored"   # log every call
    SANDBOXED = "sandboxed"   # subprocess timeout + resource limits
    RESTRICTED = "restricted" # rate limited, specific agents only


class SkillPackage(SkillsBase):
    """A skill package: SKILL.md behavioral guide + optional skill.py MCP server."""
    __tablename__ = "skill_packages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, unique=True, index=True)
    version = Column(String, default="1.0.0")
    state = Column(String, nullable=False, default=SkillState.DRAFT)
    repo_id = Column(String, nullable=True)               # null = builtin or generated
    skill_md = Column(Text, nullable=False)               # full SKILL.md content
    skill_py = Column(Text, nullable=True)                # skill.py source
    manifest = Column(JSON, default=dict)                 # parsed frontmatter
    trust_level = Column(String, default=TrustLevel.MONITORED)
    mcp_pid = Column(Integer, nullable=True)              # running subprocess PID
    gap_reason = Column(Text, nullable=True)              # why AutoBot generated this
    requested_by = Column(String, default="autobot-self")
    created_at = Column(DateTime, default=datetime.utcnow)
    promoted_at = Column(DateTime, nullable=True)


class SkillRepo(SkillsBase):
    """A registered skill repository."""
    __tablename__ = "skill_repos"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, unique=True)
    url = Column(String, nullable=False)
    repo_type = Column(String, nullable=False)
    auto_sync = Column(Boolean, default=False)
    sync_interval = Column(Integer, default=60)           # minutes
    last_synced = Column(DateTime, nullable=True)
    skill_count = Column(Integer, default=0)
    status = Column(String, default="active")             # active | error | syncing
    error_message = Column(Text, nullable=True)


class SkillApproval(SkillsBase):
    """Admin approval record for a skill."""
    __tablename__ = "skill_approvals"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    skill_id = Column(String, nullable=False, index=True)
    requested_by = Column(String, nullable=False)
    requested_at = Column(DateTime, default=datetime.utcnow)
    reason = Column(Text, nullable=False)
    status = Column(String, default="pending")            # pending|approved|rejected|modified
    reviewed_by = Column(String, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    restrictions = Column(JSON, default=dict)             # rate limits, allowed agents


class GovernanceConfig(SkillsBase):
    """Global skill governance configuration (single row)."""
    __tablename__ = "skill_governance"

    id = Column(Integer, primary_key=True, default=1)
    mode = Column(String, default=GovernanceMode.SEMI_AUTO)
    default_trust_level = Column(String, default=TrustLevel.MONITORED)
    gap_detection_enabled = Column(Boolean, default=True)
    self_generation_enabled = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String, nullable=True)
```

### Task 1.3: Run tests — should pass

Run: `cd autobot-backend && python -m pytest skills/models_test.py -v`
Expected: 4 PASSED

### Task 1.4: Wire tables into lifespan

In `autobot-backend/initialization/lifespan.py`, add after existing DB init:

```python
from skills.models import SkillsBase
from skills.db import get_skills_engine

async def _init_skills_tables() -> None:
    """Create skills system tables if not exist."""
    engine = get_skills_engine()
    async with engine.begin() as conn:
        await conn.run_sync(SkillsBase.metadata.create_all)
    logger.info("Skills tables initialized")
```

Create `autobot-backend/skills/db.py`:

```python
"""Skills DB engine — uses autobot_data.db (same as main backend)."""
import os
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

_engine: AsyncEngine | None = None

def get_skills_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        base = os.environ.get("AUTOBOT_BASE_DIR", "/opt/autobot")
        db_path = os.path.join(base, "data", "autobot_data.db")
        _engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    return _engine
```

### Task 1.5: Lint + commit

```bash
cd autobot-backend
ruff check skills/models.py skills/db.py skills/models_test.py
git add skills/models.py skills/db.py skills/models_test.py initialization/lifespan.py
git commit -m "feat(skills): Phase 1 - DB models for skill packages, repos, approvals (#TBD)"
```

---

## Phase 2: MCP Subprocess Manager

**Purpose:** Each active `skill.py` runs as a persistent MCP server subprocess. The manager starts/stops subprocesses and proxies tool calls.

**Files:**
- Create: `autobot-backend/skills/mcp_process.py`
- Create: `autobot-backend/skills/mcp_process_test.py`
- Add to requirements: `mcp>=1.0.0` (MCP Python SDK)

### Task 2.1: Add MCP dependency

```bash
# In autobot-backend/requirements.txt, add:
mcp>=1.0.0
```

### Task 2.2: Write failing MCP process tests

```python
# autobot-backend/skills/mcp_process_test.py
import pytest
import asyncio
from skills.mcp_process import MCPProcessManager

@pytest.mark.asyncio
async def test_start_stop_mcp_server():
    """A valid skill.py MCP server can be started and stopped."""
    skill_py = '''
from mcp.server import Server
from mcp.server.stdio import stdio_server

app = Server("test-skill")

@app.tool()
async def echo(message: str) -> str:
    """Echo a message."""
    return message

if __name__ == "__main__":
    import asyncio
    asyncio.run(stdio_server(app))
'''
    mgr = MCPProcessManager()
    pid = await mgr.start("test-skill", skill_py)
    assert pid > 0
    assert mgr.is_running("test-skill")
    tools = await mgr.list_tools("test-skill")
    assert any(t["name"] == "echo" for t in tools)
    result = await mgr.call_tool("test-skill", "echo", {"message": "hello"})
    assert result == "hello"
    await mgr.stop("test-skill")
    assert not mgr.is_running("test-skill")

@pytest.mark.asyncio
async def test_invalid_skill_py_raises():
    """A skill.py with syntax errors fails to start cleanly."""
    mgr = MCPProcessManager()
    with pytest.raises(RuntimeError, match="failed to start"):
        await mgr.start("bad-skill", "this is not python !!!")
```

Run: `cd autobot-backend && python -m pytest skills/mcp_process_test.py -v`
Expected: ImportError

### Task 2.3: Implement MCPProcessManager

Create `autobot-backend/skills/mcp_process.py`:

```python
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
import logging
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

STARTUP_TIMEOUT = 10.0   # seconds to wait for MCP server ready
CALL_TIMEOUT = 30.0      # seconds per tool call


@dataclass
class _MCPProcess:
    name: str
    proc: asyncio.subprocess.Process
    tmpfile: str                          # temp file containing skill.py
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class MCPProcessManager:
    """Manages lifecycle of skill MCP server subprocesses."""

    def __init__(self) -> None:
        self._processes: Dict[str, _MCPProcess] = {}

    async def start(self, name: str, skill_py: str) -> int:
        """Write skill.py to temp file and launch as MCP subprocess.

        Returns the PID of the started process.
        Raises RuntimeError if startup fails.
        """
        if name in self._processes:
            await self.stop(name)

        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        )
        tmp.write(skill_py)
        tmp.close()

        try:
            proc = await asyncio.create_subprocess_exec(
                "python", tmp.name,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except Exception as exc:
            os.unlink(tmp.name)
            raise RuntimeError(f"Skill '{name}' failed to start: {exc}") from exc

        # Send initialize request, wait for response
        entry = _MCPProcess(name=name, proc=proc, tmpfile=tmp.name)
        self._processes[name] = entry

        try:
            await self._send(entry, {"jsonrpc": "2.0", "id": 0,
                                      "method": "initialize",
                                      "params": {"protocolVersion": "2024-11-05",
                                                 "capabilities": {},
                                                 "clientInfo": {"name": "autobot"}}})
            resp = await asyncio.wait_for(self._recv(entry), timeout=STARTUP_TIMEOUT)
            if "error" in resp:
                raise RuntimeError(f"Skill '{name}' failed to start: {resp['error']}")
        except asyncio.TimeoutError:
            await self.stop(name)
            raise RuntimeError(f"Skill '{name}' failed to start: timeout")

        logger.info("MCP skill started: %s (pid=%d)", name, proc.pid)
        return proc.pid

    def is_running(self, name: str) -> bool:
        """Return True if the named skill subprocess is alive."""
        entry = self._processes.get(name)
        if not entry:
            return False
        return entry.proc.returncode is None

    async def list_tools(self, name: str) -> List[Dict[str, Any]]:
        """Call tools/list on the skill server, return tool descriptors."""
        entry = self._get_entry(name)
        async with entry._lock:
            await self._send(entry, {"jsonrpc": "2.0", "id": 1,
                                      "method": "tools/list", "params": {}})
            resp = await asyncio.wait_for(self._recv(entry), timeout=CALL_TIMEOUT)
        return resp.get("result", {}).get("tools", [])

    async def call_tool(
        self, name: str, tool: str, args: Dict[str, Any]
    ) -> Any:
        """Call a tool on the skill server and return its result."""
        entry = self._get_entry(name)
        async with entry._lock:
            await self._send(entry, {
                "jsonrpc": "2.0", "id": 2,
                "method": "tools/call",
                "params": {"name": tool, "arguments": args},
            })
            resp = await asyncio.wait_for(self._recv(entry), timeout=CALL_TIMEOUT)
        if "error" in resp:
            raise RuntimeError(f"Tool call failed: {resp['error']}")
        return resp.get("result")

    async def stop(self, name: str) -> None:
        """Terminate the skill subprocess and clean up."""
        entry = self._processes.pop(name, None)
        if not entry:
            return
        try:
            entry.proc.terminate()
            await asyncio.wait_for(entry.proc.wait(), timeout=5.0)
        except (asyncio.TimeoutError, ProcessLookupError):
            entry.proc.kill()
        finally:
            if os.path.exists(entry.tmpfile):
                os.unlink(entry.tmpfile)
        logger.info("MCP skill stopped: %s", name)

    async def stop_all(self) -> None:
        """Stop all running skill subprocesses (called on shutdown)."""
        for name in list(self._processes.keys()):
            await self.stop(name)

    def _get_entry(self, name: str) -> _MCPProcess:
        """Get process entry or raise if not running."""
        if not self.is_running(name):
            raise RuntimeError(f"Skill '{name}' is not running")
        return self._processes[name]

    @staticmethod
    async def _send(entry: _MCPProcess, msg: Dict[str, Any]) -> None:
        """Write JSON-RPC message to subprocess stdin."""
        data = json.dumps(msg).encode() + b"\n"
        entry.proc.stdin.write(data)
        await entry.proc.stdin.drain()

    @staticmethod
    async def _recv(entry: _MCPProcess) -> Dict[str, Any]:
        """Read one JSON-RPC response from subprocess stdout."""
        line = await entry.proc.stdout.readline()
        return json.loads(line.decode())


# Module-level singleton
_manager: Optional[MCPProcessManager] = None


def get_mcp_manager() -> MCPProcessManager:
    """Get the singleton MCPProcessManager."""
    global _manager
    if _manager is None:
        _manager = MCPProcessManager()
    return _manager
```

### Task 2.4: Run tests

Run: `cd autobot-backend && python -m pytest skills/mcp_process_test.py -v`
Expected: 2 PASSED

### Task 2.5: Lint + commit

```bash
ruff check skills/mcp_process.py skills/mcp_process_test.py
git add skills/mcp_process.py skills/mcp_process_test.py requirements.txt
git commit -m "feat(skills): Phase 2 - MCP subprocess manager (#TBD)"
```

---

## Phase 3: Skill Repo Sync Engine

**Purpose:** Pull skill packages from git/local/HTTP/MCP repos into DB as `INSTALLED` state.

**Files:**
- Create: `autobot-backend/skills/sync/git_sync.py`
- Create: `autobot-backend/skills/sync/mcp_sync.py`
- Create: `autobot-backend/skills/sync/local_sync.py`
- Create: `autobot-backend/skills/sync/base_sync.py`
- Create: `autobot-backend/skills/sync/__init__.py`
- Create: `autobot-backend/skills/sync/sync_test.py`

### Task 3.1: Write failing sync tests

```python
# autobot-backend/skills/sync/sync_test.py
import os, pytest, tempfile, textwrap
from skills.sync.local_sync import LocalDirSync
from skills.models import SkillState

SAMPLE_SKILL_MD = textwrap.dedent("""\
    ---
    name: sample-skill
    version: 1.0.0
    description: A sample skill for testing
    tools: [do_thing]
    ---
    # Sample Skill
    Do a thing.
""")

@pytest.mark.asyncio
async def test_local_sync_discovers_skills():
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = os.path.join(tmpdir, "sample-skill")
        os.makedirs(skill_dir)
        with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
            f.write(SAMPLE_SKILL_MD)
        sync = LocalDirSync(tmpdir)
        packages = await sync.discover()
        assert len(packages) == 1
        assert packages[0]["name"] == "sample-skill"
        assert packages[0]["state"] == SkillState.INSTALLED
        assert "do_thing" in packages[0]["manifest"]["tools"]
```

Run: `cd autobot-backend && python -m pytest skills/sync/sync_test.py -v`
Expected: ImportError

### Task 3.2: Implement base + local sync

Create `autobot-backend/skills/sync/base_sync.py`:

```python
"""Base sync interface for skill repos."""
from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseRepoSync(ABC):
    """Abstract base for all repo sync implementations."""

    @abstractmethod
    async def discover(self) -> List[Dict[str, Any]]:
        """Return list of skill package dicts found in this repo."""

    @staticmethod
    def _parse_skill_md(content: str) -> Dict[str, Any]:
        """Parse SKILL.md frontmatter into manifest dict."""
        import re
        import yaml
        match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if not match:
            return {}
        try:
            return yaml.safe_load(match.group(1)) or {}
        except Exception:
            return {}
```

Create `autobot-backend/skills/sync/local_sync.py`:

```python
"""Local directory skill repo sync."""
import os
from typing import Any, Dict, List
from skills.models import SkillState
from skills.sync.base_sync import BaseRepoSync


class LocalDirSync(BaseRepoSync):
    """Sync skills from a local directory tree."""

    def __init__(self, path: str) -> None:
        self.path = path

    async def discover(self) -> List[Dict[str, Any]]:
        """Scan path for directories containing SKILL.md."""
        packages = []
        for entry in os.scandir(self.path):
            if not entry.is_dir():
                continue
            skill_md_path = os.path.join(entry.path, "SKILL.md")
            if not os.path.exists(skill_md_path):
                continue
            with open(skill_md_path, encoding="utf-8") as f:
                skill_md = f.read()
            skill_py_path = os.path.join(entry.path, "skill.py")
            skill_py = None
            if os.path.exists(skill_py_path):
                with open(skill_py_path, encoding="utf-8") as f:
                    skill_py = f.read()
            manifest = self._parse_skill_md(skill_md)
            packages.append({
                "name": manifest.get("name", entry.name),
                "version": manifest.get("version", "1.0.0"),
                "state": SkillState.INSTALLED,
                "skill_md": skill_md,
                "skill_py": skill_py,
                "manifest": manifest,
            })
        return packages
```

Create `autobot-backend/skills/sync/mcp_sync.py`:

```python
"""MCP server skill repo sync — wraps remote MCP tools as skill packages."""
import logging
from typing import Any, Dict, List
from skills.models import SkillState
from skills.sync.base_sync import BaseRepoSync
from skills.mcp_process import MCPProcessManager

logger = logging.getLogger(__name__)
_SKILL_MD_TEMPLATE = """\
---
name: {name}
version: 1.0.0
description: {description}
tools: {tools}
category: remote-mcp
---

# {name}

Remote MCP tool from {server_url}.

## Available Tools
{tool_list}
"""


class MCPClientSync(BaseRepoSync):
    """Sync skills from a remote MCP server by calling tools/list."""

    def __init__(self, server_url: str) -> None:
        self.server_url = server_url

    async def discover(self) -> List[Dict[str, Any]]:
        """Connect to MCP server, list tools, wrap as skill packages."""
        try:
            tools = await self._fetch_tools()
        except Exception as exc:
            logger.error("MCP sync failed for %s: %s", self.server_url, exc)
            return []
        return [self._tool_to_package(tool) for tool in tools]

    async def _fetch_tools(self) -> List[Dict[str, Any]]:
        """Fetch tool list from remote MCP server via HTTP."""
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.server_url}/rpc",
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                return data.get("result", {}).get("tools", [])

    def _tool_to_package(self, tool: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a remote MCP tool descriptor to a local skill package dict."""
        name = tool.get("name", "unknown")
        desc = tool.get("description", "")
        skill_md = _SKILL_MD_TEMPLATE.format(
            name=name, description=desc, tools=[name],
            server_url=self.server_url, tool_list=f"- {name}: {desc}",
        )
        return {
            "name": name,
            "version": "1.0.0",
            "state": SkillState.INSTALLED,
            "skill_md": skill_md,
            "skill_py": None,            # no local executor — proxied to remote
            "manifest": {"name": name, "tools": [name], "remote_mcp": self.server_url},
        }
```

Create `autobot-backend/skills/sync/__init__.py`:

```python
from skills.sync.git_sync import GitRepoSync
from skills.sync.local_sync import LocalDirSync
from skills.sync.mcp_sync import MCPClientSync

__all__ = ["GitRepoSync", "LocalDirSync", "MCPClientSync"]
```

Create `autobot-backend/skills/sync/git_sync.py`:

```python
"""Git repo skill sync — clones/pulls then delegates to LocalDirSync."""
import asyncio
import logging
import os
import tempfile
from typing import Any, Dict, List

from skills.sync.base_sync import BaseRepoSync
from skills.sync.local_sync import LocalDirSync

logger = logging.getLogger(__name__)


class GitRepoSync(BaseRepoSync):
    """Sync skills from a git repository."""

    def __init__(self, url: str, branch: str = "main") -> None:
        self.url = url
        self.branch = branch

    async def discover(self) -> List[Dict[str, Any]]:
        """Clone/pull git repo then scan for skill directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            await self._clone(tmpdir)
            skills_dir = self._find_skills_dir(tmpdir)
            return await LocalDirSync(skills_dir).discover()

    async def _clone(self, dest: str) -> None:
        """Clone repo into dest directory."""
        proc = await asyncio.create_subprocess_exec(
            "git", "clone", "--depth=1", "--branch", self.branch, self.url, dest,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"git clone failed: {stderr.decode()}")

    @staticmethod
    def _find_skills_dir(repo_root: str) -> str:
        """Return skills/ subdir if it exists, else repo root."""
        skills_sub = os.path.join(repo_root, "skills")
        return skills_sub if os.path.isdir(skills_sub) else repo_root
```

### Task 3.3: Run tests

Run: `cd autobot-backend && python -m pytest skills/sync/sync_test.py -v`
Expected: 1 PASSED

### Task 3.4: Add pyyaml to requirements if not present

```bash
grep -q "pyyaml\|PyYAML" autobot-backend/requirements.txt || echo "pyyaml>=6.0" >> autobot-backend/requirements.txt
```

### Task 3.5: Lint + commit

```bash
ruff check skills/sync/
git add skills/sync/
git commit -m "feat(skills): Phase 3 - repo sync engine (git/local/MCP) (#TBD)"
```

---

## Phase 4: Skill Gap Detector

**Purpose:** Detect when AutoBot lacks a skill and trigger the generation pipeline.

**Files:**
- Create: `autobot-backend/skills/gap_detector.py`
- Create: `autobot-backend/skills/gap_detector_test.py`

### Task 4.1: Write failing gap detector tests

```python
# autobot-backend/skills/gap_detector_test.py
import pytest
from skills.gap_detector import SkillGapDetector, GapTrigger, GapResult

def test_explicit_trigger_from_agent_output():
    detector = SkillGapDetector(available_tools=["web_search", "scrape_url"])
    result = detector.analyze_agent_output(
        "I don't have a tool to parse PDF files. I cannot complete this task."
    )
    assert result is not None
    assert result.trigger == GapTrigger.EXPLICIT
    assert "pdf" in result.capability.lower()

def test_no_gap_when_tool_available():
    detector = SkillGapDetector(available_tools=["parse_pdf"])
    result = detector.analyze_agent_output("Let me parse that PDF for you.")
    assert result is None

def test_failed_call_trigger():
    detector = SkillGapDetector(available_tools=["web_search"])
    result = detector.analyze_failed_tool_call("parse_pdf", {"path": "doc.pdf"})
    assert result is not None
    assert result.trigger == GapTrigger.FAILED_CALL
    assert "parse_pdf" in result.capability
```

Run: `cd autobot-backend && python -m pytest skills/gap_detector_test.py -v`
Expected: ImportError

### Task 4.2: Implement gap detector

Create `autobot-backend/skills/gap_detector.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Skill Gap Detector

Identifies when AutoBot lacks a capability by monitoring agent outputs
and failed tool calls.
"""
import re
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_EXPLICIT_PATTERNS = [
    r"i don't have a tool (to|for) (.+?)[\.\n]",
    r"i cannot (.+?) because (i lack|there is no|no tool)",
    r"no skill (available|exists) (for|to) (.+?)[\.\n]",
    r"capability unavailable[:\s]+(.+?)[\.\n]",
    r"i need a? ?(.+?) skill to",
]


class GapTrigger(str, Enum):
    EXPLICIT = "explicit"       # agent said "I don't have a tool for..."
    FAILED_CALL = "failed_call" # tool_call resolved to no handler
    USER_HINT = "user_hint"     # user asked for capability not in any skill


@dataclass
class GapResult:
    trigger: GapTrigger
    capability: str             # human-readable description of missing capability
    context: Dict[str, Any]    # original event data for the generator


class SkillGapDetector:
    """Analyzes agent output and tool events to detect capability gaps."""

    def __init__(self, available_tools: List[str]) -> None:
        self.available_tools = set(available_tools)

    def analyze_agent_output(self, text: str) -> Optional[GapResult]:
        """Scan agent output text for explicit gap signals."""
        lower = text.lower()
        for pattern in _EXPLICIT_PATTERNS:
            match = re.search(pattern, lower)
            if match:
                capability = _extract_capability(match)
                return GapResult(
                    trigger=GapTrigger.EXPLICIT,
                    capability=capability,
                    context={"agent_output": text[:500]},
                )
        return None

    def analyze_failed_tool_call(
        self, tool_name: str, args: Dict[str, Any]
    ) -> Optional[GapResult]:
        """Detect gap when a requested tool doesn't exist."""
        if tool_name in self.available_tools:
            return None
        return GapResult(
            trigger=GapTrigger.FAILED_CALL,
            capability=f"tool named '{tool_name}' with args {list(args.keys())}",
            context={"tool_name": tool_name, "args": args},
        )

    def analyze_user_message(self, message: str) -> Optional[GapResult]:
        """Detect when user requests something no existing skill covers."""
        # Simple heuristic: action verbs with no matching tool
        action_patterns = [
            r"can you (.+?)\?",
            r"please (.+?) for me",
            r"i need you to (.+)",
        ]
        for pattern in action_patterns:
            match = re.search(pattern, message.lower())
            if match:
                action = match.group(1).strip()
                if not self._any_tool_matches(action):
                    return GapResult(
                        trigger=GapTrigger.USER_HINT,
                        capability=action,
                        context={"user_message": message},
                    )
        return None

    def _any_tool_matches(self, action: str) -> bool:
        """Check if action words appear in any available tool name."""
        words = set(action.split())
        return any(
            any(w in tool for w in words)
            for tool in self.available_tools
        )


def _extract_capability(match: re.Match) -> str:
    """Extract the capability description from a regex match."""
    groups = [g for g in match.groups() if g and len(g) > 3]
    return groups[-1].strip() if groups else match.group(0)
```

### Task 4.3: Run tests

Run: `cd autobot-backend && python -m pytest skills/gap_detector_test.py -v`
Expected: 3 PASSED

### Task 4.4: Lint + commit

```bash
ruff check skills/gap_detector.py skills/gap_detector_test.py
git add skills/gap_detector.py skills/gap_detector_test.py
git commit -m "feat(skills): Phase 4 - skill gap detector (#TBD)"
```

---

## Phase 5: Skill Generator + Validator

**Purpose:** LLM generates a new SKILL.md + skill.py for a detected gap. Validator spins up the MCP server and tests it before storing.

**Files:**
- Create: `autobot-backend/skills/generator.py`
- Create: `autobot-backend/skills/validator.py`
- Create: `autobot-backend/skills/generator_test.py`

### Task 5.1: Write failing generator tests

```python
# autobot-backend/skills/generator_test.py
import pytest
from unittest.mock import AsyncMock, patch
from skills.generator import SkillGenerator
from skills.validator import SkillValidator

@pytest.mark.asyncio
async def test_generator_returns_skill_package():
    mock_llm = AsyncMock()
    mock_llm.generate_structured.return_value = {
        "skill_md": "---\nname: pdf-parser\ntools: [parse_pdf]\n---\n# PDF Parser",
        "skill_py": "from mcp.server import Server\napp = Server('pdf-parser')"
    }
    gen = SkillGenerator(llm=mock_llm)
    pkg = await gen.generate("parse PDF documents")
    assert pkg["name"] == "pdf-parser"
    assert "parse_pdf" in pkg["skill_md"]

@pytest.mark.asyncio
async def test_validator_detects_syntax_error():
    validator = SkillValidator()
    result = await validator.validate(
        skill_md="---\nname: bad\ntools: [x]\n---\n# Bad",
        skill_py="this is not python !!!",
    )
    assert not result.valid
    assert "syntax" in result.errors[0].lower()
```

Run: `cd autobot-backend && python -m pytest skills/generator_test.py -v`
Expected: ImportError

### Task 5.2: Implement SkillGenerator

Create `autobot-backend/skills/generator.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Skill Generator

Uses the LLM to generate SKILL.md + skill.py for a detected capability gap.
Structured output ensures valid manifests every time.
"""
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an expert at building AutoBot skill packages.
A skill has two parts:
1. SKILL.md — YAML frontmatter with: name (kebab-case), version, description,
   tools (list of function names), triggers, tags, category.
   Followed by Markdown: when to use, workflow steps, limitations.
2. skill.py — A Python MCP server using the `mcp` library.
   Each tool listed in the manifest must be implemented as @app.tool().

Rules:
- name must be kebab-case
- skill.py must be runnable standalone: `python skill.py`
- Tools must have type-annotated parameters
- Keep skill.py under 100 lines
- Use only stdlib + mcp library (no other deps)
"""

_GENERATION_SCHEMA = {
    "type": "object",
    "properties": {
        "skill_md": {"type": "string"},
        "skill_py": {"type": "string"},
    },
    "required": ["skill_md", "skill_py"],
}


class SkillGenerator:
    """Generates SKILL.md + skill.py for a capability gap using the LLM."""

    def __init__(self, llm: Any = None) -> None:
        self._llm = llm or self._get_default_llm()

    async def generate(self, gap_description: str) -> Dict[str, Any]:
        """Generate a skill package for the described capability gap.

        Returns dict with name, skill_md, skill_py, manifest keys.
        """
        prompt = (
            f"Generate a skill package for this capability: {gap_description}\n\n"
            "Return JSON with 'skill_md' and 'skill_py' keys."
        )
        result = await self._llm.generate_structured(
            system=_SYSTEM_PROMPT,
            prompt=prompt,
            schema=_GENERATION_SCHEMA,
        )
        manifest = _parse_manifest(result["skill_md"])
        return {
            "name": manifest.get("name", "generated-skill"),
            "skill_md": result["skill_md"],
            "skill_py": result["skill_py"],
            "manifest": manifest,
            "gap_description": gap_description,
        }

    @staticmethod
    def _get_default_llm() -> Any:
        """Get the AutoBot LLM interface."""
        from llm_interface_pkg.interface import get_llm_interface
        return get_llm_interface()


def _parse_manifest(skill_md: str) -> Dict[str, Any]:
    """Parse YAML frontmatter from SKILL.md content."""
    import re
    import yaml
    match = re.match(r"^---\n(.*?)\n---", skill_md, re.DOTALL)
    if not match:
        return {}
    try:
        return yaml.safe_load(match.group(1)) or {}
    except Exception:
        return {}
```

### Task 5.3: Implement SkillValidator

Create `autobot-backend/skills/validator.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Skill Validator

Validates a generated skill package before storing as a draft.
Checks: Python syntax, MCP server starts, tools callable.
"""
import ast
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from skills.mcp_process import MCPProcessManager

logger = logging.getLogger(__name__)

_TEST_TIMEOUT = 15.0


@dataclass
class ValidationResult:
    valid: bool
    errors: List[str] = field(default_factory=list)
    tools_found: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


class SkillValidator:
    """Validates skill packages by checking syntax and running the MCP server."""

    async def validate(
        self, skill_md: str, skill_py: Optional[str] = None
    ) -> ValidationResult:
        """Run all validation checks. Returns ValidationResult."""
        errors = []
        tools_found = []

        errors.extend(_check_manifest(skill_md))
        if skill_py:
            errors.extend(_check_python_syntax(skill_py))
            if not errors:
                mcp_errors, tools_found = await self._check_mcp_server(skill_py)
                errors.extend(mcp_errors)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            tools_found=tools_found,
        )

    @staticmethod
    async def _check_mcp_server(
        skill_py: str,
    ) -> tuple[List[str], List[str]]:
        """Start MCP server, list tools, return (errors, tool_names)."""
        mgr = MCPProcessManager()
        errors = []
        tools = []
        try:
            await mgr.start("_validation_tmp", skill_py)
            tool_list = await mgr.list_tools("_validation_tmp")
            tools = [t["name"] for t in tool_list]
            if not tools:
                errors.append("MCP server started but no tools declared")
        except RuntimeError as exc:
            errors.append(f"MCP server failed to start: {exc}")
        finally:
            await mgr.stop("_validation_tmp")
        return errors, tools


def _check_manifest(skill_md: str) -> List[str]:
    """Validate SKILL.md has required frontmatter fields."""
    import re, yaml
    errors = []
    match = re.match(r"^---\n(.*?)\n---", skill_md, re.DOTALL)
    if not match:
        errors.append("SKILL.md missing YAML frontmatter (--- block)")
        return errors
    try:
        manifest = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        errors.append(f"Invalid YAML frontmatter: {exc}")
        return errors
    for field_name in ("name", "description", "tools"):
        if not manifest.get(field_name):
            errors.append(f"Manifest missing required field: {field_name}")
    return errors


def _check_python_syntax(skill_py: str) -> List[str]:
    """Check skill.py for syntax errors."""
    try:
        ast.parse(skill_py)
        return []
    except SyntaxError as exc:
        return [f"syntax error in skill.py at line {exc.lineno}: {exc.msg}"]
```

### Task 5.4: Run tests

Run: `cd autobot-backend && python -m pytest skills/generator_test.py -v`
Expected: 2 PASSED

### Task 5.5: Lint + commit

```bash
ruff check skills/generator.py skills/validator.py skills/generator_test.py
git add skills/generator.py skills/validator.py skills/generator_test.py
git commit -m "feat(skills): Phase 5 - skill generator + validator (#TBD)"
```

---

## Phase 6: Governance Layer + Skill Promoter

**Purpose:** Enforce FULL_AUTO/SEMI_AUTO/LOCKED modes. Handle approval workflow. Promote drafts to disk.

**Files:**
- Create: `autobot-backend/skills/governance.py`
- Create: `autobot-backend/skills/promoter.py`
- Create: `autobot-backend/skills/governance_test.py`

### Task 6.1: Write failing governance tests

```python
# autobot-backend/skills/governance_test.py
import pytest
from skills.governance import GovernanceEngine, GovernanceMode

@pytest.mark.asyncio
async def test_full_auto_skips_approval():
    engine = GovernanceEngine(mode=GovernanceMode.FULL_AUTO)
    result = await engine.request_activation("test-skill", "autobot-self", "gap")
    assert result.approved
    assert result.requires_human_review is False

@pytest.mark.asyncio
async def test_semi_auto_requires_review():
    engine = GovernanceEngine(mode=GovernanceMode.SEMI_AUTO)
    result = await engine.request_activation("test-skill", "autobot-self", "gap")
    assert not result.approved
    assert result.requires_human_review is True
    assert result.approval_id is not None

@pytest.mark.asyncio
async def test_locked_blocks_self_generation():
    engine = GovernanceEngine(mode=GovernanceMode.LOCKED)
    result = await engine.request_activation("test-skill", "autobot-self", "gap")
    assert not result.approved
    assert result.requires_human_review is False
    assert "locked" in result.reason.lower()
```

Run: `cd autobot-backend && python -m pytest skills/governance_test.py -v`
Expected: ImportError

### Task 6.2: Implement governance engine

Create `autobot-backend/skills/governance.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Skill Governance Engine

Enforces FULL_AUTO / SEMI_AUTO / LOCKED modes for skill activation.
Creates approval records and notifies SLM admin via Redis pub/sub.
"""
import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from skills.models import GovernanceMode, TrustLevel

logger = logging.getLogger(__name__)
REDIS_APPROVAL_CHANNEL = "skills:approvals:pending"


@dataclass
class ActivationResult:
    approved: bool
    requires_human_review: bool
    approval_id: Optional[str] = None
    reason: str = ""
    trust_level: TrustLevel = TrustLevel.MONITORED


class GovernanceEngine:
    """Enforces skill activation governance policy."""

    def __init__(
        self,
        mode: GovernanceMode = GovernanceMode.SEMI_AUTO,
        default_trust: TrustLevel = TrustLevel.MONITORED,
    ) -> None:
        self.mode = mode
        self.default_trust = default_trust

    async def request_activation(
        self,
        skill_name: str,
        requested_by: str,
        reason: str,
    ) -> ActivationResult:
        """Process an activation request under the current governance mode."""
        if self.mode == GovernanceMode.LOCKED:
            return _locked_result()
        if self.mode == GovernanceMode.FULL_AUTO:
            return ActivationResult(
                approved=True,
                requires_human_review=False,
                reason="full_auto mode",
                trust_level=self.default_trust,
            )
        # SEMI_AUTO: create pending approval
        approval_id = str(uuid.uuid4())
        await self._notify_admin(skill_name, approval_id, requested_by, reason)
        return ActivationResult(
            approved=False,
            requires_human_review=True,
            approval_id=approval_id,
            reason="pending admin approval",
        )

    async def approve(
        self,
        approval_id: str,
        admin_id: str,
        trust_level: TrustLevel = TrustLevel.MONITORED,
        notes: str = "",
    ) -> ActivationResult:
        """Admin approves a pending skill activation."""
        logger.info("Skill approved by %s: approval=%s", admin_id, approval_id)
        return ActivationResult(
            approved=True,
            requires_human_review=False,
            approval_id=approval_id,
            reason=f"approved by {admin_id}",
            trust_level=trust_level,
        )

    @staticmethod
    async def _notify_admin(
        skill_name: str, approval_id: str, requested_by: str, reason: str
    ) -> None:
        """Publish pending approval to Redis for SLM dashboard notification."""
        try:
            from autobot_shared.redis_client import get_redis_client
            import json
            redis = get_redis_client(async_client=True, database="main")
            await redis.publish(REDIS_APPROVAL_CHANNEL, json.dumps({
                "skill_name": skill_name,
                "approval_id": approval_id,
                "requested_by": requested_by,
                "reason": reason,
            }))
        except Exception as exc:
            logger.warning("Failed to notify admin of skill approval: %s", exc)


def _locked_result() -> ActivationResult:
    """Return blocked result for LOCKED mode."""
    return ActivationResult(
        approved=False,
        requires_human_review=False,
        reason="system is in locked mode — only admin can activate skills",
    )
```

### Task 6.3: Implement Skill Promoter

Create `autobot-backend/skills/promoter.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Skill Promoter

Writes an approved draft skill to autobot-backend/skills/builtin/
and optionally commits it to git.
"""
import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class SkillPromoter:
    """Promotes a draft skill package to the codebase."""

    def __init__(self, skills_base_dir: Optional[str] = None) -> None:
        base = os.environ.get("AUTOBOT_BASE_DIR", "/opt/autobot")
        self.skills_dir = skills_base_dir or os.path.join(
            base, "autobot-backend", "skills", "builtin"
        )

    async def promote(
        self,
        name: str,
        skill_md: str,
        skill_py: Optional[str],
        issue_ref: str = "",
        auto_commit: bool = True,
    ) -> str:
        """Write skill to disk and optionally git commit.

        Returns path to the promoted skill directory.
        """
        dest = os.path.join(self.skills_dir, name)
        os.makedirs(dest, exist_ok=True)

        skill_md_path = os.path.join(dest, "SKILL.md")
        with open(skill_md_path, "w", encoding="utf-8") as f:
            f.write(skill_md)

        if skill_py:
            skill_py_path = os.path.join(dest, "skill.py")
            with open(skill_py_path, "w", encoding="utf-8") as f:
                f.write(skill_py)

        if auto_commit:
            await self._lint_and_commit(dest, name, issue_ref)

        logger.info("Skill promoted to disk: %s → %s", name, dest)
        return dest

    async def _lint_and_commit(
        self, dest: str, name: str, issue_ref: str
    ) -> None:
        """Run ruff check then git commit the promoted skill."""
        skill_py_path = os.path.join(dest, "skill.py")
        if os.path.exists(skill_py_path):
            await _run_cmd(["ruff", "check", "--fix", skill_py_path])

        ref = f" (#{issue_ref})" if issue_ref else ""
        msg = f"feat(skills): promote {name} skill to builtin{ref}"
        await _run_cmd(["git", "add", dest])
        await _run_cmd(["git", "commit", "-m", msg])
        logger.info("Committed promoted skill: %s", name)


async def _run_cmd(cmd: list) -> None:
    """Run a shell command, log output on failure."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.warning("Command %s failed: %s", cmd[0], stderr.decode())
```

### Task 6.4: Run governance tests

Run: `cd autobot-backend && python -m pytest skills/governance_test.py -v`
Expected: 3 PASSED

### Task 6.5: Lint + commit

```bash
ruff check skills/governance.py skills/promoter.py skills/governance_test.py
git add skills/governance.py skills/promoter.py skills/governance_test.py
git commit -m "feat(skills): Phase 6 - governance engine + skill promoter (#TBD)"
```

---

## Phase 7: Extended Skills API

**Extends** `autobot-backend/api/skills.py` and adds new router files.

**Files:**
- Modify: `autobot-backend/api/skills.py` (add repo/gap/approval endpoints)
- Create: `autobot-backend/api/skills_repos.py`
- Create: `autobot-backend/api/skills_governance.py`
- Modify: `autobot-backend/initialization/router_registry/feature_routers.py`

### Task 7.1: Add repo management endpoints

Create `autobot-backend/api/skills_repos.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Skills Repo API — CRUD + sync for skill repositories."""
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from skills.models import RepoType
from skills.sync import GitRepoSync, LocalDirSync, MCPClientSync
from skills.db import get_skills_engine
from skills.models import SkillRepo, SkillsBase

logger = logging.getLogger(__name__)
router = APIRouter()


class AddRepoRequest(BaseModel):
    name: str = Field(..., description="Human-readable repo name")
    url: str = Field(..., description="git URL, local path, HTTP URL, or MCP URL")
    repo_type: RepoType = Field(..., description="git | local | http | mcp")
    auto_sync: bool = Field(False)
    sync_interval: int = Field(60, description="Sync interval in minutes")


@router.post("/", summary="Register a skill repo")
async def add_repo(req: AddRepoRequest) -> Dict[str, Any]:
    """Register a new skill repository."""
    async with get_skills_engine().begin() as conn:
        repo = SkillRepo(
            name=req.name, url=req.url, repo_type=req.repo_type,
            auto_sync=req.auto_sync, sync_interval=req.sync_interval,
        )
        conn.add(repo)
    return {"id": repo.id, "name": repo.name, "status": "registered"}


@router.get("/", summary="List skill repos")
async def list_repos() -> List[Dict[str, Any]]:
    """Return all registered skill repos."""
    from sqlalchemy import select
    async with get_skills_engine().connect() as conn:
        rows = await conn.execute(select(SkillRepo))
        return [dict(r._mapping) for r in rows]


@router.post("/{repo_id}/sync", summary="Sync a repo now")
async def sync_repo(repo_id: str) -> Dict[str, Any]:
    """Pull latest skills from the repo and upsert into DB."""
    from sqlalchemy import select
    async with get_skills_engine().connect() as conn:
        row = await conn.execute(
            select(SkillRepo).where(SkillRepo.id == repo_id)
        )
        repo = row.fetchone()
    if not repo:
        raise HTTPException(404, f"Repo {repo_id} not found")
    packages = await _sync_packages(repo)
    return {"synced": len(packages), "repo": repo.name}


@router.get("/{repo_id}/browse", summary="Browse available skills in a repo")
async def browse_repo(repo_id: str) -> Dict[str, Any]:
    """List skills available in a repo without installing them."""
    from sqlalchemy import select
    async with get_skills_engine().connect() as conn:
        row = await conn.execute(
            select(SkillRepo).where(SkillRepo.id == repo_id)
        )
        repo = row.fetchone()
    if not repo:
        raise HTTPException(404, f"Repo {repo_id} not found")
    packages = await _sync_packages(repo)
    return {"packages": [p["name"] for p in packages], "count": len(packages)}


async def _sync_packages(repo: Any) -> List[Dict[str, Any]]:
    """Run the appropriate sync for the repo type."""
    syncs = {
        RepoType.GIT: lambda: GitRepoSync(repo.url).discover(),
        RepoType.LOCAL: lambda: LocalDirSync(repo.url).discover(),
        RepoType.MCP: lambda: MCPClientSync(repo.url).discover(),
    }
    syncer = syncs.get(repo.repo_type)
    if not syncer:
        return []
    return await syncer()
```

### Task 7.2: Add governance + gaps endpoints

Create `autobot-backend/api/skills_governance.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Skills Governance API — gaps, approvals, mode management."""
import logging
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from skills.models import GovernanceMode, TrustLevel
from skills.governance import GovernanceEngine
from skills.generator import SkillGenerator
from skills.validator import SkillValidator
from skills.promoter import SkillPromoter

logger = logging.getLogger(__name__)
router = APIRouter()


class GapRequest(BaseModel):
    task: str = Field(..., description="Description of what AutoBot tried to do")
    agent_output: str = Field("", description="Agent's output text if available")


class ApprovalDecision(BaseModel):
    approved: bool
    trust_level: TrustLevel = TrustLevel.MONITORED
    notes: str = ""


class ModeUpdate(BaseModel):
    mode: GovernanceMode


@router.post("/gaps", summary="Report a capability gap and trigger skill generation")
async def report_gap(req: GapRequest) -> Dict[str, Any]:
    """AutoBot reports it lacks a capability. Generator creates a draft skill."""
    gen = SkillGenerator()
    pkg = await gen.generate(req.task)
    validator = SkillValidator()
    result = await validator.validate(pkg["skill_md"], pkg.get("skill_py"))
    if not result.valid:
        return {"success": False, "errors": result.errors, "draft": pkg}
    # Store draft in DB
    from skills.db import get_skills_engine
    from skills.models import SkillPackage, SkillState
    from datetime import datetime
    async with get_skills_engine().begin() as conn:
        skill = SkillPackage(
            name=pkg["name"], skill_md=pkg["skill_md"],
            skill_py=pkg.get("skill_py"), manifest=pkg.get("manifest", {}),
            state=SkillState.DRAFT, gap_reason=req.task,
        )
        conn.add(skill)
    return {"success": True, "draft_id": skill.id, "name": pkg["name"],
            "tools_found": result.tools_found}


@router.get("/drafts", summary="List self-generated draft skills")
async def list_drafts() -> List[Dict[str, Any]]:
    """Return all draft skills awaiting review."""
    from sqlalchemy import select
    from skills.db import get_skills_engine
    from skills.models import SkillPackage, SkillState
    async with get_skills_engine().connect() as conn:
        rows = await conn.execute(
            select(SkillPackage).where(SkillPackage.state == SkillState.DRAFT)
        )
        return [dict(r._mapping) for r in rows]


@router.post("/drafts/{skill_id}/test", summary="Sandbox test a draft skill")
async def test_draft(skill_id: str) -> Dict[str, Any]:
    """Run validator against a draft skill."""
    from sqlalchemy import select
    from skills.db import get_skills_engine
    from skills.models import SkillPackage
    async with get_skills_engine().connect() as conn:
        row = await conn.execute(
            select(SkillPackage).where(SkillPackage.id == skill_id)
        )
        skill = row.fetchone()
    if not skill:
        raise HTTPException(404, "Draft not found")
    validator = SkillValidator()
    result = await validator.validate(skill.skill_md, skill.skill_py)
    return {"valid": result.valid, "errors": result.errors,
            "tools_found": result.tools_found}


@router.post("/drafts/{skill_id}/promote", summary="Promote draft to builtin")
async def promote_draft(skill_id: str) -> Dict[str, Any]:
    """Write draft skill to disk and commit to git."""
    from sqlalchemy import select
    from skills.db import get_skills_engine
    from skills.models import SkillPackage, SkillState
    from datetime import datetime
    async with get_skills_engine().connect() as conn:
        row = await conn.execute(
            select(SkillPackage).where(SkillPackage.id == skill_id)
        )
        skill = row.fetchone()
    if not skill:
        raise HTTPException(404, "Draft not found")
    promoter = SkillPromoter()
    path = await promoter.promote(skill.name, skill.skill_md, skill.skill_py)
    async with get_skills_engine().begin() as conn:
        from sqlalchemy import update
        await conn.execute(
            update(SkillPackage)
            .where(SkillPackage.id == skill_id)
            .values(state=SkillState.BUILTIN, promoted_at=datetime.utcnow())
        )
    return {"promoted": True, "path": path, "name": skill.name}


@router.get("/approvals", summary="List pending approvals")
async def list_approvals() -> List[Dict[str, Any]]:
    """Return all skills pending admin approval."""
    from sqlalchemy import select
    from skills.db import get_skills_engine
    from skills.models import SkillApproval
    async with get_skills_engine().connect() as conn:
        rows = await conn.execute(
            select(SkillApproval).where(SkillApproval.status == "pending")
        )
        return [dict(r._mapping) for r in rows]


@router.post("/approvals/{approval_id}", summary="Approve or reject a skill")
async def decide_approval(
    approval_id: str, decision: ApprovalDecision
) -> Dict[str, Any]:
    """Admin approves or rejects a pending skill activation."""
    from sqlalchemy import update, select
    from skills.db import get_skills_engine
    from skills.models import SkillApproval
    from datetime import datetime
    new_status = "approved" if decision.approved else "rejected"
    async with get_skills_engine().begin() as conn:
        await conn.execute(
            update(SkillApproval)
            .where(SkillApproval.id == approval_id)
            .values(status=new_status, notes=decision.notes,
                    reviewed_at=datetime.utcnow())
        )
    return {"approval_id": approval_id, "status": new_status}


@router.get("/governance", summary="Get current governance config")
async def get_governance() -> Dict[str, Any]:
    """Return current governance mode and settings."""
    from sqlalchemy import select
    from skills.db import get_skills_engine
    from skills.models import GovernanceConfig
    async with get_skills_engine().connect() as conn:
        row = await conn.execute(select(GovernanceConfig))
        cfg = row.fetchone()
    if not cfg:
        return {"mode": GovernanceMode.SEMI_AUTO, "gap_detection_enabled": True}
    return dict(cfg._mapping)


@router.put("/governance", summary="Update governance mode")
async def update_governance(update: ModeUpdate) -> Dict[str, Any]:
    """Set the global skill governance mode."""
    from sqlalchemy import update as sa_update
    from skills.db import get_skills_engine
    from skills.models import GovernanceConfig
    from datetime import datetime
    async with get_skills_engine().begin() as conn:
        await conn.execute(
            sa_update(GovernanceConfig)
            .where(GovernanceConfig.id == 1)
            .values(mode=update.mode, updated_at=datetime.utcnow())
        )
    return {"mode": update.mode}
```

### Task 7.3: Register routers

In `autobot-backend/initialization/router_registry/feature_routers.py`, add:

```python
("backend.api.skills_repos",       "/skills/repos",       ["skills"], "skills-repos"),
("backend.api.skills_governance",  "/skills/governance",  ["skills"], "skills-governance"),
```

### Task 7.4: Lint + commit

```bash
ruff check api/skills_repos.py api/skills_governance.py
git add api/skills_repos.py api/skills_governance.py initialization/router_registry/feature_routers.py
git commit -m "feat(skills): Phase 7 - extended skills API (repos, gaps, approvals, governance) (#TBD)"
```

---

## Phase 8: SLM Skills Manager UI

**Extends** existing `SkillsView.vue` and `useSkills.ts` in `autobot-slm-frontend/`.

**Files:**
- Modify: `autobot-slm-frontend/src/views/SkillsView.vue` (add 3 new tabs)
- Modify: `autobot-slm-frontend/src/composables/useSkills.ts` (extend with new methods)
- Create: `autobot-slm-frontend/src/components/skills/ReposTab.vue`
- Create: `autobot-slm-frontend/src/components/skills/ApprovalsTab.vue`
- Create: `autobot-slm-frontend/src/components/skills/DraftsTab.vue`
- Create: `autobot-slm-frontend/src/components/skills/GovernanceModeSelector.vue`

### Task 8.1: Extend useSkills.ts composable

Add to `autobot-slm-frontend/src/composables/useSkills.ts` after existing exports:

```typescript
// --- Skill Repos ---

export interface SkillRepo {
  id: string
  name: string
  url: string
  repo_type: 'git' | 'local' | 'http' | 'mcp'
  skill_count: number
  status: string
  last_synced: string | null
}

export interface SkillApproval {
  id: string
  skill_id: string
  requested_by: string
  requested_at: string
  reason: string
  status: 'pending' | 'approved' | 'rejected'
  notes: string | null
}

export interface GovernanceConfig {
  mode: 'full_auto' | 'semi_auto' | 'locked'
  gap_detection_enabled: boolean
  default_trust_level: string
}

// Governance API base — note: hits main backend via SLM proxy
const SKILLS_GOVERNANCE_BASE = '/autobot-api/skills/governance'

export function useSkillGovernance() {
  const repos = ref<SkillRepo[]>([])
  const approvals = ref<SkillApproval[]>([])
  const drafts = ref<SkillPackage[]>([])  // reuse SkillInfo for draft shape
  const governanceConfig = ref<GovernanceConfig | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchRepos() {
    loading.value = true
    try {
      const { data } = await axios.get(`${SKILLS_GOVERNANCE_BASE}/repos`)
      repos.value = data
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch repos'
    } finally {
      loading.value = false
    }
  }

  async function addRepo(payload: Omit<SkillRepo, 'id' | 'skill_count' | 'status' | 'last_synced'>) {
    const { data } = await axios.post(`${SKILLS_GOVERNANCE_BASE}/repos`, payload)
    await fetchRepos()
    return data
  }

  async function syncRepo(repoId: string) {
    const { data } = await axios.post(`${SKILLS_GOVERNANCE_BASE}/repos/${repoId}/sync`)
    await fetchRepos()
    return data
  }

  async function fetchApprovals() {
    const { data } = await axios.get(`${SKILLS_GOVERNANCE_BASE}/approvals`)
    approvals.value = data
  }

  async function decideApproval(approvalId: string, approved: boolean, notes = '') {
    await axios.post(`${SKILLS_GOVERNANCE_BASE}/approvals/${approvalId}`, {
      approved, notes, trust_level: 'monitored'
    })
    await fetchApprovals()
  }

  async function fetchDrafts() {
    const { data } = await axios.get(`${SKILLS_GOVERNANCE_BASE}/drafts`)
    drafts.value = data
  }

  async function testDraft(skillId: string) {
    const { data } = await axios.post(`${SKILLS_GOVERNANCE_BASE}/drafts/${skillId}/test`)
    return data
  }

  async function promoteDraft(skillId: string) {
    const { data } = await axios.post(`${SKILLS_GOVERNANCE_BASE}/drafts/${skillId}/promote`)
    await fetchDrafts()
    return data
  }

  async function fetchGovernance() {
    const { data } = await axios.get(`${SKILLS_GOVERNANCE_BASE}/governance`)
    governanceConfig.value = data
  }

  async function setGovernanceMode(mode: GovernanceConfig['mode']) {
    await axios.put(`${SKILLS_GOVERNANCE_BASE}/governance`, { mode })
    await fetchGovernance()
  }

  return {
    repos: readonly(repos),
    approvals: readonly(approvals),
    drafts: readonly(drafts),
    governanceConfig: readonly(governanceConfig),
    loading: readonly(loading),
    error: readonly(error),
    fetchRepos, addRepo, syncRepo,
    fetchApprovals, decideApproval,
    fetchDrafts, testDraft, promoteDraft,
    fetchGovernance, setGovernanceMode,
  }
}
```

### Task 8.2: Create GovernanceModeSelector component

Create `autobot-slm-frontend/src/components/skills/GovernanceModeSelector.vue`:

```vue
<template>
  <div class="governance-mode-selector">
    <label class="mode-label">Governance Mode</label>
    <div class="mode-buttons">
      <button
        v-for="m in modes"
        :key="m.value"
        :class="['mode-btn', { active: modelValue === m.value }]"
        @click="$emit('update:modelValue', m.value)"
      >
        <span class="mode-icon">{{ m.icon }}</span>
        <span class="mode-name">{{ m.label }}</span>
      </button>
    </div>
    <p class="mode-desc">{{ currentMode?.description }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

type GovernanceMode = 'full_auto' | 'semi_auto' | 'locked'

const props = defineProps<{ modelValue: GovernanceMode }>()
defineEmits<{ 'update:modelValue': [value: GovernanceMode] }>()

const modes = [
  { value: 'full_auto' as GovernanceMode, label: 'Full Auto', icon: '⚡',
    description: 'AutoBot installs and activates skills without approval.' },
  { value: 'semi_auto' as GovernanceMode, label: 'Semi Auto', icon: '👤',
    description: 'AutoBot proposes skills — you approve before activation.' },
  { value: 'locked' as GovernanceMode, label: 'Locked', icon: '🔒',
    description: 'Only admin-approved skills run. No self-generation.' },
]

const currentMode = computed(() => modes.find(m => m.value === props.modelValue))
</script>
```

### Task 8.3: Create ApprovalsTab component

Create `autobot-slm-frontend/src/components/skills/ApprovalsTab.vue`:

```vue
<template>
  <div class="approvals-tab">
    <div v-if="approvals.length === 0" class="empty-state">
      No pending approvals
    </div>
    <div v-for="approval in approvals" :key="approval.id" class="approval-card">
      <div class="approval-header">
        <span class="approval-skill">{{ approval.skill_id }}</span>
        <span class="approval-by">Requested by: {{ approval.requested_by }}</span>
      </div>
      <p class="approval-reason">{{ approval.reason }}</p>
      <div class="approval-actions">
        <select v-model="trustLevels[approval.id]" class="trust-select">
          <option value="monitored">Monitored</option>
          <option value="trusted">Trusted</option>
          <option value="sandboxed">Sandboxed</option>
          <option value="restricted">Restricted</option>
        </select>
        <button class="btn-approve" @click="approve(approval.id)">Approve</button>
        <button class="btn-reject" @click="reject(approval.id)">Reject</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { SkillApproval } from '@/composables/useSkills'

const props = defineProps<{ approvals: SkillApproval[] }>()
const emit = defineEmits<{
  approve: [id: string, trustLevel: string]
  reject: [id: string]
}>()

const trustLevels = ref<Record<string, string>>({})

function approve(id: string) {
  emit('approve', id, trustLevels.value[id] || 'monitored')
}
function reject(id: string) {
  emit('reject', id)
}
</script>
```

### Task 8.4: Create ReposTab and DraftsTab components

Create `autobot-slm-frontend/src/components/skills/ReposTab.vue`:

```vue
<template>
  <div class="repos-tab">
    <div class="repos-toolbar">
      <button class="btn-add" @click="showAddModal = true">+ Add Repo</button>
    </div>
    <table class="repos-table">
      <thead>
        <tr><th>Name</th><th>Type</th><th>URL</th><th>Skills</th><th>Last Sync</th><th></th></tr>
      </thead>
      <tbody>
        <tr v-for="repo in repos" :key="repo.id">
          <td>{{ repo.name }}</td>
          <td><span :class="`badge badge-${repo.repo_type}`">{{ repo.repo_type }}</span></td>
          <td class="url-cell">{{ repo.url }}</td>
          <td>{{ repo.skill_count }}</td>
          <td>{{ repo.last_synced ? new Date(repo.last_synced).toLocaleString() : 'Never' }}</td>
          <td>
            <button class="btn-sync" @click="$emit('sync', repo.id)">Sync</button>
            <button class="btn-browse" @click="$emit('browse', repo.id)">Browse</button>
          </td>
        </tr>
      </tbody>
    </table>
    <!-- Add repo modal omitted for brevity — use existing modal pattern from app -->
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { SkillRepo } from '@/composables/useSkills'

defineProps<{ repos: SkillRepo[] }>()
defineEmits<{ sync: [id: string]; browse: [id: string] }>()
const showAddModal = ref(false)
</script>
```

Create `autobot-slm-frontend/src/components/skills/DraftsTab.vue`:

```vue
<template>
  <div class="drafts-tab">
    <div v-if="drafts.length === 0" class="empty-state">
      No draft skills. AutoBot will generate skills here when it detects capability gaps.
    </div>
    <div v-for="draft in drafts" :key="draft.id" class="draft-card">
      <div class="draft-header">
        <span class="draft-name">{{ draft.name }}</span>
        <span class="draft-reason">{{ draft.gap_reason }}</span>
      </div>
      <pre class="skill-md-preview">{{ draft.skill_md?.slice(0, 300) }}...</pre>
      <div class="draft-actions">
        <button class="btn-test" @click="$emit('test', draft.id)">Test Run</button>
        <button class="btn-promote" @click="$emit('promote', draft.id)">Promote to Builtin</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ drafts: any[] }>()
defineEmits<{ test: [id: string]; promote: [id: string] }>()
</script>
```

### Task 8.5: Update SkillsView.vue to add new tabs

In `autobot-slm-frontend/src/views/SkillsView.vue`, add the tab bar and wire the new components.

Add to `<script setup>`:

```typescript
import { useSkillGovernance } from '@/composables/useSkills'
import GovernanceModeSelector from '@/components/skills/GovernanceModeSelector.vue'
import ApprovalsTab from '@/components/skills/ApprovalsTab.vue'
import ReposTab from '@/components/skills/ReposTab.vue'
import DraftsTab from '@/components/skills/DraftsTab.vue'

const {
  repos, approvals, drafts, governanceConfig,
  fetchRepos, syncRepo, fetchApprovals, decideApproval,
  fetchDrafts, testDraft, promoteDraft, fetchGovernance, setGovernanceMode,
} = useSkillGovernance()

const activeTab = ref<'active' | 'approvals' | 'repos' | 'drafts'>('active')

onMounted(async () => {
  await Promise.all([fetchGovernance(), fetchApprovals(), fetchRepos(), fetchDrafts()])
})
```

Add to `<template>` above existing content:

```html
<div class="skills-header">
  <div class="tab-bar">
    <button :class="['tab', { active: activeTab === 'active' }]"
            @click="activeTab = 'active'">Active Skills</button>
    <button :class="['tab', { active: activeTab === 'approvals' }]"
            @click="activeTab = 'approvals'">
      Pending
      <span v-if="approvals.length" class="badge">{{ approvals.length }}</span>
    </button>
    <button :class="['tab', { active: activeTab === 'repos' }]"
            @click="activeTab = 'repos'">Repos</button>
    <button :class="['tab', { active: activeTab === 'drafts' }]"
            @click="activeTab = 'drafts'">Drafts</button>
  </div>
  <GovernanceModeSelector
    v-if="governanceConfig"
    :model-value="governanceConfig.mode"
    @update:model-value="setGovernanceMode"
  />
</div>

<ApprovalsTab
  v-if="activeTab === 'approvals'"
  :approvals="approvals"
  @approve="(id, trust) => decideApproval(id, true)"
  @reject="(id) => decideApproval(id, false)"
/>
<ReposTab
  v-if="activeTab === 'repos'"
  :repos="repos"
  @sync="syncRepo"
/>
<DraftsTab
  v-if="activeTab === 'drafts'"
  :drafts="drafts"
  @test="testDraft"
  @promote="promoteDraft"
/>
<!-- existing skills grid stays under activeTab === 'active' guard -->
```

### Task 8.6: Build check + lint

```bash
cd autobot-slm-frontend
npm run type-check
npm run lint
npm run build
```

Fix any TypeScript errors before committing.

### Task 8.7: Commit frontend

```bash
git add autobot-slm-frontend/src/
git commit -m "feat(skills): Phase 8 - SLM Skills Manager UI (repos, approvals, drafts, governance) (#TBD)"
```

---

## Phase 9: Create GitHub Issue + Wire Everything Together

### Task 9.1: Create tracking issue

```bash
gh issue create \
  --title "feat: AutoBot Self-Improving Skills System with MCP + SLM Governance" \
  --body "## Summary
Full skills system with MCP-based packages, skill repos, self-generation via gap detection, and SLM governance (FULL_AUTO/SEMI_AUTO/LOCKED).

## Phases
- [ ] Phase 1: DB Models
- [ ] Phase 2: MCP Subprocess Manager
- [ ] Phase 3: Repo Sync Engine
- [ ] Phase 4: Gap Detector
- [ ] Phase 5: Generator + Validator
- [ ] Phase 6: Governance + Promoter
- [ ] Phase 7: Extended API
- [ ] Phase 8: SLM Frontend

## Architecture
SKILL.md (behavioral guide) + skill.py (MCP server) per skill.
Lifecycle: Draft → Installed → Active → Builtin.
Repos: git | local | http | mcp.
Governance: full_auto | semi_auto | locked."
```

### Task 9.2: Update all commit messages with the issue number

Replace `#TBD` in all commits with the actual issue number:
```bash
# Note the issue number from the gh issue create output, then
# reference it in future commits and add to existing ones via
# git commit --amend (only if not yet pushed)
```

### Task 9.3: Integration smoke test

```bash
# Start the backend
sudo systemctl restart autobot-backend

# Wait for startup (~60s)
ssh autobot@172.16.168.19 'curl -sk https://172.16.168.20:8443/api/skills/governance'
# Expected: {"mode": "semi_auto", "gap_detection_enabled": true, ...}

ssh autobot@172.16.168.19 'curl -sk https://172.16.168.20:8443/api/skills/drafts'
# Expected: []

ssh autobot@172.16.168.19 'curl -sk -X POST https://172.16.168.20:8443/api/skills/repos \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"community\",\"url\":\"mcp://skills.example.com\",\"repo_type\":\"mcp\"}"'
# Expected: {"id": "...", "name": "community", "status": "registered"}
```

### Task 9.4: Deploy to fleet

```bash
cd autobot-slm-backend/ansible
ansible-playbook playbooks/deploy-full.yml --tags backend,frontend \
  -i inventory/production.yml -i inventory/slm-nodes.yml
```

### Task 9.5: Close issue with summary

```bash
gh issue comment <number> --body "## Completed
All 8 phases implemented. AutoBot can now:
- Register skill repos (git/local/http/mcp)
- Detect capability gaps from agent output + failed tool calls
- Generate SKILL.md + skill.py via LLM
- Validate generated skills in sandbox (MCP subprocess)
- Enforce governance (FULL_AUTO/SEMI_AUTO/LOCKED)
- Present pending approvals in SLM dashboard
- Promote approved skills to disk + git commit"

gh issue close <number>
```

---

## Quick Reference

### File Map

| File | Purpose |
|------|---------|
| `skills/models.py` | DB models: SkillPackage, SkillRepo, SkillApproval, GovernanceConfig |
| `skills/db.py` | SQLAlchemy async engine for skills tables |
| `skills/mcp_process.py` | MCPProcessManager — runs skill.py subprocesses |
| `skills/sync/git_sync.py` | Git repo → skill packages |
| `skills/sync/local_sync.py` | Local dir → skill packages |
| `skills/sync/mcp_sync.py` | Remote MCP server → skill packages |
| `skills/gap_detector.py` | Detects missing capabilities |
| `skills/generator.py` | LLM generates SKILL.md + skill.py |
| `skills/validator.py` | Syntax + MCP runtime validation |
| `skills/governance.py` | FULL_AUTO/SEMI_AUTO/LOCKED enforcement |
| `skills/promoter.py` | Write to disk + git commit |
| `api/skills_repos.py` | Repo CRUD + sync endpoints |
| `api/skills_governance.py` | Gaps, drafts, approvals, mode endpoints |
| `slm-frontend/.../useSkills.ts` | Extended composable with governance methods |
| `slm-frontend/.../ApprovalsTab.vue` | Pending approval review UI |
| `slm-frontend/.../ReposTab.vue` | Repo management UI |
| `slm-frontend/.../DraftsTab.vue` | Draft skill review + promote UI |
| `slm-frontend/.../GovernanceModeSelector.vue` | Mode switcher component |

### Test Commands

```bash
# Backend unit tests
cd autobot-backend
python -m pytest skills/ -v --tb=short

# Frontend type check
cd autobot-slm-frontend && npm run type-check

# Lint all changed files
cd autobot-backend && ruff check skills/ api/skills_repos.py api/skills_governance.py
```

### Key Decisions

- **Existing BaseSkill/SkillRegistry preserved** — builtins keep working unchanged
- **New skills use MCP** — skill.py is always an MCP server, not a BaseSkill subclass
- **SQLite for skill tables** — same `autobot_data.db` as main backend, no new DB
- **Redis pub/sub for approval notifications** — SLM dashboard subscribes to `skills:approvals:pending`
- **Governance default is SEMI_AUTO** — safe out of the box, admin enables full auto explicitly
