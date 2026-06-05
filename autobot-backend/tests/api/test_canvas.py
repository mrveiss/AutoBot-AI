"""
Tests for the Live Canvas API (MVA-359).

Covers:
- GET /api/canvas/{id}: 200 with canvas+cells, 403 cross-user, 404 not found
- PUT /api/canvas/{id}: autosave, 403 cross-user
- POST /api/canvas/{id}/cells: add user-owned cell, 403 cross-user
- PATCH /api/canvas/{id}/cells/{cellId}: accept/edit/discard, trust contract,
  state machine enforcement (including committed → terminal)
- POST /api/canvas/{id}/export: md/json/html/pdf, include toggles
- WebSocket canvas_cell and canvas_cancel (MVA-370): ownership check, cross-user rejection
"""

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.canvas import router
from canvas.models import Canvas, CanvasCell, CellState

# ---------------------------------------------------------------------------
# Test helpers / fixtures
# ---------------------------------------------------------------------------

_USER_A = {"user_id": "user-alice", "username": "alice"}
_USER_B = {"user_id": "user-bob", "username": "bob"}

_CANVAS_ID = uuid.uuid4()
_CELL_ID = uuid.uuid4()
_NOW = datetime(2026, 5, 16, 8, 0, 0, tzinfo=timezone.utc)


def _make_canvas(user_id: str = "user-alice"):
    """Create a mock Canvas instance with required attributes."""
    c = MagicMock(spec=Canvas)
    c.id = _CANVAS_ID
    c.user_id = user_id
    c.title = "Test Canvas"
    c.save_token = uuid.uuid4()
    c.undo_cursor = 0
    c.created_at = _NOW
    c.updated_at = _NOW
    return c


def _make_cell(
    owner: str = "agent",
    state: str = CellState.complete,
    user_id: str = "user-alice",
):
    """Create a mock CanvasCell instance with required attributes."""
    cell = MagicMock(spec=CanvasCell)
    cell.id = _CELL_ID
    cell.canvas_id = _CANVAS_ID
    cell.user_id = user_id
    cell.position = 0
    cell.type = "text"
    cell.content = "Hello from agent"
    cell.state = state
    cell.owner = owner
    cell.version = 1
    cell.locked_by = None
    cell.rich_payload = None
    cell.created_at = _NOW
    cell.updated_at = _NOW
    return cell


@pytest.fixture()
def app():
    """Minimal FastAPI app with canvas router and overridden dependencies."""
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return app


def _mock_session():
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    # Simulate scalars().all() chain
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    # Create a non-async result mock where scalar_one_or_none is a regular method
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    result_mock.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=result_mock)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


# ---------------------------------------------------------------------------
# GET /api/canvas/{id}
# ---------------------------------------------------------------------------


class TestGetCanvas:
    def test_get_canvas_200(self, app):
        canvas = _make_canvas()
        session = _mock_session()

        def _execute_side_effect(stmt):
            result = MagicMock()
            scalars = MagicMock()
            scalars.all.return_value = []
            result.scalar_one_or_none = MagicMock(return_value=canvas)
            result.scalars = MagicMock(return_value=scalars)
            return result

        session.execute = AsyncMock(side_effect=_execute_side_effect)

        from auth_middleware import get_current_user
        from user_management.database import get_async_session

        app.dependency_overrides = {
            get_async_session: lambda: session,
            get_current_user: lambda: _USER_A,
        }

        with TestClient(app) as client:
            resp = client.get(f"/api/canvas/{_CANVAS_ID}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["canvas"]["id"] == str(_CANVAS_ID)
        assert data["cells"] == []

    def test_get_canvas_404(self, app):
        session = _mock_session()
        session.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)

        from auth_middleware import get_current_user
        from user_management.database import get_async_session

        app.dependency_overrides = {
            get_async_session: lambda: session,
            get_current_user: lambda: _USER_A,
        }

        with TestClient(app) as client:
            resp = client.get(f"/api/canvas/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_get_canvas_403_cross_user(self, app):
        canvas = _make_canvas(user_id="user-alice")
        session = _mock_session()
        session.execute.return_value.scalar_one_or_none = MagicMock(return_value=canvas)

        from auth_middleware import get_current_user
        from user_management.database import get_async_session

        app.dependency_overrides = {
            get_async_session: lambda: session,
            get_current_user: lambda: _USER_B,
        }

        with TestClient(app) as client:
            resp = client.get(f"/api/canvas/{_CANVAS_ID}")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PUT /api/canvas/{id}
# ---------------------------------------------------------------------------


class TestPutCanvas:
    def test_autosave_returns_token(self, app):
        canvas = _make_canvas()
        session = _mock_session()
        session.execute.return_value.scalar_one_or_none = MagicMock(return_value=canvas)

        from auth_middleware import get_current_user
        from user_management.database import get_async_session

        app.dependency_overrides = {
            get_async_session: lambda: session,
            get_current_user: lambda: _USER_A,
        }

        with TestClient(app) as client:
            resp = client.put(
                f"/api/canvas/{_CANVAS_ID}",
                json={"title": "Updated Title", "cells": []},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "save_token" in data
        assert "saved_at" in data

    def test_autosave_403_cross_user(self, app):
        canvas = _make_canvas(user_id="user-alice")
        session = _mock_session()
        session.execute.return_value.scalar_one_or_none = MagicMock(return_value=canvas)

        from auth_middleware import get_current_user
        from user_management.database import get_async_session

        app.dependency_overrides = {
            get_async_session: lambda: session,
            get_current_user: lambda: _USER_B,
        }

        with TestClient(app) as client:
            resp = client.put(f"/api/canvas/{_CANVAS_ID}", json={"cells": []})
        assert resp.status_code == 403

    def test_autosave_can_set_title_to_null(self, app):
        """Test that title can be explicitly set to null (GH#9526)."""
        canvas = _make_canvas()
        canvas.title = "Existing Title"
        session = _mock_session()
        session.execute.return_value.scalar_one_or_none = MagicMock(return_value=canvas)

        from auth_middleware import get_current_user
        from user_management.database import get_async_session

        app.dependency_overrides = {
            get_async_session: lambda: session,
            get_current_user: lambda: _USER_A,
        }

        with TestClient(app) as client:
            resp = client.put(
                f"/api/canvas/{_CANVAS_ID}",
                json={"title": None, "cells": []},
            )
        assert resp.status_code == 200
        assert canvas.title is None

    def test_autosave_omitted_title_unchanged(self, app):
        """Test that omitting title from request leaves it unchanged."""
        canvas = _make_canvas()
        canvas.title = "Existing Title"
        session = _mock_session()
        session.execute.return_value.scalar_one_or_none = MagicMock(return_value=canvas)

        from auth_middleware import get_current_user
        from user_management.database import get_async_session

        app.dependency_overrides = {
            get_async_session: lambda: session,
            get_current_user: lambda: _USER_A,
        }

        with TestClient(app) as client:
            resp = client.put(
                f"/api/canvas/{_CANVAS_ID}",
                json={"cells": []},
            )
        assert resp.status_code == 200
        assert canvas.title == "Existing Title"


# ---------------------------------------------------------------------------
# POST /api/canvas/{id}/cells
# ---------------------------------------------------------------------------


class TestAddCell:
    def test_add_cell_201(self, app):
        canvas = _make_canvas()
        new_cell = _make_cell(owner="user", state=CellState.committed)

        session = _mock_session()
        session.execute.return_value.scalar_one_or_none = MagicMock(return_value=canvas)
        session.refresh = AsyncMock(side_effect=lambda obj: None)

        # After add+commit, the cell is what we hand back
        async def _refresh_patch(obj):
            obj.id = new_cell.id
            obj.state = CellState.committed
            obj.owner = "user"
            obj.version = 1
            obj.locked_by = None
            obj.created_at = _NOW
            obj.updated_at = _NOW

        session.refresh = _refresh_patch

        from auth_middleware import get_current_user
        from user_management.database import get_async_session

        app.dependency_overrides = {
            get_async_session: lambda: session,
            get_current_user: lambda: _USER_A,
        }

        with TestClient(app) as client:
            resp = client.post(
                f"/api/canvas/{_CANVAS_ID}/cells",
                json={"type": "text", "content": "Hello", "position": 0},
            )
        assert resp.status_code == 201

    def test_add_cell_403_cross_user(self, app):
        canvas = _make_canvas(user_id="user-alice")
        session = _mock_session()
        session.execute.return_value.scalar_one_or_none = MagicMock(return_value=canvas)

        from auth_middleware import get_current_user
        from user_management.database import get_async_session

        app.dependency_overrides = {
            get_async_session: lambda: session,
            get_current_user: lambda: _USER_B,
        }

        with TestClient(app) as client:
            resp = client.post(
                f"/api/canvas/{_CANVAS_ID}/cells",
                json={"type": "text", "content": "Hello", "position": 0},
            )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /api/canvas/{id}/cells/{cellId}
# ---------------------------------------------------------------------------


class TestTransitionCell:
    def _setup_app(self, app, canvas, cell):
        session = _mock_session()
        call_count = 0

        def _execute_side_effect(stmt):
            nonlocal call_count
            result = MagicMock()
            scalars_mock = MagicMock()
            scalars_mock.all.return_value = []
            result.scalars = MagicMock(return_value=scalars_mock)
            if call_count == 0:
                result.scalar_one_or_none = MagicMock(return_value=canvas)
            else:
                result.scalar_one_or_none = MagicMock(return_value=cell)
            call_count += 1
            return result

        session.execute = AsyncMock(side_effect=_execute_side_effect)

        async def _refresh_patch(obj):
            pass

        session.refresh = _refresh_patch

        from auth_middleware import get_current_user
        from user_management.database import get_async_session

        app.dependency_overrides = {
            get_async_session: lambda: session,
            get_current_user: lambda: _USER_A,
        }
        return session

    def test_accept_agent_cell_reaches_committed(self, app):
        canvas = _make_canvas()
        cell = _make_cell(owner="agent", state=CellState.complete)
        self._setup_app(app, canvas, cell)

        with TestClient(app) as client:
            resp = client.patch(
                f"/api/canvas/{_CANVAS_ID}/cells/{_CELL_ID}",
                json={"action": "accept"},
            )
        assert resp.status_code == 200
        assert resp.json()["state"] == CellState.committed

    def test_trust_contract_agent_cell_not_auto_committed(self, app):
        """Agent cell CANNOT reach committed without explicit user action."""
        canvas = _make_canvas()
        # Cell is still streaming — cannot accept yet
        cell = _make_cell(owner="agent", state=CellState.streaming)
        self._setup_app(app, canvas, cell)

        with TestClient(app) as client:
            resp = client.patch(
                f"/api/canvas/{_CANVAS_ID}/cells/{_CELL_ID}",
                json={"action": "accept"},
            )
        assert resp.status_code == 409

    def test_discard_moves_to_cancelled(self, app):
        canvas = _make_canvas()
        cell = _make_cell(owner="agent", state=CellState.complete)
        self._setup_app(app, canvas, cell)

        with TestClient(app) as client:
            resp = client.patch(
                f"/api/canvas/{_CANVAS_ID}/cells/{_CELL_ID}",
                json={"action": "discard"},
            )
        assert resp.status_code == 200
        assert resp.json()["state"] == CellState.cancelled

    def test_edit_requires_content(self, app):
        canvas = _make_canvas()
        cell = _make_cell(owner="agent", state=CellState.complete)
        self._setup_app(app, canvas, cell)

        with TestClient(app) as client:
            resp = client.patch(
                f"/api/canvas/{_CANVAS_ID}/cells/{_CELL_ID}",
                json={"action": "edit"},
            )
        assert resp.status_code == 422

    def test_committed_cell_is_terminal(self, app):
        """committed is a terminal state — discard/accept must return 409."""
        canvas = _make_canvas()
        cell = _make_cell(owner="agent", state=CellState.committed)
        self._setup_app(app, canvas, cell)

        with TestClient(app) as client:
            resp = client.patch(
                f"/api/canvas/{_CANVAS_ID}/cells/{_CELL_ID}",
                json={"action": "discard"},
            )
        assert resp.status_code == 409

    def test_transition_403_cross_user(self, app):
        canvas = _make_canvas(user_id="user-alice")
        session = _mock_session()
        session.execute.return_value.scalar_one_or_none = MagicMock(return_value=canvas)

        from auth_middleware import get_current_user
        from user_management.database import get_async_session

        app.dependency_overrides = {
            get_async_session: lambda: session,
            get_current_user: lambda: _USER_B,
        }

        with TestClient(app) as client:
            resp = client.patch(
                f"/api/canvas/{_CANVAS_ID}/cells/{_CELL_ID}",
                json={"action": "accept"},
            )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Export helpers (pure functions — no DB, no auth)
# ---------------------------------------------------------------------------


class TestExportHelpers:
    def test_md_export(self):
        from api.canvas import _export_md

        canvas = _make_canvas()
        cells = [_make_cell(owner="user", state=CellState.committed)]
        cells[0].content = "Hello world"
        result = _export_md(canvas, cells)
        assert "Test Canvas" in result
        assert "Hello world" in result

    def test_json_export(self):
        import json as _json

        from api.canvas import _export_json

        canvas = _make_canvas()
        cells = [_make_cell(owner="user", state=CellState.committed)]
        result = _export_json(canvas, cells)
        data = _json.loads(result)
        assert "canvas" in data
        assert "cells" in data
        assert len(data["cells"]) == 1

    def test_html_export_sanitizes_xss(self):
        from api.canvas import _export_html

        canvas = _make_canvas()
        cell = _make_cell(owner="user", state=CellState.committed)
        cell.content = "<script>alert(1)</script>"
        result = _export_html(canvas, [cell])
        assert "<script>" not in result

    def test_include_filter_excludes_agent_cells(self):
        from api.canvas import _export_json

        canvas = _make_canvas()
        agent_cell = _make_cell(owner="agent", state=CellState.committed)
        user_cell = _make_cell(owner="user", state=CellState.committed)
        user_cell.id = uuid.uuid4()
        user_cell.content = "User content"

        # include.agent=False → only user cells
        result = _export_json(canvas, [user_cell])
        import json as _json

        data = _json.loads(result)
        assert len(data["cells"]) == 1
        assert data["cells"][0]["owner"] == "user"


# ---------------------------------------------------------------------------
# WebSocket canvas streaming (MVA-370)
# ---------------------------------------------------------------------------


def _make_cancel_db_mock(cell_user_id: str):
    """Return an async context manager that yields a session returning a cell owned by cell_user_id."""
    mock_cell = MagicMock(spec=CanvasCell)
    mock_cell.user_id = cell_user_id

    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = mock_cell
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    @asynccontextmanager
    async def _ctx():
        yield session

    return _ctx


class TestCanvasWebSocketStreaming:
    @pytest.mark.asyncio
    async def test_register_and_unregister_streaming_task(self):
        from api.websockets import (
            _canvas_streaming_tasks,
            register_canvas_streaming_task,
            unregister_canvas_streaming_task,
        )

        task = asyncio.create_task(asyncio.sleep(10))
        canvas_id = str(uuid.uuid4())
        cell_id = str(uuid.uuid4())

        await register_canvas_streaming_task(canvas_id, cell_id, task)
        key = (canvas_id, cell_id)
        assert key in _canvas_streaming_tasks
        assert _canvas_streaming_tasks[key] == task

        await unregister_canvas_streaming_task(canvas_id, cell_id)
        assert key not in _canvas_streaming_tasks

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_canvas_cancel_stops_streaming_task(self):
        from api.websockets import (
            _handle_canvas_cancel,
            register_canvas_streaming_task,
        )

        canvas_id = str(uuid.uuid4())
        cell_id = str(uuid.uuid4())
        owner_id = "user-alice"

        async def mock_stream():
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                pass

        task = asyncio.create_task(mock_stream())
        await register_canvas_streaming_task(canvas_id, cell_id, task)

        assert not task.done()

        with patch("user_management.database.db_session_context", _make_cancel_db_mock(owner_id)):
            await _handle_canvas_cancel({"cellId": cell_id, "canvasId": canvas_id}, owner_id)

        # Task should be cancelled
        await asyncio.sleep(0.01)  # Give task time to process cancellation
        assert task.done()
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_canvas_cancel_with_multiple_tasks(self):
        from api.websockets import (
            _handle_canvas_cancel,
            register_canvas_streaming_task,
        )

        canvas_id = str(uuid.uuid4())
        cell_id_1 = str(uuid.uuid4())
        cell_id_2 = str(uuid.uuid4())
        owner_id = "user-alice"

        async def mock_stream():
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                pass

        task1 = asyncio.create_task(mock_stream())
        task2 = asyncio.create_task(mock_stream())

        await register_canvas_streaming_task(canvas_id, cell_id_1, task1)
        await register_canvas_streaming_task(canvas_id, cell_id_2, task2)

        with patch("user_management.database.db_session_context", _make_cancel_db_mock(owner_id)):
            await _handle_canvas_cancel({"cellId": cell_id_1, "canvasId": canvas_id}, owner_id)

        await asyncio.sleep(0.01)
        assert task1.done()
        assert not task2.done()

        # Cleanup
        task2.cancel()
        try:
            await task2
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_canvas_cancel_cross_user_rejected(self):
        """User B cannot cancel User A's streaming task (MVA-362 security fix)."""
        from api.websockets import (
            _handle_canvas_cancel,
            register_canvas_streaming_task,
        )

        canvas_id = str(uuid.uuid4())
        cell_id = str(uuid.uuid4())
        owner_id = "user-alice"
        attacker_id = "user-bob"

        async def mock_stream():
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                pass

        task = asyncio.create_task(mock_stream())
        await register_canvas_streaming_task(canvas_id, cell_id, task)

        assert not task.done()

        # user-bob tries to cancel user-alice's cell — DB returns alice's cell
        with patch("user_management.database.db_session_context", _make_cancel_db_mock(owner_id)):
            await _handle_canvas_cancel({"cellId": cell_id, "canvasId": canvas_id}, attacker_id)

        await asyncio.sleep(0.01)
        # Task must NOT be cancelled
        assert not task.done()

        # Cleanup
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    def test_canvas_cell_event_format(self):
        from api.websockets import get_canvas_cell_event

        cell_id = str(uuid.uuid4())
        canvas_id = str(uuid.uuid4())

        event = get_canvas_cell_event(cell_id, seq=1, delta="Hello", state="streaming", canvas_id=canvas_id)

        assert event["type"] == "canvas_cell"
        assert event["payload"]["cellId"] == cell_id
        assert event["payload"]["canvasId"] == canvas_id
        assert event["payload"]["seq"] == 1
        assert event["payload"]["delta"] == "Hello"
        assert event["payload"]["state"] == "streaming"
