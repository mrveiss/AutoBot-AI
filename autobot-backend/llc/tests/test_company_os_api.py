# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Company OS model API, end to end on SQLite (#18390).

Real routers, real services, real tables. Only the session factory and the two
auth dependencies are replaced, so the tenancy under test is the production path:
``require_org_context`` -> ``ctx.org_id`` -> a ``company_id`` predicate in the SQL.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.user_management.dependencies import get_current_user, require_org_context
from llc.api.company_os import router as company_os_router
from llc.api.company_os_skills import router as skills_router
from llc.deps import get_session
from llc.models.company_os import LLCProcess, LLCRoleSkill, LLCWorkflowNode, LLCWorkflowTransition
from llc.models.enums import MembershipRole
from llc.models.membership import LLCCompanyMembership
from llc.services.company_os.graph_types import GraphSpec
from llc.services.workflow import WorkflowService

# Registers the SQLite compile shims for postgresql.JSONB / postgresql.UUID.
from llc.tests import _e2e_harness as harness
from models.workflow import Workflow
from user_management.models.base import Base
from user_management.models.role import Role
from user_management.services import TenantContext

COMPANY_A, COMPANY_B = uuid.uuid4(), uuid.uuid4()
ADMIN_A, ADMIN_B, MEMBER_A = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
PREFIX = "/api/llc/company-os"
_TABLES = [
    Role.__table__,
    Workflow.__table__,
    LLCProcess.__table__,
    LLCWorkflowNode.__table__,
    LLCWorkflowTransition.__table__,
    LLCRoleSkill.__table__,
    LLCCompanyMembership.__table__,
]


@pytest_asyncio.fixture
async def factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine (test-local)
    for table in _TABLES:
        harness._scrub_pg_server_defaults(table)
        harness._clientside_timestamps(table)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    maker = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with maker() as s:
        for company, user, role in (
            (COMPANY_A, ADMIN_A, MembershipRole.ADMIN),
            (COMPANY_B, ADMIN_B, MembershipRole.ADMIN),
            (COMPANY_A, MEMBER_A, MembershipRole.MEMBER),
        ):
            s.add(LLCCompanyMembership(id=uuid.uuid4(), company_id=company, user_id=user, role=role.value))
        await s.commit()
    yield maker
    await engine.dispose()


def _client(maker, company: uuid.UUID, user: uuid.UUID) -> httpx.AsyncClient:
    app = FastAPI()
    app.include_router(company_os_router, prefix="/api/llc")
    app.include_router(skills_router, prefix="/api/llc")

    async def _session():
        async with maker() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(user)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=company, user_id=user, is_platform_admin=False
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def _role(maker, company: uuid.UUID, name: str) -> uuid.UUID:
    async with maker() as s:
        role = Role(id=uuid.uuid4(), org_id=company, name=name)
        s.add(role)
        await s.commit()
        return role.id


async def _post(c, path, **body):
    return await c.post(f"{PREFIX}{path}", json=body)


GRAPH = {
    "nodes": [
        {"key": "s", "kind": "start"},
        {"key": "a", "kind": "process", "process_key": "p1"},
        {"key": "ok", "kind": "end", "end_outcome": "done"},
        {"key": "bad", "kind": "end", "end_outcome": "failed"},
    ],
    "transitions": [
        {"from_node": "s", "kind": "success", "to_node": "a"},
        {"from_node": "a", "kind": "success", "to_node": "ok"},
        {"from_node": "a", "kind": "failure", "to_node": "bad", "retry_max": 3},
    ],
}


@pytest_asyncio.fixture
async def seeded(factory):
    """Company A: two roles, one process, one workflow per role."""
    sales, ops = await _role(factory, COMPANY_A, "Sales"), await _role(factory, COMPANY_A, "Ops")
    async with _client(factory, COMPANY_A, ADMIN_A) as c:
        assert (
            await _post(
                c, "/processes", process_key="p1", name="Qualify", owner_role_id=str(sales), required_skills=["sql"]
            )
        ).status_code == 201
        for wid, role in (("sales-wf", sales), ("ops-wf", ops)):
            assert (await _post(c, "/workflows", workflow_id=wid, owner_role_id=str(role))).status_code == 201
    return {"sales": sales, "ops": ops}


async def test_graph_round_trips_in_authored_order(factory, seeded):
    async with _client(factory, COMPANY_A, ADMIN_A) as c:
        put = await c.put(f"{PREFIX}/workflows/sales-wf/graph", json=GRAPH)
        assert put.status_code == 200, put.text
        got = (await c.get(f"{PREFIX}/workflows/sales-wf/graph")).json()
    assert [n["key"] for n in got["graph"]["nodes"]] == ["s", "a", "ok", "bad"]
    assert got["graph"]["transitions"][2] == {
        "from_node": "a",
        "kind": "failure",
        "to_node": "bad",
        "retry_max": 3,
        "condition": None,
        "timeout_seconds": None,
        "handoff_workflow_id": None,
    }
    assert got["validation"]["errors"] == []


async def test_malformed_graph_is_rejected_and_not_stored(factory, seeded):
    bad = {"nodes": [{"key": "s", "kind": "start"}], "transitions": []}
    async with _client(factory, COMPANY_A, ADMIN_A) as c:
        assert (await c.put(f"{PREFIX}/workflows/sales-wf/graph", json=GRAPH)).status_code == 200
        res = await c.put(f"{PREFIX}/workflows/sales-wf/graph", json=bad)
        assert res.status_code == 422 and res.json()["detail"]["errors"]
        assert len((await c.get(f"{PREFIX}/workflows/sales-wf/graph")).json()["graph"]["nodes"]) == 4


async def test_untyped_transition_is_a_422(factory, seeded):
    bad = {**GRAPH, "transitions": [{"from_node": "s", "kind": "sometimes", "to_node": "a"}]}
    async with _client(factory, COMPANY_A, ADMIN_A) as c:
        assert (await c.put(f"{PREFIX}/workflows/sales-wf/graph", json=bad)).status_code == 422


async def test_cross_role_handoff_is_a_transition_visible_from_both_sides(factory, seeded):
    ops_graph = {
        "nodes": [{"key": "s", "kind": "start"}, {"key": "ok", "kind": "end", "end_outcome": "done"}],
        "transitions": [{"from_node": "s", "kind": "success", "to_node": "ok"}],
    }
    sales_graph = {
        **GRAPH,
        "transitions": GRAPH["transitions"] + [{"from_node": "ok", "kind": "handoff", "handoff_workflow_id": "ops-wf"}],
    }
    async with _client(factory, COMPANY_A, ADMIN_A) as c:
        assert (await c.put(f"{PREFIX}/workflows/ops-wf/graph", json=ops_graph)).status_code == 200
        assert (await c.put(f"{PREFIX}/workflows/sales-wf/graph", json=sales_graph)).status_code == 200
        got = (await c.get(f"{PREFIX}/workflows/sales-wf/graph")).json()["graph"]["transitions"]
        assert got[-1]["kind"] == "handoff" and got[-1]["handoff_workflow_id"] == "ops-wf"
        # Each role's workflow is still owned by that role.
        owners = {w["workflow_id"]: w["owner_role_id"] for w in (await c.get(f"{PREFIX}/workflows")).json()}
        assert owners == {"sales-wf": str(seeded["sales"]), "ops-wf": str(seeded["ops"])}
        # A referenced handoff target cannot be deleted from under the handoff.
        assert (await c.delete(f"{PREFIX}/workflows/ops-wf")).status_code == 409
        # Re-owning it to the sender's role would make the handoff stay inside one role.
        res = await c.patch(f"{PREFIX}/workflows/ops-wf", json={"owner_role_id": str(seeded["sales"])})
        assert res.status_code == 409


async def test_handoff_within_one_role_or_to_nowhere_is_rejected(factory, seeded):
    async with _client(factory, COMPANY_A, ADMIN_A) as c:
        await _post(c, "/workflows", workflow_id="sales-wf-2", owner_role_id=str(seeded["sales"]))
        for target in ("sales-wf-2", "ghost"):
            g = {
                **GRAPH,
                "transitions": GRAPH["transitions"]
                + [{"from_node": "ok", "kind": "handoff", "handoff_workflow_id": target}],
            }
            res = await c.put(f"{PREFIX}/workflows/sales-wf/graph", json=g)
            assert res.status_code == 422, (target, res.text)


async def test_company_a_cannot_see_or_edit_company_b(factory, seeded):
    role_b = await _role(factory, COMPANY_B, "Sales")
    async with _client(factory, COMPANY_B, ADMIN_B) as b:
        assert (
            await _post(b, "/processes", process_key="p1", name="B proc", owner_role_id=str(role_b))
        ).status_code == 201
        assert (await _post(b, "/workflows", workflow_id="b-wf", owner_role_id=str(role_b))).status_code == 201
        assert (await _post(b, "/workflows", workflow_id="b-meta", kind="meta_skill")).status_code == 201
    async with _client(factory, COMPANY_A, ADMIN_A) as a:
        assert "b-wf" not in {w["workflow_id"] for w in (await a.get(f"{PREFIX}/workflows")).json()}
        for method, path, body in (
            ("get", "/workflows/b-wf", None),
            ("patch", "/workflows/b-wf", {"name": "x"}),
            ("delete", "/workflows/b-wf", None),
            ("get", "/workflows/b-wf/graph", None),
            ("put", "/workflows/b-wf/graph", GRAPH),
            ("get", "/workflows/b-wf/validation", None),
            ("get", f"/roles/{role_b}/skills", None),
        ):
            res = await a.request(method.upper(), f"{PREFIX}{path}", json=body)
            assert res.status_code == 404, (method, path, res.status_code)
        # B's role id, B's meta skill and B's workflow cannot be referenced from A.
        assert (await _post(a, "/processes", process_key="px", name="x", owner_role_id=str(role_b))).status_code == 404
        assert (await _post(a, "/workflows", workflow_id="wx", owner_role_id=str(role_b))).status_code == 404
        sales = seeded["sales"]
        assert (await _post(a, f"/roles/{sales}/skills", meta_skill_id="b-meta")).status_code == 404
        g = {
            **GRAPH,
            "transitions": GRAPH["transitions"]
            + [{"from_node": "ok", "kind": "handoff", "handoff_workflow_id": "b-wf"}],
        }
        assert (await a.put(f"{PREFIX}/workflows/sales-wf/graph", json=g)).status_code == 422
        # A's own p1 is untouched by B's p1 of the same key.
        assert (await a.get(f"{PREFIX}/processes/p1")).json()["name"] == "Qualify"
    async with _client(factory, COMPANY_B, ADMIN_B) as b:
        assert (await b.get(f"{PREFIX}/workflows/b-wf")).status_code == 200
        assert (await b.get(f"{PREFIX}/workflows/sales-wf")).status_code == 404


async def test_company_is_never_taken_from_the_request(factory, seeded):
    async with _client(factory, COMPANY_A, ADMIN_A) as a:
        for route in a._transport.app.routes:  # type: ignore[attr-defined]
            assert "company" not in getattr(route, "path", ""), route.path
        res = await a.get(f"{PREFIX}/workflows", params={"company_id": str(COMPANY_B)})
        assert {w["workflow_id"] for w in res.json()} == {"sales-wf", "ops-wf"}


async def test_writes_need_company_admin(factory, seeded):
    async with _client(factory, COMPANY_A, MEMBER_A) as member:
        assert (await member.get(f"{PREFIX}/workflows")).status_code == 200
        assert (
            await _post(member, "/workflows", workflow_id="w", owner_role_id=str(seeded["sales"]))
        ).status_code == 403
        assert (await member.put(f"{PREFIX}/workflows/sales-wf/graph", json=GRAPH)).status_code == 403
        assert (await _post(member, f"/roles/{seeded['sales']}/skills", skill_name="sql")).status_code == 403


async def test_meta_skill_has_no_owner_and_no_trigger(factory, seeded):
    async with _client(factory, COMPANY_A, ADMIN_A) as c:
        assert (
            await _post(c, "/workflows", workflow_id="m", kind="meta_skill", owner_role_id=str(seeded["sales"]))
        ).status_code == 400
        assert (
            await _post(c, "/workflows", workflow_id="m", kind="meta_skill", trigger_type="manual")
        ).status_code == 400
        ok = await _post(c, "/workflows", workflow_id="m", kind="meta_skill")
        assert ok.status_code == 201 and ok.json()["owner_role_id"] is None and ok.json()["trigger_type"] is None
        assert (await c.patch(f"{PREFIX}/workflows/m", json={"owner_role_id": str(seeded["sales"])})).status_code == 400
        assert [
            w["workflow_id"] for w in (await c.get(f"{PREFIX}/workflows", params={"kind": "meta_skill"})).json()
        ] == ["m"]


async def test_workflow_needs_an_owner_role_and_one_valid_trigger(factory, seeded):
    async with _client(factory, COMPANY_A, ADMIN_A) as c:
        assert (await _post(c, "/workflows", workflow_id="w")).status_code == 400
        for trig in (
            {"trigger_type": "carrier_pigeon"},
            {"trigger_type": "work_item_status"},
            {"trigger_type": "process_result", "trigger_config": {"process_key": "nope", "result": "success"}},
        ):
            res = await _post(c, "/workflows", workflow_id="w", owner_role_id=str(seeded["sales"]), **trig)
            assert res.status_code in (400, 404), (trig, res.text)
        res = await _post(
            c,
            "/workflows",
            workflow_id="w",
            owner_role_id=str(seeded["sales"]),
            trigger_type="process_result",
            trigger_config={"process_key": "p1", "result": "failure"},
        )
        assert res.status_code == 201 and res.json()["trigger_type"] == "process_result"
        assert (await _post(c, "/workflows", workflow_id="w", owner_role_id=str(seeded["sales"]))).status_code == 409
        # p1 is the source of a trigger, so it cannot be deleted.
        assert (await c.delete(f"{PREFIX}/processes/p1")).status_code == 409


async def test_skills_held_through_a_meta_skill_name_their_source(factory, seeded):
    sales = seeded["sales"]
    inner_graph = {
        "nodes": [
            {"key": "s", "kind": "start"},
            {"key": "a", "kind": "process", "process_key": "p1"},
            {"key": "e", "kind": "end", "end_outcome": "done"},
        ],
        "transitions": [
            {"from_node": "s", "kind": "success", "to_node": "a"},
            {"from_node": "a", "kind": "success", "to_node": "e"},
        ],
    }
    outer_graph = {
        "nodes": [
            {"key": "s", "kind": "start"},
            {"key": "m", "kind": "meta_skill", "meta_skill_id": "inner"},
            {"key": "e", "kind": "end", "end_outcome": "done"},
        ],
        "transitions": [
            {"from_node": "s", "kind": "success", "to_node": "m"},
            {"from_node": "m", "kind": "success", "to_node": "e"},
        ],
    }
    async with _client(factory, COMPANY_A, ADMIN_A) as c:
        await _post(c, "/workflows", workflow_id="inner", kind="meta_skill", name="Inner")
        await _post(c, "/workflows", workflow_id="outer", kind="meta_skill", name="Outer")
        assert (await c.put(f"{PREFIX}/workflows/inner/graph", json=inner_graph)).status_code == 200
        assert (await c.put(f"{PREFIX}/workflows/outer/graph", json=outer_graph)).status_code == 200
        assert (await _post(c, f"/roles/{sales}/skills", skill_name="excel")).status_code == 201
        grant = await _post(c, f"/roles/{sales}/skills", meta_skill_id="outer")
        assert grant.status_code == 201
        assert (await _post(c, f"/roles/{sales}/skills", meta_skill_id="outer")).status_code == 409
        assert (await _post(c, f"/roles/{sales}/skills", meta_skill_id="sales-wf")).status_code == 400
        body = (await c.get(f"{PREFIX}/roles/{sales}/skills")).json()
        held = {h["skill"]: h["sources"] for h in body["skills"]}
        assert held["excel"] == [{"kind": "direct", "meta_skill_id": None, "meta_skill_name": None, "via": []}]
        assert held["sql"] == [
            {"kind": "meta_skill", "meta_skill_id": "outer", "meta_skill_name": "Outer", "via": ["Outer", "Inner"]}
        ]
        # A meta skill still held by a role cannot be deleted; revoking frees it.
        assert (await c.delete(f"{PREFIX}/workflows/outer")).status_code == 409
        assert (await c.delete(f"{PREFIX}/roles/{sales}/skills/{grant.json()['id']}")).status_code == 204
        after = (await c.get(f"{PREFIX}/roles/{sales}/skills")).json()
        assert [h["skill"] for h in after["skills"]] == ["excel"]
        assert (await c.delete(f"{PREFIX}/workflows/outer")).status_code == 204
        assert (await c.delete(f"{PREFIX}/workflows/inner")).status_code == 204


async def test_validation_endpoint_reports_missing_skill_as_warning(factory, seeded):
    async with _client(factory, COMPANY_A, ADMIN_A) as c:
        res = await c.put(f"{PREFIX}/workflows/sales-wf/graph", json=GRAPH)
        assert res.status_code == 200
        assert any("does not hold skill 'sql'" in w for w in res.json()["validation"]["warnings"])
        await _post(c, f"/roles/{seeded['sales']}/skills", skill_name="sql")
        stored = (await c.get(f"{PREFIX}/workflows/sales-wf/validation")).json()
        assert stored == {"errors": [], "warnings": []}
        dry = await c.post(f"{PREFIX}/workflows/sales-wf/graph/validate", json={"nodes": [], "transitions": []})
        assert dry.status_code == 200 and dry.json()["errors"]


async def test_process_delete_is_refused_while_a_graph_uses_it(factory, seeded):
    async with _client(factory, COMPANY_A, ADMIN_A) as c:
        await c.put(f"{PREFIX}/workflows/sales-wf/graph", json=GRAPH)
        assert (await c.delete(f"{PREFIX}/processes/p1")).status_code == 409
        assert (await c.delete(f"{PREFIX}/workflows/sales-wf")).status_code == 204
        assert (await c.delete(f"{PREFIX}/processes/p1")).status_code == 204


async def test_existing_automation_rows_stay_valid(factory):
    """A row written the old way, without any Company OS field, still reads back."""
    async with factory() as s:
        row = await WorkflowService().create(s, COMPANY_A, "legacy-wf", name="Old", definition={"steps": [1]})
        await s.commit()
        assert (row.kind, row.owner_role_id, row.trigger_type, row.trigger_config) == ("workflow", None, None, {})
    async with _client(factory, COMPANY_A, ADMIN_A) as c:
        got = (await c.get(f"{PREFIX}/workflows/legacy-wf")).json()
        assert got["kind"] == "workflow" and got["owner_role_id"] is None
        assert (await c.get(f"{PREFIX}/workflows/legacy-wf/graph")).json()["graph"] == {"nodes": [], "transitions": []}


async def test_unauthenticated_requests_are_refused(factory):
    """No override: the request is refused, and no data comes back."""
    app = FastAPI()
    app.include_router(company_os_router, prefix="/api/llc")
    app.include_router(skills_router, prefix="/api/llc")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        for path in ("/workflows", "/processes", f"/roles/{uuid.uuid4()}/skills"):
            res = await c.get(f"{PREFIX}{path}")
            assert 400 <= res.status_code < 500 and "workflow_id" not in res.text, (path, res.status_code)


def test_every_route_depends_on_auth_and_the_org_context():
    for router in (company_os_router, skills_router):
        for route in router.routes:
            calls = {d.call for d in route.dependant.dependencies}
            assert get_current_user in calls and require_org_context in calls, route.path


# ---- the older /llc/workflows routes must not bypass the Company OS rules (#18390) ----

LEGACY = "/api/llc/workflows"


def _legacy_client(maker, company, user) -> httpx.AsyncClient:
    from api.user_management.dependencies import get_current_user as gcu
    from llc.api.workflows import router as legacy_router
    from user_management.database import get_async_session

    app = FastAPI()
    app.include_router(legacy_router, prefix="/api/llc")

    async def _session():
        async with maker() as s:
            yield s

    app.dependency_overrides[get_async_session] = _session
    app.dependency_overrides[gcu] = lambda: {"id": str(user)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=company, user_id=user, is_platform_admin=False
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_legacy_routes_enforce_the_admin_gate_on_company_os_rows(factory, seeded):
    async with _client(factory, COMPANY_A, ADMIN_A) as c:
        await _post(c, "/workflows", workflow_id="meta", kind="meta_skill")
    async with _legacy_client(factory, COMPANY_A, MEMBER_A) as member:
        for wid in ("sales-wf", "meta"):
            assert (await member.delete(f"{LEGACY}/{COMPANY_A}/{wid}")).status_code == 403
            res = await member.patch(f"{LEGACY}/{COMPANY_A}/{wid}", json={"status": "running"})
            assert res.status_code == 403
    async with _client(factory, COMPANY_A, MEMBER_A) as check:
        rows = {w["workflow_id"]: w for w in (await check.get(f"{PREFIX}/workflows")).json()}
        assert {"sales-wf", "meta"} <= set(rows)
        assert rows["sales-wf"]["status"] == rows["meta"]["status"] == "planned", "a refused PATCH must not write"


async def test_legacy_delete_of_a_referenced_workflow_is_409_not_500(factory, seeded):
    ops_graph = {
        "nodes": [{"key": "s", "kind": "start"}, {"key": "ok", "kind": "end", "end_outcome": "done"}],
        "transitions": [{"from_node": "s", "kind": "success", "to_node": "ok"}],
    }
    sales_graph = {
        **GRAPH,
        "transitions": GRAPH["transitions"] + [{"from_node": "ok", "kind": "handoff", "handoff_workflow_id": "ops-wf"}],
    }
    async with _client(factory, COMPANY_A, ADMIN_A) as c:
        await c.put(f"{PREFIX}/workflows/ops-wf/graph", json=ops_graph)
        await c.put(f"{PREFIX}/workflows/sales-wf/graph", json=sales_graph)
    async with _legacy_client(factory, COMPANY_A, ADMIN_A) as legacy:
        assert (await legacy.delete(f"{LEGACY}/{COMPANY_A}/ops-wf")).status_code == 409
        res = await legacy.patch(f"{LEGACY}/{COMPANY_A}/ops-wf", json={"status": "running"})
        assert res.status_code == 200 and res.json()["status"] == "running"
        assert (await legacy.delete(f"{LEGACY}/{COMPANY_A}/sales-wf")).status_code == 204


async def test_legacy_list_and_role_attach_do_not_see_meta_skills(factory, seeded):
    from llc.services.role_workflow import RoleWorkflowService

    async with _client(factory, COMPANY_A, ADMIN_A) as c:
        await _post(c, "/workflows", workflow_id="meta", kind="meta_skill")
    async with _legacy_client(factory, COMPANY_A, ADMIN_A) as legacy:
        listed = {w["workflow_id"] for w in (await legacy.get(f"{LEGACY}/{COMPANY_A}")).json()}
    assert listed == {"sales-wf", "ops-wf"}
    async with factory() as s:
        with pytest.raises(ValueError, match="meta skill"):
            await RoleWorkflowService()._require_workflow(s, COMPANY_A, "meta")


async def test_replacing_a_graph_locks_the_workflow_row(factory, seeded):
    from sqlalchemy.dialects import postgresql

    from llc.services.company_os.graphs import GraphService

    seen = []
    async with factory() as s:
        real = s.execute

        async def spy(stmt, *a, **k):
            seen.append(stmt)
            return await real(stmt, *a, **k)

        s.execute = spy
        await GraphService().replace(s, COMPANY_A, "sales-wf", GraphSpec.model_validate(GRAPH), actor=ADMIN_A)
    locking = [x for x in seen if "FOR UPDATE" in str(x.compile(dialect=postgresql.dialect()))]
    assert locking, "replace() must SELECT ... FOR UPDATE the workflow row"


@pytest.mark.parametrize("verb", ["delete", "patch"])
async def test_a_move_landing_between_the_read_and_the_write_is_still_refused(factory, seeded, verb, monkeypatch):
    """#18446: the row is a plain workflow when first read and role-owned by the time the
    legacy write runs. The write's own predicate matches nothing, the route re-loads and
    re-dispatches through the Company OS rules, and the member is refused."""
    from llc.services.company_os.workflows import CompanyOsWorkflowService
    from llc.services.workflow import WorkflowService

    async with factory() as s:
        await WorkflowService().create(s, COMPANY_A, "race-wf", name="plain")
        await s.commit()
    original = getattr(WorkflowService, "delete" if verb == "delete" else "update_status")

    async def move_then_write(self, session, *args, **kwargs):
        async with factory() as other:
            row = await CompanyOsWorkflowService().get(other, COMPANY_A, "race-wf")
            await CompanyOsWorkflowService()._move_to_role(other, COMPANY_A, row, seeded["sales"])
            await other.commit()
        return await original(self, session, *args, **kwargs)

    monkeypatch.setattr(WorkflowService, "delete" if verb == "delete" else "update_status", move_then_write)
    async with _legacy_client(factory, COMPANY_A, MEMBER_A) as member:
        if verb == "delete":
            res = await member.delete(f"{LEGACY}/{COMPANY_A}/race-wf")
        else:
            res = await member.patch(f"{LEGACY}/{COMPANY_A}/race-wf", json={"status": "running"})
    assert res.status_code == 403
    async with _client(factory, COMPANY_A, ADMIN_A) as admin:
        row = (await admin.get(f"{PREFIX}/workflows/race-wf")).json()
    assert row["owner_role_id"] == str(seeded["sales"]) and row["status"] == "planned"
