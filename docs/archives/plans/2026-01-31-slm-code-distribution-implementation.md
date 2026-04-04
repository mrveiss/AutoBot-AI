# SLM Code Distribution Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement version tracking and code distribution for SLM agents across the fleet, with GUI notifications and sync controls.

**Architecture:** Git commit hash-based versioning with hybrid push notification (heartbeat response) and pull distribution (agent requests from SLM). Manual + scheduled sync triggers with multiple restart strategies.

**Tech Stack:** Python/FastAPI (backend), Vue 3/TypeScript (frontend), SQLAlchemy (database), aiohttp (agent), Ansible (deployment)

**GitHub Issue:** #741

---

## Phase 1: Version Tracking Foundation

### Task 1.1: Add Version Fields to Node Model

**Files:**
- Modify: `slm-server/models/database.py:63-94` (Node class)

**Step 1: Write the failing test**

Create file: `tests/services/slm/test_code_version.py`

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for code version tracking (Issue #741)."""

import pytest
from sqlalchemy import select

from models.database import Node, CodeStatus


class TestNodeCodeVersion:
    """Test Node code version fields."""

    @pytest.mark.asyncio
    async def test_node_has_code_version_field(self, db_session):
        """Node model should have code_version field."""
        node = Node(
            node_id="test-node-1",
            hostname="test-host",
            ip_address="192.168.1.1",
            code_version="abc123def",
        )
        db_session.add(node)
        await db_session.commit()

        result = await db_session.execute(
            select(Node).where(Node.node_id == "test-node-1")
        )
        saved = result.scalar_one()
        assert saved.code_version == "abc123def"

    @pytest.mark.asyncio
    async def test_node_has_code_status_field(self, db_session):
        """Node model should have code_status field."""
        node = Node(
            node_id="test-node-2",
            hostname="test-host",
            ip_address="192.168.1.2",
            code_status=CodeStatus.UNKNOWN.value,
        )
        db_session.add(node)
        await db_session.commit()

        result = await db_session.execute(
            select(Node).where(Node.node_id == "test-node-2")
        )
        saved = result.scalar_one()
        assert saved.code_status == "unknown"
```

**Step 2: Run test to verify it fails**

Run: `cd slm-server && python -m pytest ../tests/services/slm/test_code_version.py -v`
Expected: FAIL with "CodeStatus not defined" or "code_version not found"

**Step 3: Add CodeStatus enum and Node fields**

Modify `slm-server/models/database.py`, add after BackupStatus enum (~line 60):

```python
class CodeStatus(str, enum.Enum):
    """Code version status."""
    UP_TO_DATE = "up_to_date"
    OUTDATED = "outdated"
    UNKNOWN = "unknown"
```

Modify Node class, add after `os_info` field (~line 89):

```python
    # Code version tracking (Issue #741)
    code_version = Column(String(64), nullable=True)
    code_status = Column(String(20), default=CodeStatus.UNKNOWN.value)
```

**Step 4: Run test to verify it passes**

Run: `cd slm-server && python -m pytest ../tests/services/slm/test_code_version.py -v`
Expected: PASS

**Step 5: Create migration**

Run: `cd slm-server && alembic revision --autogenerate -m "Add code_version fields to Node"`

**Step 6: Apply migration**

Run: `cd slm-server && alembic upgrade head`

**Step 7: Commit**

```bash
git add slm-server/models/database.py tests/services/slm/test_code_version.py slm-server/migrations/versions/
git commit -m "feat(slm): add code_version and code_status fields to Node (#741)"
```

---

### Task 1.2: Extend HeartbeatRequest Schema

**Files:**
- Modify: `slm-server/models/schemas.py:119-128` (HeartbeatRequest)

**Step 1: Write the failing test**

Add to `tests/services/slm/test_code_version.py`:

```python
from models.schemas import HeartbeatRequest, HeartbeatResponse


class TestHeartbeatSchemas:
    """Test heartbeat schema extensions."""

    def test_heartbeat_request_accepts_code_version(self):
        """HeartbeatRequest should accept code_version field."""
        request = HeartbeatRequest(
            cpu_percent=25.0,
            memory_percent=50.0,
            disk_percent=30.0,
            code_version="abc123def456",
        )
        assert request.code_version == "abc123def456"

    def test_heartbeat_response_includes_update_info(self):
        """HeartbeatResponse should include update availability info."""
        response = HeartbeatResponse(
            status="ok",
            update_available=True,
            latest_version="def789abc",
        )
        assert response.update_available is True
        assert response.latest_version == "def789abc"
```

**Step 2: Run test to verify it fails**

Run: `cd slm-server && python -m pytest ../tests/services/slm/test_code_version.py::TestHeartbeatSchemas -v`
Expected: FAIL with "HeartbeatResponse not defined" or missing field

**Step 3: Extend HeartbeatRequest and add HeartbeatResponse**

Modify `slm-server/models/schemas.py`:

After HeartbeatRequest (~line 128), update and add:

```python
class HeartbeatRequest(BaseModel):
    """Agent heartbeat request."""

    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    disk_percent: float = 0.0
    agent_version: Optional[str] = None
    os_info: Optional[str] = None
    code_version: Optional[str] = None  # Issue #741: Git commit hash
    extra_data: Dict = Field(default_factory=dict)


class HeartbeatResponse(BaseModel):
    """Agent heartbeat response (Issue #741)."""

    status: str = "ok"
    update_available: bool = False
    latest_version: Optional[str] = None
    update_url: Optional[str] = None
```

**Step 4: Run test to verify it passes**

Run: `cd slm-server && python -m pytest ../tests/services/slm/test_code_version.py::TestHeartbeatSchemas -v`
Expected: PASS

**Step 5: Commit**

```bash
git add slm-server/models/schemas.py tests/services/slm/test_code_version.py
git commit -m "feat(slm): extend heartbeat schemas for code version (#741)"
```

---

### Task 1.3: Update Heartbeat Endpoint to Store and Compare Versions

**Files:**
- Modify: `slm-server/api/nodes.py` (heartbeat endpoint)

**Step 1: Write the failing test**

Add to `tests/services/slm/test_code_version.py`:

```python
import pytest
from httpx import AsyncClient


class TestHeartbeatEndpoint:
    """Test heartbeat endpoint version handling."""

    @pytest.mark.asyncio
    async def test_heartbeat_stores_code_version(self, client: AsyncClient, auth_headers, db_session):
        """Heartbeat should store reported code_version."""
        # Create a node first
        from models.database import Node
        node = Node(
            node_id="version-test-node",
            hostname="test-host",
            ip_address="192.168.1.100",
        )
        db_session.add(node)
        await db_session.commit()

        # Send heartbeat with code_version
        response = await client.post(
            "/api/nodes/version-test-node/heartbeat",
            json={
                "cpu_percent": 10.0,
                "memory_percent": 20.0,
                "disk_percent": 30.0,
                "code_version": "abc123def456",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()

        # Should return update info
        assert "update_available" in data

        # Verify stored in database
        from sqlalchemy import select
        result = await db_session.execute(
            select(Node).where(Node.node_id == "version-test-node")
        )
        saved = result.scalar_one()
        assert saved.code_version == "abc123def456"
```

**Step 2: Run test to verify it fails**

Run: `cd slm-server && python -m pytest ../tests/services/slm/test_code_version.py::TestHeartbeatEndpoint -v`
Expected: FAIL (code_version not stored or response missing update_available)

**Step 3: Update heartbeat endpoint**

Modify `slm-server/api/nodes.py`, find the heartbeat endpoint and update:

```python
from models.schemas import HeartbeatRequest, HeartbeatResponse
from models.database import CodeStatus

@router.post("/{node_id}/heartbeat", response_model=HeartbeatResponse)
async def receive_heartbeat(
    node_id: str,
    request: HeartbeatRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HeartbeatResponse:
    """
    Receive heartbeat from node agent.

    Returns update availability info (Issue #741).
    """
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node {node_id} not found",
        )

    # Update health metrics
    node.cpu_percent = request.cpu_percent
    node.memory_percent = request.memory_percent
    node.disk_percent = request.disk_percent
    node.agent_version = request.agent_version
    node.os_info = request.os_info
    node.last_heartbeat = datetime.utcnow()

    # Store code version (Issue #741)
    if request.code_version:
        node.code_version = request.code_version

    # Store extra data
    if request.extra_data:
        node.extra_data = request.extra_data

    # Update node status based on health
    if node.status == NodeStatus.OFFLINE.value:
        node.status = NodeStatus.ONLINE.value

    # Determine code status (Issue #741)
    update_available = False
    latest_version = None

    # Get latest version from settings
    from services.database import get_setting
    latest_version = await get_setting(db, "slm_agent_latest_commit")

    if latest_version and request.code_version:
        if request.code_version != latest_version:
            node.code_status = CodeStatus.OUTDATED.value
            update_available = True
        else:
            node.code_status = CodeStatus.UP_TO_DATE.value
    else:
        node.code_status = CodeStatus.UNKNOWN.value

    await db.commit()

    logger.debug(
        "Heartbeat from %s: cpu=%.1f%%, mem=%.1f%%, code=%s",
        node_id, request.cpu_percent, request.memory_percent, request.code_version
    )

    return HeartbeatResponse(
        status="ok",
        update_available=update_available,
        latest_version=latest_version,
        update_url=f"/api/nodes/{node_id}/code-package" if update_available else None,
    )
```

**Step 4: Run test to verify it passes**

Run: `cd slm-server && python -m pytest ../tests/services/slm/test_code_version.py::TestHeartbeatEndpoint -v`
Expected: PASS

**Step 5: Commit**

```bash
git add slm-server/api/nodes.py tests/services/slm/test_code_version.py
git commit -m "feat(slm): store code_version in heartbeat, return update info (#741)"
```

---

## Phase 2: Git Version Tracker Service

### Task 2.1: Create Git Tracker Service

**Files:**
- Create: `slm-server/services/git_tracker.py`
- Test: `tests/services/slm/test_git_tracker.py`

**Step 1: Write the failing test**

Create `tests/services/slm/test_git_tracker.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for Git version tracker service (Issue #741)."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from services.git_tracker import GitTracker


class TestGitTracker:
    """Test GitTracker service."""

    @pytest.mark.asyncio
    async def test_get_local_commit_hash(self, tmp_path):
        """Should get current commit hash from local git repo."""
        tracker = GitTracker(repo_path=str(tmp_path))

        # Mock git command
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (b"abc123def456\n", b"")
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc

            commit = await tracker.get_local_commit()
            assert commit == "abc123def456"

    @pytest.mark.asyncio
    async def test_fetch_remote_updates(self):
        """Should fetch updates from remote."""
        tracker = GitTracker(repo_path="/tmp/test")

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (b"", b"")
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc

            success = await tracker.fetch_remote()
            assert success is True

    @pytest.mark.asyncio
    async def test_get_remote_head_commit(self):
        """Should get HEAD commit from remote tracking branch."""
        tracker = GitTracker(repo_path="/tmp/test")

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (b"def789abc123\n", b"")
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc

            commit = await tracker.get_remote_head()
            assert commit == "def789abc123"
```

**Step 2: Run test to verify it fails**

Run: `cd slm-server && python -m pytest ../tests/services/slm/test_git_tracker.py -v`
Expected: FAIL with "No module named 'services.git_tracker'"

**Step 3: Create GitTracker service**

Create `slm-server/services/git_tracker.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Git Version Tracker Service (Issue #741)

Tracks the latest code version from the Git repository and
stores it for comparison with agent-reported versions.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class GitTracker:
    """Tracks Git repository version for code distribution."""

    def __init__(
        self,
        repo_path: str = "/home/kali/Desktop/AutoBot",
        remote: str = "origin",
        branch: str = "main",
    ):
        """
        Initialize Git tracker.

        Args:
            repo_path: Path to the git repository
            remote: Remote name (default: origin)
            branch: Branch to track (default: main)
        """
        self.repo_path = Path(repo_path)
        self.remote = remote
        self.branch = branch
        self.last_fetch: Optional[datetime] = None
        self.last_commit: Optional[str] = None

    async def _run_git_command(self, *args: str) -> tuple[str, int]:
        """Run a git command and return output."""
        cmd = ["git", "-C", str(self.repo_path)] + list(args)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            logger.warning(
                "Git command failed: %s, stderr: %s",
                " ".join(cmd),
                stderr.decode().strip(),
            )

        return stdout.decode().strip(), proc.returncode

    async def get_local_commit(self) -> Optional[str]:
        """Get the current HEAD commit hash."""
        output, code = await self._run_git_command("rev-parse", "HEAD")
        if code == 0 and output:
            return output[:12]  # Short hash
        return None

    async def fetch_remote(self) -> bool:
        """Fetch updates from remote repository."""
        _, code = await self._run_git_command("fetch", self.remote, self.branch)
        if code == 0:
            self.last_fetch = datetime.utcnow()
            return True
        return False

    async def get_remote_head(self) -> Optional[str]:
        """Get the HEAD commit of the remote tracking branch."""
        ref = f"{self.remote}/{self.branch}"
        output, code = await self._run_git_command("rev-parse", ref)
        if code == 0 and output:
            return output[:12]  # Short hash
        return None

    async def check_for_updates(self) -> dict:
        """
        Check if there are updates available.

        Returns dict with:
            - local_commit: Current local HEAD
            - remote_commit: Remote branch HEAD
            - update_available: True if remote is ahead
            - last_fetch: When we last fetched
        """
        await self.fetch_remote()

        local = await self.get_local_commit()
        remote = await self.get_remote_head()

        update_available = local != remote if local and remote else False

        self.last_commit = remote or local

        return {
            "local_commit": local,
            "remote_commit": remote,
            "update_available": update_available,
            "last_fetch": self.last_fetch.isoformat() if self.last_fetch else None,
        }


# Singleton instance
git_tracker = GitTracker()
```

**Step 4: Run test to verify it passes**

Run: `cd slm-server && python -m pytest ../tests/services/slm/test_git_tracker.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add slm-server/services/git_tracker.py tests/services/slm/test_git_tracker.py
git commit -m "feat(slm): add GitTracker service for version tracking (#741)"
```

---

### Task 2.2: Add Background Version Check Task

**Files:**
- Modify: `slm-server/main.py` (add background task)
- Create: `slm-server/services/version_checker.py`

**Step 1: Write the failing test**

Create `tests/services/slm/test_version_checker.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for version checker background task (Issue #741)."""

import pytest
from unittest.mock import AsyncMock, patch

from services.version_checker import VersionChecker


class TestVersionChecker:
    """Test version checker background service."""

    @pytest.mark.asyncio
    async def test_stores_latest_commit_in_settings(self):
        """Should store latest commit hash in system settings."""
        checker = VersionChecker(check_interval=300)

        with patch("services.version_checker.git_tracker") as mock_tracker:
            mock_tracker.check_for_updates = AsyncMock(return_value={
                "local_commit": "abc123",
                "remote_commit": "def456",
                "update_available": True,
                "last_fetch": "2026-01-31T12:00:00",
            })

            with patch("services.version_checker.set_setting") as mock_set:
                mock_set.return_value = None

                await checker.check_and_store()

                mock_set.assert_called()
                # Should store the remote commit as latest
                calls = [str(c) for c in mock_set.call_args_list]
                assert any("def456" in c for c in calls)
```

**Step 2: Run test to verify it fails**

Run: `cd slm-server && python -m pytest ../tests/services/slm/test_version_checker.py -v`
Expected: FAIL with "No module named 'services.version_checker'"

**Step 3: Create VersionChecker service**

Create `slm-server/services/version_checker.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Version Checker Background Service (Issue #741)

Periodically checks for code updates and stores the latest
version in system settings for heartbeat comparison.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from services.git_tracker import git_tracker

logger = logging.getLogger(__name__)


async def set_setting(key: str, value: str) -> None:
    """Store a setting in the database."""
    from services.database import db_service
    from models.database import Setting
    from sqlalchemy import select

    async with db_service.session() as db:
        result = await db.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()

        if setting:
            setting.value = value
            setting.updated_at = datetime.utcnow()
        else:
            setting = Setting(
                key=key,
                value=value,
                value_type="string",
                description="Auto-managed by version checker",
            )
            db.add(setting)

        await db.commit()


class VersionChecker:
    """Background service that checks for code updates."""

    def __init__(self, check_interval: int = 300):
        """
        Initialize version checker.

        Args:
            check_interval: Seconds between checks (default: 5 minutes)
        """
        self.check_interval = check_interval
        self.running = False
        self.last_check: Optional[datetime] = None
        self.latest_version: Optional[str] = None

    async def check_and_store(self) -> dict:
        """Check for updates and store latest version."""
        result = await git_tracker.check_for_updates()

        # Store the remote commit as the "latest" version
        latest = result.get("remote_commit") or result.get("local_commit")

        if latest:
            self.latest_version = latest
            await set_setting("slm_agent_latest_commit", latest)
            await set_setting(
                "slm_agent_last_check",
                datetime.utcnow().isoformat(),
            )

            logger.info(
                "Version check complete: latest=%s, update_available=%s",
                latest,
                result.get("update_available"),
            )

        self.last_check = datetime.utcnow()
        return result

    async def run(self) -> None:
        """Run the background check loop."""
        self.running = True
        logger.info(
            "Version checker started (interval: %ds)",
            self.check_interval,
        )

        while self.running:
            try:
                await self.check_and_store()
            except Exception as e:
                logger.error("Version check failed: %s", e)

            await asyncio.sleep(self.check_interval)

        logger.info("Version checker stopped")

    def stop(self) -> None:
        """Stop the background loop."""
        self.running = False


# Singleton instance
version_checker = VersionChecker()
```

**Step 4: Run test to verify it passes**

Run: `cd slm-server && python -m pytest ../tests/services/slm/test_version_checker.py -v`
Expected: PASS

**Step 5: Add to main.py startup**

Modify `slm-server/main.py`, add to lifespan or startup:

```python
from services.version_checker import version_checker

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... existing startup code ...

    # Start version checker background task (Issue #741)
    version_task = asyncio.create_task(version_checker.run())
    logger.info("Version checker background task started")

    yield

    # Shutdown
    version_checker.stop()
    version_task.cancel()
    # ... existing shutdown code ...
```

**Step 6: Commit**

```bash
git add slm-server/services/version_checker.py slm-server/main.py tests/services/slm/test_version_checker.py
git commit -m "feat(slm): add version checker background service (#741)"
```

---

## Phase 3: Code Distribution API

### Task 3.1: Create Code Sync API Endpoints

**Files:**
- Create: `slm-server/api/code_sync.py`
- Test: `tests/api/slm/test_code_sync_api.py`

**Step 1: Write the failing test**

Create `tests/api/slm/test_code_sync_api.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for code sync API endpoints (Issue #741)."""

import pytest
from httpx import AsyncClient


class TestCodeSyncStatus:
    """Test /api/code-sync/status endpoint."""

    @pytest.mark.asyncio
    async def test_get_status_returns_version_info(
        self, client: AsyncClient, auth_headers
    ):
        """Should return current version status."""
        response = await client.get(
            "/api/code-sync/status",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()

        assert "latest_version" in data
        assert "last_check" in data
        assert "outdated_nodes" in data


class TestCodeSyncRefresh:
    """Test /api/code-sync/refresh endpoint."""

    @pytest.mark.asyncio
    async def test_refresh_triggers_version_check(
        self, client: AsyncClient, auth_headers
    ):
        """Should trigger immediate version check."""
        response = await client.post(
            "/api/code-sync/refresh",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
```

**Step 2: Run test to verify it fails**

Run: `cd slm-server && python -m pytest ../tests/api/slm/test_code_sync_api.py -v`
Expected: FAIL with 404 (endpoint not found)

**Step 3: Create code sync API**

Create `slm-server/api/code_sync.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Sync API Routes (Issue #741)

Endpoints for code distribution and version management.
"""

import logging
from datetime import datetime
from typing import Optional

from typing_extensions import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import Node, CodeStatus
from services.auth import get_current_user
from services.database import get_db, get_setting
from services.version_checker import version_checker

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/code-sync", tags=["code-sync"])


class CodeSyncStatusResponse(BaseModel):
    """Code sync status response."""

    latest_version: Optional[str] = None
    last_check: Optional[str] = None
    outdated_nodes: int = 0
    up_to_date_nodes: int = 0
    unknown_nodes: int = 0
    total_nodes: int = 0


class CodeSyncRefreshResponse(BaseModel):
    """Code sync refresh response."""

    success: bool
    message: str
    latest_version: Optional[str] = None
    update_available: bool = False


class NodeSyncRequest(BaseModel):
    """Request to sync a node."""

    restart_strategy: str = Field(
        default="immediate",
        pattern="^(immediate|graceful|manual)$",
    )


class NodeSyncResponse(BaseModel):
    """Node sync response."""

    success: bool
    message: str
    job_id: Optional[str] = None
    node_id: str


class FleetSyncRequest(BaseModel):
    """Request to sync entire fleet."""

    strategy: str = Field(
        default="rolling",
        pattern="^(parallel|rolling)$",
    )
    restart_strategy: str = Field(
        default="immediate",
        pattern="^(immediate|graceful|manual)$",
    )
    batch_size: int = Field(default=1, ge=1, le=10)
    health_check_delay: int = Field(default=30, ge=0, le=300)
    abort_on_failure: bool = True


class FleetSyncResponse(BaseModel):
    """Fleet sync response."""

    success: bool
    message: str
    job_id: Optional[str] = None
    nodes_queued: int = 0


@router.get("/status", response_model=CodeSyncStatusResponse)
async def get_status(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> CodeSyncStatusResponse:
    """Get current code sync status."""
    # Get latest version from settings
    latest_version = await get_setting(db, "slm_agent_latest_commit")
    last_check = await get_setting(db, "slm_agent_last_check")

    # Count nodes by code status
    outdated = await db.execute(
        select(func.count()).select_from(Node).where(
            Node.code_status == CodeStatus.OUTDATED.value
        )
    )
    up_to_date = await db.execute(
        select(func.count()).select_from(Node).where(
            Node.code_status == CodeStatus.UP_TO_DATE.value
        )
    )
    unknown = await db.execute(
        select(func.count()).select_from(Node).where(
            Node.code_status == CodeStatus.UNKNOWN.value
        )
    )
    total = await db.execute(select(func.count()).select_from(Node))

    return CodeSyncStatusResponse(
        latest_version=latest_version,
        last_check=last_check,
        outdated_nodes=outdated.scalar() or 0,
        up_to_date_nodes=up_to_date.scalar() or 0,
        unknown_nodes=unknown.scalar() or 0,
        total_nodes=total.scalar() or 0,
    )


@router.post("/refresh", response_model=CodeSyncRefreshResponse)
async def refresh_version(
    _: Annotated[dict, Depends(get_current_user)],
) -> CodeSyncRefreshResponse:
    """Trigger immediate version check."""
    try:
        result = await version_checker.check_and_store()

        return CodeSyncRefreshResponse(
            success=True,
            message="Version check completed",
            latest_version=result.get("remote_commit") or result.get("local_commit"),
            update_available=result.get("update_available", False),
        )
    except Exception as e:
        logger.error("Version refresh failed: %s", e)
        return CodeSyncRefreshResponse(
            success=False,
            message=str(e),
        )


@router.get("/pending")
async def list_pending_updates(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
):
    """List all nodes needing updates."""
    result = await db.execute(
        select(Node).where(Node.code_status == CodeStatus.OUTDATED.value)
    )
    nodes = result.scalars().all()

    return {
        "nodes": [
            {
                "node_id": n.node_id,
                "hostname": n.hostname,
                "ip_address": n.ip_address,
                "current_version": n.code_version,
                "status": n.status,
            }
            for n in nodes
        ],
        "total": len(nodes),
    }
```

**Step 4: Register router in main.py**

Add to `slm-server/main.py`:

```python
from api.code_sync import router as code_sync_router
app.include_router(code_sync_router, prefix="/api")
```

**Step 5: Run test to verify it passes**

Run: `cd slm-server && python -m pytest ../tests/api/slm/test_code_sync_api.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add slm-server/api/code_sync.py slm-server/main.py tests/api/slm/test_code_sync_api.py
git commit -m "feat(slm): add code sync API endpoints (#741)"
```

---

### Task 3.2: Add Node Sync Endpoint

**Files:**
- Modify: `slm-server/api/code_sync.py` (add sync endpoint)
- Create: `slm-server/services/code_distributor.py`

**Step 1: Write the failing test**

Add to `tests/api/slm/test_code_sync_api.py`:

```python
class TestNodeSync:
    """Test /api/code-sync/nodes/{node_id}/sync endpoint."""

    @pytest.mark.asyncio
    async def test_sync_node_creates_job(
        self, client: AsyncClient, auth_headers, db_session
    ):
        """Should create sync job for node."""
        from models.database import Node

        # Create test node
        node = Node(
            node_id="sync-test-node",
            hostname="sync-host",
            ip_address="192.168.1.200",
            code_status="outdated",
        )
        db_session.add(node)
        await db_session.commit()

        response = await client.post(
            "/api/code-sync/nodes/sync-test-node/sync",
            json={"restart_strategy": "immediate"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["node_id"] == "sync-test-node"
        assert "job_id" in data
```

**Step 2: Run test to verify it fails**

Run: `cd slm-server && python -m pytest ../tests/api/slm/test_code_sync_api.py::TestNodeSync -v`
Expected: FAIL with 404

**Step 3: Create CodeDistributor service**

Create `slm-server/services/code_distributor.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Distributor Service (Issue #741)

Handles building and distributing code packages to agents.
"""

import asyncio
import logging
import os
import tarfile
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Track running sync jobs
_sync_jobs: Dict[str, asyncio.Task] = {}


class SyncJob:
    """Represents a code sync job."""

    def __init__(
        self,
        job_id: str,
        node_id: str,
        restart_strategy: str = "immediate",
    ):
        self.job_id = job_id
        self.node_id = node_id
        self.restart_strategy = restart_strategy
        self.status = "pending"
        self.progress = 0
        self.error: Optional[str] = None
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None


async def build_agent_package(version: str) -> Path:
    """
    Build a tarball of the agent code.

    Returns path to the tarball.
    """
    repo_path = Path("/home/kali/Desktop/AutoBot")
    agent_src = repo_path / "src" / "slm" / "agent"

    if not agent_src.exists():
        raise FileNotFoundError(f"Agent source not found: {agent_src}")

    # Create temp directory for package
    tmp_dir = Path(tempfile.mkdtemp(prefix="slm-agent-"))
    package_path = tmp_dir / f"slm-agent-{version}.tar.gz"

    with tarfile.open(package_path, "w:gz") as tar:
        # Add agent code
        tar.add(agent_src, arcname="slm/agent")

        # Create version.json
        version_file = tmp_dir / "version.json"
        version_file.write_text(f'{{"version": "{version}", "built_at": "{datetime.utcnow().isoformat()}"}}')
        tar.add(version_file, arcname="version.json")

    logger.info("Built agent package: %s", package_path)
    return package_path


async def sync_node(
    node_id: str,
    ip_address: str,
    ssh_user: str,
    ssh_port: int,
    version: str,
    restart_strategy: str = "immediate",
) -> dict:
    """
    Sync code to a specific node.

    Steps:
    1. Build agent package
    2. Transfer to node via SCP
    3. Extract and swap atomically
    4. Optionally restart agent service
    """
    result = {
        "success": False,
        "message": "",
        "node_id": node_id,
    }

    try:
        # Build package
        package_path = await build_agent_package(version)

        # Transfer via SCP
        remote_path = "/tmp/slm-agent-update.tar.gz"
        scp_cmd = [
            "scp",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=30",
            "-P", str(ssh_port),
            str(package_path),
            f"{ssh_user}@{ip_address}:{remote_path}",
        ]

        proc = await asyncio.create_subprocess_exec(
            *scp_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

        if proc.returncode != 0:
            result["message"] = f"SCP failed: {stderr.decode()}"
            return result

        # Extract and install on remote
        install_cmd = f"""
            cd /tmp && \
            rm -rf slm-agent-staging && \
            mkdir slm-agent-staging && \
            tar -xzf {remote_path} -C slm-agent-staging && \
            sudo rm -rf /opt/slm-agent.old && \
            sudo mv /opt/slm-agent /opt/slm-agent.old 2>/dev/null || true && \
            sudo mv slm-agent-staging /opt/slm-agent && \
            rm -f {remote_path}
        """

        ssh_cmd = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=30",
            "-p", str(ssh_port),
            f"{ssh_user}@{ip_address}",
            install_cmd,
        ]

        proc = await asyncio.create_subprocess_exec(
            *ssh_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

        if proc.returncode != 0:
            result["message"] = f"Install failed: {stderr.decode()}"
            return result

        # Restart if requested
        if restart_strategy != "manual":
            restart_cmd = "sudo systemctl restart slm-agent"
            if restart_strategy == "graceful":
                restart_cmd = "sudo systemctl reload-or-restart slm-agent"

            ssh_restart = [
                "ssh",
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-p", str(ssh_port),
                f"{ssh_user}@{ip_address}",
                restart_cmd,
            ]

            proc = await asyncio.create_subprocess_exec(
                *ssh_restart,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

        # Cleanup local package
        package_path.unlink()
        package_path.parent.rmdir()

        result["success"] = True
        result["message"] = f"Code synced to {node_id}"

    except asyncio.TimeoutError:
        result["message"] = "Operation timed out"
    except Exception as e:
        logger.error("Sync failed for %s: %s", node_id, e)
        result["message"] = str(e)

    return result


def create_sync_job(node_id: str, restart_strategy: str) -> SyncJob:
    """Create a new sync job."""
    job_id = str(uuid.uuid4())[:16]
    return SyncJob(job_id, node_id, restart_strategy)
```

**Step 4: Add sync endpoint to code_sync.py**

Add to `slm-server/api/code_sync.py`:

```python
from services.code_distributor import create_sync_job, sync_node

@router.post("/nodes/{node_id}/sync", response_model=NodeSyncResponse)
async def sync_node_code(
    node_id: str,
    request: NodeSyncRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NodeSyncResponse:
    """Sync code to a specific node."""
    # Get node
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    # Get latest version
    latest = await get_setting(db, "slm_agent_latest_commit")
    if not latest:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No version available. Run refresh first.",
        )

    # Create job
    job = create_sync_job(node_id, request.restart_strategy)

    # Start sync in background
    async def run_sync():
        result = await sync_node(
            node_id=node.node_id,
            ip_address=node.ip_address,
            ssh_user=node.ssh_user or "autobot",
            ssh_port=node.ssh_port or 22,
            version=latest,
            restart_strategy=request.restart_strategy,
        )

        # Update node status on success
        if result["success"]:
            from services.database import db_service
            async with db_service.session() as db:
                node_result = await db.execute(
                    select(Node).where(Node.node_id == node_id)
                )
                n = node_result.scalar_one_or_none()
                if n:
                    n.code_version = latest
                    n.code_status = CodeStatus.UP_TO_DATE.value
                    await db.commit()

    asyncio.create_task(run_sync())

    logger.info("Sync job created: %s for node %s", job.job_id, node_id)

    return NodeSyncResponse(
        success=True,
        message=f"Sync job started for {node_id}",
        job_id=job.job_id,
        node_id=node_id,
    )
```

**Step 5: Run test to verify it passes**

Run: `cd slm-server && python -m pytest ../tests/api/slm/test_code_sync_api.py::TestNodeSync -v`
Expected: PASS

**Step 6: Commit**

```bash
git add slm-server/services/code_distributor.py slm-server/api/code_sync.py tests/api/slm/test_code_sync_api.py
git commit -m "feat(slm): add node sync endpoint and code distributor (#741)"
```

---

## Phase 4: Agent Updater

### Task 4.1: Add Version Module to Agent

**Files:**
- Create: `src/slm/agent/version.py`
- Test: `tests/slm/test_version.py`

**Step 1: Write the failing test**

Create `tests/slm/test_version.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for agent version module (Issue #741)."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock


class TestVersionModule:
    """Test version reading and reporting."""

    def test_read_version_from_file(self, tmp_path):
        """Should read version from version.json."""
        from src.slm.agent.version import read_version

        version_file = tmp_path / "version.json"
        version_file.write_text('{"version": "abc123def"}')

        version = read_version(str(tmp_path))
        assert version == "abc123def"

    def test_read_version_missing_file(self, tmp_path):
        """Should return None if version.json missing."""
        from src.slm.agent.version import read_version

        version = read_version(str(tmp_path))
        assert version is None

    def test_get_git_version_fallback(self):
        """Should get version from git if no version.json."""
        from src.slm.agent.version import get_version

        with patch("src.slm.agent.version.read_version") as mock_read:
            mock_read.return_value = None

            with patch("subprocess.run") as mock_run:
                mock_run.return_value.stdout = "def456abc\n"
                mock_run.return_value.returncode = 0

                version = get_version()
                # Should try git as fallback
                assert version is not None or mock_run.called
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/slm/test_version.py -v`
Expected: FAIL with "No module named 'src.slm.agent.version'"

**Step 3: Create version module**

Create `src/slm/agent/version.py`:

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Version Module (Issue #741)

Handles version tracking for the SLM agent.
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default paths
DEFAULT_INSTALL_PATH = "/opt/slm-agent"
VERSION_FILE = "version.json"


def read_version(install_path: str = DEFAULT_INSTALL_PATH) -> Optional[str]:
    """
    Read version from version.json file.

    Args:
        install_path: Path where agent is installed

    Returns:
        Version string (commit hash) or None
    """
    version_file = Path(install_path) / VERSION_FILE

    if not version_file.exists():
        logger.debug("Version file not found: %s", version_file)
        return None

    try:
        data = json.loads(version_file.read_text(encoding="utf-8"))
        return data.get("version")
    except (json.JSONDecodeError, IOError) as e:
        logger.warning("Failed to read version file: %s", e)
        return None


def get_git_version() -> Optional[str]:
    """Get version from git repository (development fallback)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        logger.debug("Git version lookup failed: %s", e)

    return None


def get_version(install_path: str = DEFAULT_INSTALL_PATH) -> Optional[str]:
    """
    Get the current agent version.

    First tries version.json, falls back to git for development.

    Args:
        install_path: Path where agent is installed

    Returns:
        Version string (commit hash) or None
    """
    # Try version.json first (production)
    version = read_version(install_path)
    if version:
        return version

    # Fall back to git (development)
    return get_git_version()
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/slm/test_version.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/slm/agent/version.py tests/slm/test_version.py
git commit -m "feat(slm): add agent version module (#741)"
```

---

### Task 4.2: Update Agent to Report Code Version

**Files:**
- Modify: `src/slm/agent/agent.py` (include code_version in heartbeat)

**Step 1: Write the failing test**

Add to `tests/slm/test_agent.py`:

```python
class TestAgentCodeVersion:
    """Test agent code version reporting."""

    @pytest.mark.asyncio
    async def test_heartbeat_includes_code_version(self):
        """Heartbeat payload should include code_version."""
        from src.slm.agent.agent import SLMAgent
        from unittest.mock import patch, AsyncMock

        agent = SLMAgent(
            admin_url="http://localhost:8000",
            node_id="test-node",
        )

        with patch("src.slm.agent.version.get_version") as mock_version:
            mock_version.return_value = "abc123def"

            with patch("aiohttp.ClientSession") as mock_session:
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(return_value={"status": "ok"})

                mock_session_instance = AsyncMock()
                mock_session_instance.post.return_value.__aenter__.return_value = mock_response
                mock_session.return_value.__aenter__.return_value = mock_session_instance

                await agent.send_heartbeat()

                # Check that code_version was in the payload
                call_args = mock_session_instance.post.call_args
                payload = call_args.kwargs.get("json", {})
                # The exact structure depends on implementation
```

**Step 2: Update agent.py to include code_version**

Modify `src/slm/agent/agent.py`:

In the `send_heartbeat` method, add:

```python
from .version import get_version

async def send_heartbeat(self) -> bool:
    """Send heartbeat with health data to admin."""
    import platform

    health = self.collector.collect()

    # Get current code version (Issue #741)
    code_version = get_version()

    # Payload matches HeartbeatRequest schema
    os_info = f"{platform.system()} {platform.release()}"
    payload = {
        "cpu_percent": health.get("cpu_percent", 0.0),
        "memory_percent": health.get("memory_percent", 0.0),
        "disk_percent": health.get("disk_percent", 0.0),
        "agent_version": "1.0.0",
        "os_info": os_info,
        "code_version": code_version,  # Issue #741
        "extra_data": {
            "services": health.get("services", {}),
            "discovered_services": health.get("discovered_services", []),
            "load_avg": health.get("load_avg", []),
            "uptime_seconds": health.get("uptime_seconds", 0),
            "hostname": health.get("hostname"),
        },
    }
    # ... rest of method
```

**Step 3: Handle update notification in response**

Add to agent.py after receiving heartbeat response:

```python
if response.status == 200:
    data = await response.json()

    # Check for update notification (Issue #741)
    if data.get("update_available"):
        logger.info(
            "Update available: current=%s, latest=%s",
            code_version,
            data.get("latest_version"),
        )
        self.pending_update = True
        self.latest_version = data.get("latest_version")

    return True
```

**Step 4: Commit**

```bash
git add src/slm/agent/agent.py tests/slm/test_agent.py
git commit -m "feat(slm): agent reports code_version in heartbeat (#741)"
```

---

## Phase 5: Frontend Updates View

### Task 5.1: Create Updates Composable

**Files:**
- Create: `slm-admin/src/composables/useCodeSync.ts`

**Step 1: Create the composable**

Create `slm-admin/src/composables/useCodeSync.ts`:

```typescript
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Code Sync Composable (Issue #741)
 *
 * Provides API integration for code distribution features.
 */

import axios from 'axios'
import { ref, computed } from 'vue'

const API_BASE = '/api'

export interface CodeSyncStatus {
  latest_version: string | null
  last_check: string | null
  outdated_nodes: number
  up_to_date_nodes: number
  unknown_nodes: number
  total_nodes: number
}

export interface PendingNode {
  node_id: string
  hostname: string
  ip_address: string
  current_version: string | null
  status: string
}

export interface SyncResult {
  success: boolean
  message: string
  job_id?: string
  node_id?: string
}

export function useCodeSync() {
  const status = ref<CodeSyncStatus | null>(null)
  const pendingNodes = ref<PendingNode[]>([])
  const isLoading = ref(false)
  const isRefreshing = ref(false)
  const isSyncing = ref<Record<string, boolean>>({})
  const error = ref<string | null>(null)

  const hasUpdates = computed(() => (status.value?.outdated_nodes ?? 0) > 0)

  async function fetchStatus(): Promise<void> {
    isLoading.value = true
    error.value = null

    try {
      const response = await axios.get<CodeSyncStatus>(
        `${API_BASE}/code-sync/status`
      )
      status.value = response.data
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message
    } finally {
      isLoading.value = false
    }
  }

  async function fetchPending(): Promise<void> {
    try {
      const response = await axios.get<{ nodes: PendingNode[]; total: number }>(
        `${API_BASE}/code-sync/pending`
      )
      pendingNodes.value = response.data.nodes
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message
    }
  }

  async function refresh(): Promise<SyncResult> {
    isRefreshing.value = true
    error.value = null

    try {
      const response = await axios.post<SyncResult>(
        `${API_BASE}/code-sync/refresh`
      )
      await fetchStatus()
      return response.data
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message
      return { success: false, message: error.value || 'Refresh failed' }
    } finally {
      isRefreshing.value = false
    }
  }

  async function syncNode(
    nodeId: string,
    restartStrategy: 'immediate' | 'graceful' | 'manual' = 'immediate'
  ): Promise<SyncResult> {
    isSyncing.value[nodeId] = true
    error.value = null

    try {
      const response = await axios.post<SyncResult>(
        `${API_BASE}/code-sync/nodes/${nodeId}/sync`,
        { restart_strategy: restartStrategy }
      )
      return response.data
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message
      return { success: false, message: error.value || 'Sync failed', node_id: nodeId }
    } finally {
      isSyncing.value[nodeId] = false
    }
  }

  async function syncFleet(
    strategy: 'parallel' | 'rolling' = 'rolling',
    restartStrategy: 'immediate' | 'graceful' | 'manual' = 'immediate'
  ): Promise<SyncResult> {
    error.value = null

    try {
      const response = await axios.post<SyncResult>(
        `${API_BASE}/code-sync/fleet/sync`,
        { strategy, restart_strategy: restartStrategy }
      )
      return response.data
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message
      return { success: false, message: error.value || 'Fleet sync failed' }
    }
  }

  return {
    // State
    status,
    pendingNodes,
    isLoading,
    isRefreshing,
    isSyncing,
    error,

    // Computed
    hasUpdates,

    // Methods
    fetchStatus,
    fetchPending,
    refresh,
    syncNode,
    syncFleet,
  }
}
```

**Step 2: Commit**

```bash
git add slm-admin/src/composables/useCodeSync.ts
git commit -m "feat(slm): add useCodeSync composable (#741)"
```

---

### Task 5.2: Create Updates View

**Files:**
- Create: `slm-admin/src/views/UpdatesView.vue`
- Modify: `slm-admin/src/router/index.ts` (add route)

**Step 1: Create UpdatesView.vue**

Create `slm-admin/src/views/UpdatesView.vue`:

```vue
<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Updates View (Issue #741)
 *
 * Manages code distribution and version tracking for SLM agents.
 */

import { ref, onMounted, onUnmounted } from 'vue'
import { useCodeSync } from '@/composables/useCodeSync'
import { useSlmWebSocket } from '@/composables/useSlmWebSocket'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('UpdatesView')
const codeSync = useCodeSync()
const ws = useSlmWebSocket()

// Sync modal state
const showSyncModal = ref(false)
const selectedNode = ref<string | null>(null)
const restartStrategy = ref<'immediate' | 'graceful' | 'manual'>('immediate')
const isSyncingFleet = ref(false)

// Notification
const notification = ref<{ show: boolean; type: 'success' | 'error'; message: string }>({
  show: false,
  type: 'success',
  message: '',
})

async function loadData() {
  await Promise.all([
    codeSync.fetchStatus(),
    codeSync.fetchPending(),
  ])
}

async function handleRefresh() {
  const result = await codeSync.refresh()
  showNotification(result.success ? 'success' : 'error', result.message)
  await codeSync.fetchPending()
}

async function handleSyncNode(nodeId: string) {
  selectedNode.value = nodeId
  showSyncModal.value = true
}

async function confirmSync() {
  if (!selectedNode.value) return

  const result = await codeSync.syncNode(selectedNode.value, restartStrategy.value)
  showNotification(result.success ? 'success' : 'error', result.message)
  showSyncModal.value = false
  selectedNode.value = null

  // Refresh after short delay
  setTimeout(() => loadData(), 2000)
}

async function handleSyncAll() {
  isSyncingFleet.value = true
  const result = await codeSync.syncFleet('rolling', restartStrategy.value)
  showNotification(result.success ? 'success' : 'error', result.message)
  isSyncingFleet.value = false

  // Refresh after short delay
  setTimeout(() => loadData(), 2000)
}

function showNotification(type: 'success' | 'error', message: string) {
  notification.value = { show: true, type, message }
  setTimeout(() => { notification.value.show = false }, 5000)
}

// Refresh on WebSocket events
function handleWsMessage(data: any) {
  if (data.type === 'node.code_status_changed' || data.type === 'sync.completed') {
    loadData()
  }
}

onMounted(() => {
  loadData()
  ws.subscribe('events:global', handleWsMessage)
})

onUnmounted(() => {
  ws.unsubscribe('events:global', handleWsMessage)
})
</script>

<template>
  <div class="updates-view">
    <!-- Header -->
    <div class="view-header">
      <h1>Code Updates</h1>
      <div class="header-actions">
        <button
          class="btn btn-secondary"
          :disabled="codeSync.isRefreshing.value"
          @click="handleRefresh"
        >
          <span v-if="codeSync.isRefreshing.value">Checking...</span>
          <span v-else>Check for Updates</span>
        </button>
      </div>
    </div>

    <!-- Status Banner -->
    <div class="status-banner" v-if="codeSync.status.value">
      <div class="status-item">
        <span class="label">Latest Version</span>
        <code class="value">{{ codeSync.status.value.latest_version || 'Unknown' }}</code>
      </div>
      <div class="status-item">
        <span class="label">Last Check</span>
        <span class="value">{{ codeSync.status.value.last_check || 'Never' }}</span>
      </div>
      <div class="status-item">
        <span class="label">Up to Date</span>
        <span class="value good">{{ codeSync.status.value.up_to_date_nodes }}</span>
      </div>
      <div class="status-item">
        <span class="label">Outdated</span>
        <span class="value" :class="{ warn: codeSync.status.value.outdated_nodes > 0 }">
          {{ codeSync.status.value.outdated_nodes }}
        </span>
      </div>
    </div>

    <!-- Pending Updates Table -->
    <div class="pending-section" v-if="codeSync.pendingNodes.value.length > 0">
      <div class="section-header">
        <h2>Nodes Needing Updates</h2>
        <button
          class="btn btn-primary"
          :disabled="isSyncingFleet"
          @click="handleSyncAll"
        >
          {{ isSyncingFleet ? 'Syncing...' : 'Sync All' }}
        </button>
      </div>

      <table class="data-table">
        <thead>
          <tr>
            <th>Hostname</th>
            <th>IP Address</th>
            <th>Current Version</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="node in codeSync.pendingNodes.value" :key="node.node_id">
            <td>{{ node.hostname }}</td>
            <td><code>{{ node.ip_address }}</code></td>
            <td><code>{{ node.current_version || 'Unknown' }}</code></td>
            <td>
              <span class="badge badge-warning">Outdated</span>
            </td>
            <td>
              <button
                class="btn btn-sm btn-primary"
                :disabled="codeSync.isSyncing.value[node.node_id]"
                @click="handleSyncNode(node.node_id)"
              >
                {{ codeSync.isSyncing.value[node.node_id] ? 'Syncing...' : 'Sync' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- No Updates Message -->
    <div class="no-updates" v-else-if="!codeSync.isLoading.value">
      <p>All nodes are up to date!</p>
    </div>

    <!-- Sync Modal -->
    <div class="modal" v-if="showSyncModal" @click.self="showSyncModal = false">
      <div class="modal-content">
        <h3>Sync Node</h3>
        <p>Select restart strategy for {{ selectedNode }}:</p>

        <div class="form-group">
          <label>
            <input type="radio" v-model="restartStrategy" value="immediate" />
            Immediate - Stop, update, start
          </label>
          <label>
            <input type="radio" v-model="restartStrategy" value="graceful" />
            Graceful - Wait for current work, then restart
          </label>
          <label>
            <input type="radio" v-model="restartStrategy" value="manual" />
            Manual - Update code only, restart later
          </label>
        </div>

        <div class="modal-actions">
          <button class="btn btn-secondary" @click="showSyncModal = false">Cancel</button>
          <button class="btn btn-primary" @click="confirmSync">Sync Now</button>
        </div>
      </div>
    </div>

    <!-- Notification -->
    <div
      class="notification"
      :class="notification.type"
      v-if="notification.show"
    >
      {{ notification.message }}
    </div>
  </div>
</template>

<style scoped>
.updates-view {
  padding: 1.5rem;
}

.view-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

.status-banner {
  display: flex;
  gap: 2rem;
  padding: 1rem;
  background: var(--bg-secondary);
  border-radius: 8px;
  margin-bottom: 1.5rem;
}

.status-item {
  display: flex;
  flex-direction: column;
}

.status-item .label {
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.status-item .value {
  font-size: 1.25rem;
  font-weight: 600;
}

.status-item .value.good { color: var(--success); }
.status-item .value.warn { color: var(--warning); }

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table th,
.data-table td {
  padding: 0.75rem;
  text-align: left;
  border-bottom: 1px solid var(--border);
}

.badge {
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
}

.badge-warning {
  background: var(--warning-bg);
  color: var(--warning);
}

.no-updates {
  text-align: center;
  padding: 3rem;
  color: var(--text-secondary);
}

.modal {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-content {
  background: var(--bg-primary);
  padding: 1.5rem;
  border-radius: 8px;
  min-width: 400px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 1rem;
}

.form-group label {
  display: block;
  margin: 0.5rem 0;
}

.notification {
  position: fixed;
  bottom: 1rem;
  right: 1rem;
  padding: 1rem;
  border-radius: 8px;
}

.notification.success {
  background: var(--success-bg);
  color: var(--success);
}

.notification.error {
  background: var(--error-bg);
  color: var(--error);
}
</style>
```

**Step 2: Add route**

Modify `slm-admin/src/router/index.ts`, add after deployments route:

```typescript
{
  path: '/updates',
  name: 'updates',
  component: () => import('@/views/UpdatesView.vue'),
  meta: { title: 'Code Updates' }
},
```

**Step 3: Commit**

```bash
git add slm-admin/src/views/UpdatesView.vue slm-admin/src/router/index.ts
git commit -m "feat(slm): add UpdatesView for code distribution (#741)"
```

---

### Task 5.3: Add Update Badge to Navigation

**Files:**
- Modify: `slm-admin/src/components/layout/Sidebar.vue` (or equivalent nav component)

**Step 1: Add badge indicator**

Find the navigation component and add update badge next to "Updates" menu item:

```vue
<router-link to="/updates" class="nav-item">
  <span class="nav-icon">📦</span>
  <span class="nav-label">Updates</span>
  <span
    v-if="outdatedCount > 0"
    class="update-badge"
  >
    {{ outdatedCount }}
  </span>
</router-link>

<script setup>
import { ref, onMounted } from 'vue'
import { useCodeSync } from '@/composables/useCodeSync'

const codeSync = useCodeSync()
const outdatedCount = ref(0)

onMounted(async () => {
  await codeSync.fetchStatus()
  outdatedCount.value = codeSync.status.value?.outdated_nodes ?? 0
})
</script>

<style scoped>
.update-badge {
  background: var(--warning);
  color: white;
  font-size: 0.75rem;
  padding: 0.125rem 0.375rem;
  border-radius: 10px;
  margin-left: auto;
}
</style>
```

**Step 2: Commit**

```bash
git add slm-admin/src/components/
git commit -m "feat(slm): add update badge to navigation (#741)"
```

---

## Phase 6: Update Ansible Deployment

### Task 6.1: Embed Version at Deploy Time

**Files:**
- Modify: `ansible/roles/slm_agent/tasks/main.yml`
- Create: `ansible/roles/slm_agent/templates/version.json.j2`

**Step 1: Create version.json template**

Create `ansible/roles/slm_agent/templates/version.json.j2`:

```json
{
  "version": "{{ slm_agent_version | default(git_commit_hash) }}",
  "deployed_at": "{{ ansible_date_time.iso8601 }}",
  "deployed_by": "ansible"
}
```

**Step 2: Update tasks to get git hash and deploy version file**

Add to `ansible/roles/slm_agent/tasks/main.yml`:

```yaml
- name: Get current git commit hash
  delegate_to: localhost
  command: git rev-parse --short HEAD
  args:
    chdir: "{{ playbook_dir }}/.."
  register: git_hash
  changed_when: false
  run_once: true

- name: Set git commit fact
  set_fact:
    git_commit_hash: "{{ git_hash.stdout }}"
  run_once: true

- name: Deploy version.json
  template:
    src: version.json.j2
    dest: /opt/slm-agent/version.json
    owner: root
    group: root
    mode: '0644'
  notify: restart slm-agent
```

**Step 3: Commit**

```bash
git add ansible/roles/slm_agent/
git commit -m "feat(slm): embed git version in agent deployment (#741)"
```

---

## Summary

This plan covers 8 phases with bite-sized tasks:

1. **Phase 1**: Version tracking foundation (Node model, schemas, heartbeat)
2. **Phase 2**: Git tracker service (fetch, compare versions)
3. **Phase 3**: Code sync API (status, refresh, sync endpoints)
4. **Phase 4**: Agent updater (version module, heartbeat integration)
5. **Phase 5**: Frontend updates view (composable, view, navigation)
6. **Phase 6**: Ansible deployment (embed version at deploy time)

Each task follows TDD with explicit test → implement → commit cycles.

---

Plan complete and saved to `docs/plans/2026-01-31-slm-code-distribution-implementation.md`.

**Two execution options:**

1. **Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

2. **Parallel Session (separate)** - Open new session with executing-plans skill, batch execution with checkpoints

Which approach?
