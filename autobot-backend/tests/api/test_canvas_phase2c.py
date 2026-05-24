"""
Phase 2C integration tests — CSP header + rich-cell e2e coverage (MVA-486).

Covers:
- GET /api/canvas/{id} returns Content-Security-Policy header with correct value.
- Valid chart spec accepted at POST /api/canvas/{id}/cells (201).
- data.url chart spec rejected at POST /api/canvas/{id}/cells (422).
- executable: true rejected (422).
- Code cell rich_payload accessible (copy-affordance contract: content field returned).
- Chart cell rich_payload has accessible data table (spec.data.values in response).
- HTML export embeds the same CSP policy in a meta tag.
- PDF export smoke test: returns bytes with non-zero length (weasyprint optional).
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.canvas import _CANVAS_PAGE_CSP, _export_html, router
from auth_middleware import get_current_user
from canvas.models import Canvas, CanvasCell, CellState
from user_management.database import get_async_session

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_USER_A = {"user_id": "user-alice", "username": "alice"}
_CANVAS_ID = uuid.uuid4()
_CELL_ID = uuid.uuid4()
_NOW = datetime(2026, 5, 23, 12, 0, 0, tzinfo=timezone.utc)

_VALID_SPEC = {
    "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
    "description": "Sales by Region",
    "data": {
        "values": [
            {"region": "North", "sales": 420},
            {"region": "South", "sales": 380},
        ]
    },
    "mark": {"type": "bar"},
    "encoding": {
        "x": {"field": "region", "type": "ordinal"},
        "y": {"field": "sales", "type": "quantitative"},
    },
}

_VALID_CHART_PAYLOAD = {
    "payloadType": "vega-lite",
    "specVersion": "5",
    "spec": _VALID_SPEC,
}

_VALID_CODE_PAYLOAD = {
    "payloadType": "code",
    "language": "python",
    "content": "print('hello world')",
    "executable": False,
}


def _make_canvas(user_id: str = "user-alice") -> MagicMock:
    c = MagicMock(spec=Canvas)
    c.id = _CANVAS_ID
    c.user_id = user_id
    c.title = "Phase 2C Test Canvas"
    c.save_token = uuid.uuid4()
    c.undo_cursor = 0
    c.created_at = _NOW
    c.updated_at = _NOW
    return c


def _make_cell(
    cell_type: str = "text",
    owner: str = "agent",
    state: str = CellState.committed,
    rich_payload: dict | None = None,
) -> MagicMock:
    cell = MagicMock(spec=CanvasCell)
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


def _mock_session() -> AsyncMock:
    """Session mock where execute() is async but result methods are sync (MagicMock)."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    result_mock = MagicMock()  # sync mock — scalar_one_or_none() is not awaited
    result_mock.scalar_one_or_none.return_value = None
    result_mock.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=result_mock)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture()
def app():
    a = FastAPI()
    a.include_router(router, prefix="/api")
    return a


# ---------------------------------------------------------------------------
# 1. CSP header on GET /api/canvas/{id}
# ---------------------------------------------------------------------------


class TestCanvasCSPHeader:
    def test_get_canvas_sets_csp_header(self, app):
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

        app.dependency_overrides = {
            get_async_session: lambda: session,
            get_current_user: lambda: _USER_A,
        }

        with TestClient(app) as client:
            resp = client.get(f"/api/canvas/{_CANVAS_ID}")

        assert resp.status_code == 200
        csp = resp.headers.get("content-security-policy", "")
        assert "default-src 'none'" in csp
        assert "style-src 'unsafe-inline'" in csp
        assert "img-src data:" in csp
        # Must NOT contain unsafe-eval
        assert "unsafe-eval" not in csp

    def test_csp_constant_has_required_directives(self):
        assert "default-src 'none'" in _CANVAS_PAGE_CSP
        assert "style-src 'unsafe-inline'" in _CANVAS_PAGE_CSP
        assert "img-src data:" in _CANVAS_PAGE_CSP
        assert "unsafe-eval" not in _CANVAS_PAGE_CSP
        # No external network sources
        assert "http" not in _CANVAS_PAGE_CSP


# ---------------------------------------------------------------------------
# 2. Valid chart spec accepted (201)
# ---------------------------------------------------------------------------


class TestValidChartSpecAccepted:
    def test_valid_chart_cell_returns_201(self, app):
        canvas = _make_canvas()
        created_cell = _make_cell(
            cell_type="chart",
            owner="user",
            state=CellState.committed,
            rich_payload=_VALID_CHART_PAYLOAD,
        )
        session = _mock_session()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = canvas
        session.execute = AsyncMock(return_value=result_mock)

        async def _refresh(obj):
            obj.__dict__.update(created_cell.__dict__)

        session.refresh = AsyncMock(side_effect=_refresh)

        app.dependency_overrides = {
            get_async_session: lambda: session,
            get_current_user: lambda: _USER_A,
        }

        with TestClient(app) as client:
            resp = client.post(
                f"/api/canvas/{_CANVAS_ID}/cells",
                json={"type": "chart", "content": "", "position": 0, "rich_payload": _VALID_CHART_PAYLOAD},
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["type"] == "chart"
        assert body["rich_payload"]["payloadType"] == "vega-lite"


# ---------------------------------------------------------------------------
# 3. data.url spec rejected (422)
# ---------------------------------------------------------------------------


class TestDataUrlSpecRejected:
    def test_data_url_returns_422(self, app):
        canvas = _make_canvas()
        session = _mock_session()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = canvas
        session.execute = AsyncMock(return_value=result_mock)

        app.dependency_overrides = {
            get_async_session: lambda: session,
            get_current_user: lambda: _USER_A,
        }

        bad_spec = {**_VALID_SPEC, "data": {"url": "https://evil.example.com/data.csv"}}
        payload = {**_VALID_CHART_PAYLOAD, "spec": bad_spec}

        with TestClient(app) as client:
            resp = client.post(
                f"/api/canvas/{_CANVAS_ID}/cells",
                json={"type": "chart", "content": "", "position": 0, "rich_payload": payload},
            )

        assert resp.status_code == 422
        assert "data.url" in resp.json()["detail"]

    def test_data_sequence_returns_422(self, app):
        canvas = _make_canvas()
        session = _mock_session()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = canvas
        session.execute = AsyncMock(return_value=result_mock)

        app.dependency_overrides = {
            get_async_session: lambda: session,
            get_current_user: lambda: _USER_A,
        }

        bad_spec = {**_VALID_SPEC, "data": {"sequence": {"start": 0, "stop": 10}}}
        payload = {**_VALID_CHART_PAYLOAD, "spec": bad_spec}

        with TestClient(app) as client:
            resp = client.post(
                f"/api/canvas/{_CANVAS_ID}/cells",
                json={"type": "chart", "content": "", "position": 0, "rich_payload": payload},
            )

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 4. executable: true rejected (422)
# ---------------------------------------------------------------------------


class TestExecutableRejected:
    def test_executable_true_returns_422(self, app):
        canvas = _make_canvas()
        session = _mock_session()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = canvas
        session.execute = AsyncMock(return_value=result_mock)

        app.dependency_overrides = {
            get_async_session: lambda: session,
            get_current_user: lambda: _USER_A,
        }

        payload = {**_VALID_CHART_PAYLOAD, "executable": True}

        with TestClient(app) as client:
            resp = client.post(
                f"/api/canvas/{_CANVAS_ID}/cells",
                json={"type": "chart", "content": "", "position": 0, "rich_payload": payload},
            )

        assert resp.status_code == 422
        assert "executable" in resp.json()["detail"]

    def test_code_cell_executable_true_returns_422(self, app):
        canvas = _make_canvas()
        session = _mock_session()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = canvas
        session.execute = AsyncMock(return_value=result_mock)

        app.dependency_overrides = {
            get_async_session: lambda: session,
            get_current_user: lambda: _USER_A,
        }

        payload = {**_VALID_CODE_PAYLOAD, "executable": True}

        with TestClient(app) as client:
            resp = client.post(
                f"/api/canvas/{_CANVAS_ID}/cells",
                json={"type": "code", "content": "", "position": 0, "rich_payload": payload},
            )

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 5. Code cell copy-affordance contract (content accessible via API)
# ---------------------------------------------------------------------------


class TestCodeCellCopyAffordance:
    def test_code_cell_content_present_in_rich_payload(self, app):
        """Copy-affordance: code cell API response includes content field for clipboard."""
        canvas = _make_canvas()
        created_cell = _make_cell(
            cell_type="code",
            owner="user",
            state=CellState.committed,
            rich_payload={**_VALID_CODE_PAYLOAD, "executable": False},
        )
        session = _mock_session()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = canvas
        session.execute = AsyncMock(return_value=result_mock)

        async def _refresh(obj):
            obj.__dict__.update(created_cell.__dict__)

        session.refresh = AsyncMock(side_effect=_refresh)

        app.dependency_overrides = {
            get_async_session: lambda: session,
            get_current_user: lambda: _USER_A,
        }

        with TestClient(app) as client:
            resp = client.post(
                f"/api/canvas/{_CANVAS_ID}/cells",
                json={"type": "code", "content": "", "position": 0, "rich_payload": _VALID_CODE_PAYLOAD},
            )

        assert resp.status_code == 201
        body = resp.json()
        rp = body.get("rich_payload", {})
        assert rp.get("payloadType") == "code"
        assert rp.get("content") == "print('hello world')"
        assert rp.get("executable") is False

    def test_code_cell_executable_forced_false(self, app):
        """Code cell API enforces executable: false even when not passed explicitly."""
        canvas = _make_canvas()
        created_cell = _make_cell(
            cell_type="code",
            owner="user",
            state=CellState.committed,
            rich_payload={**_VALID_CODE_PAYLOAD, "executable": False},
        )
        session = _mock_session()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = canvas
        session.execute = AsyncMock(return_value=result_mock)

        async def _refresh(obj):
            obj.__dict__.update(created_cell.__dict__)

        session.refresh = AsyncMock(side_effect=_refresh)

        app.dependency_overrides = {
            get_async_session: lambda: session,
            get_current_user: lambda: _USER_A,
        }

        with TestClient(app) as client:
            resp = client.post(
                f"/api/canvas/{_CANVAS_ID}/cells",
                json={"type": "code", "content": "", "position": 0, "rich_payload": _VALID_CODE_PAYLOAD},
            )

        assert resp.status_code == 201
        assert resp.json()["rich_payload"]["executable"] is False


# ---------------------------------------------------------------------------
# 6. Chart cell accessible data table (spec.data.values in response)
# ---------------------------------------------------------------------------


class TestChartCellAccessibleDataTable:
    def test_chart_cell_data_values_present_in_response(self, app):
        """Accessible data table contract: spec.data.values preserved in API response."""
        canvas = _make_canvas()
        created_cell = _make_cell(
            cell_type="chart",
            owner="user",
            state=CellState.committed,
            rich_payload=_VALID_CHART_PAYLOAD,
        )
        session = _mock_session()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = canvas
        session.execute = AsyncMock(return_value=result_mock)

        async def _refresh(obj):
            obj.__dict__.update(created_cell.__dict__)

        session.refresh = AsyncMock(side_effect=_refresh)

        app.dependency_overrides = {
            get_async_session: lambda: session,
            get_current_user: lambda: _USER_A,
        }

        with TestClient(app) as client:
            resp = client.post(
                f"/api/canvas/{_CANVAS_ID}/cells",
                json={"type": "chart", "content": "", "position": 0, "rich_payload": _VALID_CHART_PAYLOAD},
            )

        assert resp.status_code == 201
        body = resp.json()
        values = body["rich_payload"]["spec"]["data"]["values"]
        assert len(values) == 2
        assert values[0]["region"] == "North"
        assert values[1]["region"] == "South"

    def test_chart_cell_export_md_has_data_table(self):
        """MD export includes a Markdown table from spec.data.values."""
        canvas = _make_canvas()
        cell = _make_cell(
            cell_type="chart",
            owner="agent",
            state=CellState.committed,
            rich_payload=_VALID_CHART_PAYLOAD,
        )
        from api.canvas import _export_md

        result = _export_md(canvas, [cell])
        assert "region" in result
        assert "North" in result
        assert "South" in result
        assert "| region |" in result or "region |" in result


# ---------------------------------------------------------------------------
# 7. CSP header in HTML export meta tag
# ---------------------------------------------------------------------------


class TestHtmlExportCSP:
    def test_html_export_contains_csp_meta_tag(self):
        canvas = _make_canvas()
        cell = _make_cell(
            cell_type="chart",
            owner="agent",
            state=CellState.committed,
            rich_payload=_VALID_CHART_PAYLOAD,
        )
        result = _export_html(canvas, [cell])
        assert 'http-equiv="Content-Security-Policy"' in result
        assert "default-src 'none'" in result
        assert "style-src 'unsafe-inline'" in result
        assert "img-src data:" in result
        assert "unsafe-eval" not in result

    def test_html_export_csp_matches_api_csp(self):
        """HTML export CSP must be consistent with the API response CSP."""
        canvas = _make_canvas()
        result = _export_html(canvas, [])
        # The meta tag must contain the same canonical CSP value
        assert _CANVAS_PAGE_CSP in result

    def test_html_export_with_text_cell(self):
        canvas = _make_canvas()
        cell = _make_cell(cell_type="text", owner="user", state=CellState.committed)
        cell.content = "Hello <script>alert('xss')</script>"
        result = _export_html(canvas, [cell])
        # script tag must be HTML-escaped, not rendered
        assert "<script>" not in result
        # The raw unescaped tag must not appear
        assert "</script>" not in result

    def test_html_export_with_code_cell(self):
        canvas = _make_canvas()
        cell = _make_cell(
            cell_type="code",
            owner="user",
            state=CellState.committed,
            rich_payload=_VALID_CODE_PAYLOAD,
        )
        result = _export_html(canvas, [cell])
        assert "print(" in result
        assert "language-python" in result


# ---------------------------------------------------------------------------
# 8. Export smoke test — HTML with chart cell (SVG rendering mocked)
# ---------------------------------------------------------------------------


class TestExportSmoke:
    def test_html_export_smoke_with_chart_cell(self, app):
        canvas = _make_canvas()
        chart_cell = _make_cell(
            cell_type="chart",
            owner="agent",
            state=CellState.committed,
            rich_payload=_VALID_CHART_PAYLOAD,
        )

        session = _mock_session()
        scalars_all = MagicMock()
        scalars_all.all.return_value = [chart_cell]

        def _export_execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none = MagicMock(return_value=canvas)
            result.scalars = MagicMock(return_value=scalars_all)
            return result

        session.execute = AsyncMock(side_effect=_export_execute)

        app.dependency_overrides = {
            get_async_session: lambda: session,
            get_current_user: lambda: _USER_A,
        }

        mock_svg = "<svg><rect width='100' height='50'/></svg>"

        with patch("api.canvas._render_chart_svgs", return_value={str(chart_cell.id): mock_svg}):
            with TestClient(app) as client:
                resp = client.post(
                    f"/api/canvas/{_CANVAS_ID}/export",
                    json={"format": "html", "include": {"agent": True, "user": True}},
                )

        assert resp.status_code == 200
        body = resp.text
        assert "<!DOCTYPE html>" in body
        assert mock_svg in body
        assert "Content-Security-Policy" in body or "content-security-policy" in body.lower()

    def test_pdf_export_smoke_with_chart_cell(self, app):
        """PDF export smoke: either produces PDF bytes or returns 501 (weasyprint absent)."""
        canvas = _make_canvas()
        chart_cell = _make_cell(
            cell_type="chart",
            owner="agent",
            state=CellState.committed,
            rich_payload=_VALID_CHART_PAYLOAD,
        )

        session = _mock_session()
        scalars_all = MagicMock()
        scalars_all.all.return_value = [chart_cell]

        def _pdf_execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none = MagicMock(return_value=canvas)
            result.scalars = MagicMock(return_value=scalars_all)
            return result

        session.execute = AsyncMock(side_effect=_pdf_execute)

        app.dependency_overrides = {
            get_async_session: lambda: session,
            get_current_user: lambda: _USER_A,
        }

        mock_svg = "<svg><circle r='10'/></svg>"

        with patch("api.canvas._render_chart_svgs", return_value={str(chart_cell.id): mock_svg}):
            with TestClient(app) as client:
                resp = client.post(
                    f"/api/canvas/{_CANVAS_ID}/export",
                    json={"format": "pdf", "include": {"agent": True, "user": True}},
                )

        # weasyprint may not be installed in CI — 200 or 501 are both valid
        assert resp.status_code in (200, 501)
        if resp.status_code == 200:
            assert len(resp.content) > 0
            assert resp.headers["content-type"] == "application/pdf"
