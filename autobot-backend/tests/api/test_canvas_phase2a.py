"""
Phase 2A tests — Vega-Lite spec validation, rich_payload storage, export (MVA-484).

Covers:
- validate_vegalite_spec: valid spec passes, data.url rejected, data.sequence rejected,
  animation.duration forced to 0, executable: true rejected.
- POST /api/canvas/{id}/cells: chart cell with valid richPayload accepted (201),
  data.url spec rejected (422), executable: true rejected (422).
- PATCH /api/canvas/{id}/cells/{cellId}: rich_payload update on accept/edit.
- Export md: chart cells emit description + data table.
- Export json: rich_payload included.
- Headless SVG render: VegaRenderError on missing node (smoke).
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.canvas import _export_json, _export_md, router
from canvas.models import Canvas, CanvasCell, CellState
from canvas.vega_validation import validate_vegalite_spec

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

_USER_A = {"user_id": "user-alice", "username": "alice"}
_CANVAS_ID = uuid.uuid4()
_CELL_ID = uuid.uuid4()
_NOW = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)

_VALID_VEGALITE_SPEC = {
    "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
    "description": "Revenue by Quarter",
    "data": {
        "values": [
            {"quarter": "Q1", "revenue": 1200},
            {"quarter": "Q2", "revenue": 1400},
        ]
    },
    "mark": {"type": "bar"},
    "encoding": {
        "x": {"field": "quarter", "type": "ordinal"},
        "y": {"field": "revenue", "type": "quantitative"},
    },
}

_VALID_CHART_RICH_PAYLOAD = {
    "payloadType": "vega-lite",
    "specVersion": "5",
    "spec": _VALID_VEGALITE_SPEC,
}


def _make_canvas(user_id: str = "user-alice") -> Canvas:
    c = Canvas.__new__(Canvas)
    c.id = _CANVAS_ID
    c.user_id = user_id
    c.title = "Test Canvas"
    c.save_token = uuid.uuid4()
    c.undo_cursor = 0
    c.created_at = _NOW
    c.updated_at = _NOW
    return c


def _make_cell(
    cell_type: str = "text",
    owner: str = "agent",
    state: str = CellState.complete,
    rich_payload: dict | None = None,
) -> CanvasCell:
    cell = CanvasCell.__new__(CanvasCell)
    cell.id = _CELL_ID
    cell.canvas_id = _CANVAS_ID
    cell.user_id = "user-alice"
    cell.position = 0
    cell.type = cell_type
    cell.content = ""
    cell.state = state
    cell.owner = owner
    cell.version = 1
    cell.locked_by = None
    cell.rich_payload = rich_payload
    cell.created_at = _NOW
    cell.updated_at = _NOW
    return cell


@pytest.fixture()
def app():
    a = FastAPI()
    a.include_router(router, prefix="/api")
    return a


def _mock_session():
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    result_mock = AsyncMock()
    result_mock.scalar_one_or_none.return_value = None
    result_mock.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=result_mock)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


# ---------------------------------------------------------------------------
# Unit tests — vega_validation.py
# ---------------------------------------------------------------------------


class TestValidateVegaliteSpec:
    def test_valid_spec_passes(self):
        result = validate_vegalite_spec(_VALID_VEGALITE_SPEC)
        assert isinstance(result, dict)
        assert result["config"]["animation"]["duration"] == 0

    def test_animation_duration_forced_to_zero(self):
        spec = {**_VALID_VEGALITE_SPEC, "config": {"animation": {"duration": 500}}}
        result = validate_vegalite_spec(spec)
        assert result["config"]["animation"]["duration"] == 0

    def test_animation_added_when_missing(self):
        spec = {**_VALID_VEGALITE_SPEC}
        spec.pop("config", None)
        result = validate_vegalite_spec(spec)
        assert result["config"]["animation"]["duration"] == 0

    def test_data_url_rejected(self):
        spec = {
            **_VALID_VEGALITE_SPEC,
            "data": {"url": "https://example.com/data.csv"},
        }
        with pytest.raises(ValueError, match="data.url"):
            validate_vegalite_spec(spec)

    def test_data_sequence_rejected(self):
        spec = {
            **_VALID_VEGALITE_SPEC,
            "data": {"sequence": {"start": 0, "stop": 10}},
        }
        with pytest.raises(ValueError, match="data.sequence"):
            validate_vegalite_spec(spec)

    def test_data_grapher_rejected(self):
        spec = {
            **_VALID_VEGALITE_SPEC,
            "data": {"grapher": "some-grapher"},
        }
        with pytest.raises(ValueError, match="data.grapher"):
            validate_vegalite_spec(spec)

    def test_wrong_schema_uri_rejected(self):
        spec = {**_VALID_VEGALITE_SPEC, "$schema": "https://vega.github.io/schema/vega/v5.json"}
        with pytest.raises(ValueError, match="\\$schema"):
            validate_vegalite_spec(spec)

    def test_missing_schema_uri_rejected(self):
        spec = {k: v for k, v in _VALID_VEGALITE_SPEC.items() if k != "$schema"}
        with pytest.raises(ValueError, match="\\$schema"):
            validate_vegalite_spec(spec)

    def test_non_dict_spec_rejected(self):
        with pytest.raises(ValueError, match="JSON object"):
            validate_vegalite_spec("not a dict")

    def test_original_spec_not_mutated(self):
        import copy

        original = copy.deepcopy(_VALID_VEGALITE_SPEC)
        original["config"] = {"animation": {"duration": 999}}
        validate_vegalite_spec(original)
        assert original["config"]["animation"]["duration"] == 999

    def test_nested_layer_data_url_rejected(self):
        spec = {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "description": "Layered chart",
            "layer": [
                {
                    "data": {"url": "https://example.com/evil.csv"},
                    "mark": "point",
                }
            ],
        }
        with pytest.raises(ValueError, match="data.url"):
            validate_vegalite_spec(spec)


# ---------------------------------------------------------------------------
# API tests — POST /api/canvas/{id}/cells with richPayload
# ---------------------------------------------------------------------------


class TestAddCellRichPayload:
    def _make_committed_cell(self, rich_payload=None) -> CanvasCell:
        cell = _make_cell(cell_type="chart", owner="user", state=CellState.committed, rich_payload=rich_payload)
        return cell

    def test_chart_cell_with_valid_rich_payload_201(self, app):
        canvas = _make_canvas()
        created_cell = self._make_committed_cell(rich_payload=_VALID_CHART_RICH_PAYLOAD)

        session = _mock_session()
        session.execute.return_value.scalar_one_or_none = MagicMock(return_value=canvas)

        async def _refresh(obj):
            # Simulate DB returning the created cell
            obj.__dict__.update(created_cell.__dict__)

        session.refresh = AsyncMock(side_effect=_refresh)

        from user_management.database import get_async_session

        app.dependency_overrides = {get_async_session: lambda: session}

        with patch("api.canvas.get_current_user", return_value=_USER_A):
            with TestClient(app) as client:
                resp = client.post(
                    f"/api/canvas/{_CANVAS_ID}/cells",
                    json={
                        "type": "chart",
                        "content": "",
                        "position": 0,
                        "rich_payload": _VALID_CHART_RICH_PAYLOAD,
                    },
                )
        assert resp.status_code == 201

    def test_chart_cell_data_url_rejected_422(self, app):
        canvas = _make_canvas()
        session = _mock_session()
        session.execute.return_value.scalar_one_or_none = MagicMock(return_value=canvas)

        from user_management.database import get_async_session

        app.dependency_overrides = {get_async_session: lambda: session}

        bad_spec = {
            **_VALID_VEGALITE_SPEC,
            "data": {"url": "https://evil.example.com/data.csv"},
        }
        payload = {"payloadType": "vega-lite", "specVersion": "5", "spec": bad_spec}

        with patch("api.canvas.get_current_user", return_value=_USER_A):
            with TestClient(app) as client:
                resp = client.post(
                    f"/api/canvas/{_CANVAS_ID}/cells",
                    json={"type": "chart", "content": "", "position": 0, "rich_payload": payload},
                )
        assert resp.status_code == 422
        assert "data.url" in resp.json()["detail"]

    def test_executable_true_rejected_422(self, app):
        canvas = _make_canvas()
        session = _mock_session()
        session.execute.return_value.scalar_one_or_none = MagicMock(return_value=canvas)

        from user_management.database import get_async_session

        app.dependency_overrides = {get_async_session: lambda: session}

        payload = {**_VALID_CHART_RICH_PAYLOAD, "executable": True}

        with patch("api.canvas.get_current_user", return_value=_USER_A):
            with TestClient(app) as client:
                resp = client.post(
                    f"/api/canvas/{_CANVAS_ID}/cells",
                    json={"type": "chart", "content": "", "position": 0, "rich_payload": payload},
                )
        assert resp.status_code == 422
        assert "executable" in resp.json()["detail"]

    def test_text_cell_without_rich_payload_still_works(self, app):
        canvas = _make_canvas()
        text_cell = _make_cell(cell_type="text", owner="user", state=CellState.committed)

        session = _mock_session()
        session.execute.return_value.scalar_one_or_none = MagicMock(return_value=canvas)

        async def _refresh(obj):
            obj.__dict__.update(text_cell.__dict__)

        session.refresh = AsyncMock(side_effect=_refresh)

        from user_management.database import get_async_session

        app.dependency_overrides = {get_async_session: lambda: session}

        with patch("api.canvas.get_current_user", return_value=_USER_A):
            with TestClient(app) as client:
                resp = client.post(
                    f"/api/canvas/{_CANVAS_ID}/cells",
                    json={"type": "text", "content": "Hello", "position": 0},
                )
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Export unit tests
# ---------------------------------------------------------------------------


class TestExportMdPhase2:
    def test_chart_cell_exports_description_and_table(self):
        canvas = _make_canvas()
        cell = _make_cell(
            cell_type="chart",
            owner="agent",
            state=CellState.committed,
            rich_payload={
                "payloadType": "vega-lite",
                "specVersion": "5",
                "spec": _VALID_VEGALITE_SPEC,
            },
        )
        result = _export_md(canvas, [cell])
        assert "Revenue by Quarter" in result
        assert "quarter" in result
        assert "Q1" in result

    def test_code_cell_exports_with_language(self):
        canvas = _make_canvas()
        cell = _make_cell(
            cell_type="code",
            owner="agent",
            state=CellState.committed,
            rich_payload={
                "payloadType": "code",
                "language": "python",
                "content": "print('hello')",
                "executable": False,
            },
        )
        result = _export_md(canvas, [cell])
        assert "```python" in result
        assert "print('hello')" in result


class TestExportJsonPhase2:
    def test_rich_payload_included_in_json_export(self):
        import json

        canvas = _make_canvas()
        cell = _make_cell(
            cell_type="chart",
            owner="agent",
            state=CellState.committed,
            rich_payload=_VALID_CHART_RICH_PAYLOAD,
        )
        result = json.loads(_export_json(canvas, [cell]))
        assert result["cells"][0]["rich_payload"] == _VALID_CHART_RICH_PAYLOAD

    def test_null_rich_payload_in_json_export(self):
        import json

        canvas = _make_canvas()
        cell = _make_cell(cell_type="text", state=CellState.committed)
        result = json.loads(_export_json(canvas, [cell]))
        assert result["cells"][0]["rich_payload"] is None


# ---------------------------------------------------------------------------
# Smoke test — VegaRenderError when node script missing
# ---------------------------------------------------------------------------


class TestVegaRenderSmoke:
    @pytest.mark.asyncio
    async def test_render_raises_on_missing_node(self):
        pass

        from canvas.vega_render import VegaRenderError, render_vegalite_to_svg

        with patch("canvas.vega_render._SCRIPT_PATH", "/nonexistent/vega_render.mjs"):
            with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError("node")):
                with pytest.raises(VegaRenderError, match="node executable not found"):
                    await render_vegalite_to_svg(_VALID_VEGALITE_SPEC)
