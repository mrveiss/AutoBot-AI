# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for the project timeline / Gantt helpers + endpoint (GH#9020)."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from llc.services.timeline import compute_critical_path, duration_days


def _dt(day: int) -> datetime:
    return datetime(2026, 6, day, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# duration_days
# --------------------------------------------------------------------------- #


class TestDurationDays:
    def test_spans_whole_days(self):
        assert duration_days(_dt(1), _dt(4)) == 3.0

    def test_fractional_day(self):
        start = datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
        assert duration_days(start, end) == 0.5

    def test_missing_dates_default_to_one(self):
        assert duration_days(None, None) == 1.0
        assert duration_days(_dt(1), None) == 1.0
        assert duration_days(None, _dt(4)) == 1.0

    def test_end_before_start_defaults_to_one(self):
        assert duration_days(_dt(4), _dt(1)) == 1.0


# --------------------------------------------------------------------------- #
# compute_critical_path
# --------------------------------------------------------------------------- #


class TestCriticalPath:
    def test_empty(self):
        assert compute_critical_path({}, []) == set()

    def test_single_node(self):
        assert compute_critical_path({"A": 3}, []) == {"A"}

    def test_longest_chain_wins(self):
        # A→B→C (1+5+1=7) vs standalone D (2) → chain is critical
        durations = {"A": 1, "B": 5, "C": 1, "D": 2}
        edges = [("A", "B"), ("B", "C")]
        assert compute_critical_path(durations, edges) == {"A", "B", "C"}

    def test_picks_heavier_of_two_branches(self):
        # root→{heavy(10), light(2)} → root + heavy
        durations = {"root": 1, "heavy": 10, "light": 2}
        edges = [("root", "heavy"), ("root", "light")]
        assert compute_critical_path(durations, edges) == {"root", "heavy"}

    def test_diamond(self):
        # A→B→D and A→C→D; B=5,C=2 → critical path A,B,D
        durations = {"A": 1, "B": 5, "C": 2, "D": 1}
        edges = [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")]
        assert compute_critical_path(durations, edges) == {"A", "B", "D"}

    def test_unknown_node_edges_ignored(self):
        durations = {"A": 1, "B": 2}
        edges = [("A", "B"), ("A", "GHOST"), ("GHOST", "B")]
        assert compute_critical_path(durations, edges) == {"A", "B"}

    def test_self_edge_ignored(self):
        assert compute_critical_path({"A": 1}, [("A", "A")]) == {"A"}

    def test_cycle_tolerated(self):
        # A→B→A cycle plus a heavier standalone C → must not hang, returns a set
        durations = {"A": 1, "B": 1, "C": 5}
        edges = [("A", "B"), ("B", "A")]
        result = compute_critical_path(durations, edges)
        assert result == {"C"}


# --------------------------------------------------------------------------- #
# GET /projects/{id}/timeline endpoint
# --------------------------------------------------------------------------- #


def _make_item(identifier, project_id, *, start=None, end=None):
    item = MagicMock()
    item.id = uuid.uuid4()
    item.identifier = identifier
    item.title = f"Item {identifier}"
    item.type = "task"
    item.status = "in_progress"
    item.project_id = project_id
    item.assignee_agent_id = None
    item.assignee_user_id = None
    item.scheduled_start = start
    item.scheduled_end = end
    item.started_at = None
    item.completed_at = None
    return item


def _make_relation(source_id, target_id):
    from llc.models.enums import WorkItemRelationType  # noqa: PLC0415

    rel = MagicMock()
    rel.source_id = source_id
    rel.target_id = target_id
    rel.relation_type = WorkItemRelationType.BLOCKED_BY
    return rel


def _timeline_app(project, items, relations):
    """FastAPI app whose session returns project, then items, then relations
    across the three sequential execute() calls the endpoint makes."""
    from llc.api.sprints import router  # noqa: PLC0415
    from user_management.database import get_async_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(router)

    def _scalar_result(value):
        r = MagicMock()
        r.scalar_one_or_none.return_value = value
        return r

    def _scalars_result(seq):
        r = MagicMock()
        r.scalars.return_value = seq
        return r

    results = [
        _scalar_result(project),
        _scalars_result(items),
        _scalars_result(relations),
    ]
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=results)

    async def _fake_session():
        yield session

    app.dependency_overrides[get_async_session] = _fake_session
    return app


class TestTimelineEndpoint:
    def test_project_not_found(self):
        app = _timeline_app(None, [], [])
        resp = TestClient(app).get(f"/projects/{uuid.uuid4()}/timeline")
        assert resp.status_code == 404

    def test_items_and_critical_path(self):
        pid = uuid.uuid4()
        a = _make_item("WI-A", pid, start=_dt(1), end=_dt(2))
        b = _make_item("WI-B", pid, start=_dt(2), end=_dt(9))  # heavy
        c = _make_item("WI-C", pid, start=_dt(2), end=_dt(3))  # light parallel
        project = MagicMock(id=pid)
        # B blocked_by A → edge A→B ; C blocked_by A → edge A→C
        rels = [_make_relation(b.id, a.id), _make_relation(c.id, a.id)]
        app = _timeline_app(project, [a, b, c], rels)

        resp = TestClient(app).get(f"/projects/{pid}/timeline")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == str(pid)
        assert len(data["items"]) == 3
        assert len(data["edges"]) == 2
        crit = {i["identifier"] for i in data["items"] if i["on_critical_path"]}
        assert crit == {"WI-A", "WI-B"}  # heavier branch
        # edge direction: blocker (A) → blocked (B)
        edge = next(e for e in data["edges"] if e["to_id"] == str(b.id))
        assert edge["from_id"] == str(a.id)

    def test_empty_project(self):
        pid = uuid.uuid4()
        app = _timeline_app(MagicMock(id=pid), [], [])
        resp = TestClient(app).get(f"/projects/{pid}/timeline")
        assert resp.status_code == 200
        assert resp.json()["items"] == []
        assert resp.json()["edges"] == []
