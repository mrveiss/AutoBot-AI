# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21003: every route serving a source's findings says when they come from an interrupted run."""

import inspect
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import JSONResponse

from api.codebase_analytics import run_status
from api.codebase_analytics.endpoints import report as report_mod
from api.codebase_analytics.endpoints import stats as stats_mod
from api.codebase_analytics.run_status import (
    partial_report_banner,
    record_run_finished,
    record_run_started,
    report_response,
    run_response_fields,
    with_run_state,
)

#: "Serves findings" is decided from the code, not from a list of names: a GET route that is scoped to a
#: source (a ``source_id`` path or query parameter) and whose handler's module imports a code-collection
#: accessor reads what an indexing run stored.  Such a route is labelled (``@with_run_state``), is the
#: markdown ``/report`` (labelled in its body and headers by ``report_response``), or is named here with
#: the reason it does not carry a run's findings.  A new route that reads the store and is none of these fails.
_STORE_ACCESSORS = ("get_code_collection", "get_code_collection_async")
_DOWNLOAD_ROUTES = {"/report"}
_NOT_RUN_FINDINGS = {
    "/analytics/import-tree/cached": "a stored task result, flagged stale against the last sync instead",
    "/analytics/dependencies/cached": "a stored task result, flagged stale against the last sync instead",
}


def _reads_the_store(route) -> bool:
    handler = inspect.unwrap(route.endpoint)
    return any(name in getattr(handler, "__globals__", {}) for name in _STORE_ACCESSORS)


def _is_source_scoped(route) -> bool:
    dependant = route.dependant
    return any(p.name == "source_id" for p in [*dependant.path_params, *dependant.query_params])


def _unlabelled_findings_routes(mounted) -> list[str]:
    """Paths of GET routes that read the store for one source and carry no run label."""
    return sorted(
        m.path
        for m in mounted
        if "GET" in m.methods
        and _is_source_scoped(m.route)
        and _reads_the_store(m.route)
        and not getattr(m.route.endpoint, "labels_run_state", False)
        and m.path not in _DOWNLOAD_ROUTES
        and m.path not in _NOT_RUN_FINDINGS
    )


class _RunStore:
    """Just enough of the collection for the run record: get/upsert by id."""

    def __init__(self):
        self.docs = {}
        self.reads = 0

    async def get(self, ids=None, where=None, include=None):
        self.reads += 1
        return {"metadatas": [self.docs[i] for i in ids if i in self.docs]}

    async def upsert(self, ids, documents, metadatas):
        for i, m in zip(ids, metadatas):
            self.docs[i] = dict(m)


@pytest.fixture
def run_store():
    store = _RunStore()
    with patch.object(run_status, "get_code_collection_async", AsyncMock(return_value=store)):
        yield store


async def _killed_after_a_completed_run(source="src"):
    await record_run_started(source, "run-1")
    await record_run_finished(source, "run-1", "completed")
    await record_run_started(source, "run-2")
    await record_run_finished(source, "run-2", "killed", "killed by the hard timeout: run exceeded 1800s")


@pytest.mark.asyncio
async def test_a_source_with_no_run_record_is_not_reported_partial(run_store):
    """Data indexed before run records existed: ``run`` is null and nothing claims it is incomplete."""
    assert await run_response_fields("src") == {"partial": False, "run": None}


@pytest.mark.asyncio
async def test_a_killed_run_is_partial_and_names_its_reason_and_the_last_completion(run_store):
    await _killed_after_a_completed_run()
    fields = await run_response_fields("src")
    run = fields["run"]
    assert fields["partial"] is True
    assert (run["status"], run["reason"]) == ("killed", "killed by the hard timeout: run exceeded 1800s")
    assert run["finished_at"] != "" and run["last_completed_at"] != ""


@pytest.mark.asyncio
async def test_an_unreadable_record_does_not_fail_the_findings_it_labels(run_store):
    run_store.get = AsyncMock(side_effect=RuntimeError("store down"))
    assert await run_response_fields("src") == {"partial": False, "run": None}


@pytest.mark.asyncio
async def test_the_decorator_labels_a_dict_body_once_and_leaves_responses_alone(run_store):
    await _killed_after_a_completed_run()

    @with_run_state
    async def as_dict(source_id):
        return {"status": "success"}

    @with_run_state
    async def as_response(source_id):
        return JSONResponse({"status": "error"}, status_code=404, headers={"X-Keep": "1"})

    labelled = await as_dict("src")  # positional: the label must not be lost
    body = json.loads(labelled.body)
    assert (body["status"], body["partial"], body["run"]["status"]) == ("success", True, "killed")
    assert (await as_dict(source_id="src")).body == labelled.body
    untouched = await as_response(source_id="src")
    assert (untouched.status_code, untouched.headers["x-keep"], json.loads(untouched.body)) == (
        404,
        "1",
        {"status": "error"},
    )


@pytest.mark.asyncio
async def test_a_labelled_request_reads_the_record_once(run_store):
    await _killed_after_a_completed_run()

    @with_run_state
    async def handler(source_id):
        return {}

    before = run_store.reads
    await handler(source_id="src")
    assert run_store.reads == before + 1


def test_every_route_that_serves_findings_is_labelled():
    from api.codebase_analytics.router import router
    from autobot_shared.api_routing.router_routes import effective_routes

    mounted = effective_routes(router)
    assert _unlabelled_findings_routes(mounted) == []
    # the walk still sees the routes it exists to see (a rule that finds nothing would pass)
    labelled = {m.path for m in mounted if getattr(m.route.endpoint, "labels_run_state", False)}
    assert labelled >= {
        "/stats",
        "/hardcodes",
        "/problems",
        "/analytics/charts",
        "/declarations",
        "/analytics/import-tree",
        "/analytics/dependencies",
    }


def test_control_an_unlabelled_store_reading_route_is_flagged_and_a_labelled_one_is_not():
    from fastapi import APIRouter

    from api.source_scope import SourceIdQuery
    from autobot_shared.api_routing.router_routes import effective_routes

    namespace = {"get_code_collection": object(), "SourceIdQuery": SourceIdQuery}
    exec("async def reads(source_id: SourceIdQuery):\n    return {}\n", namespace)  # noqa: S102
    unrelated = {"SourceIdQuery": SourceIdQuery}
    exec("async def does_not_read(source_id: SourceIdQuery):\n    return {}\n", unrelated)
    throwaway = APIRouter()
    throwaway.get("/unlabelled")(namespace["reads"])
    throwaway.get("/labelled")(with_run_state(namespace["reads"]))
    throwaway.get("/elsewhere")(unrelated["does_not_read"])
    assert _unlabelled_findings_routes(effective_routes(throwaway)) == ["/unlabelled"]


def _stats_collection():
    collection = MagicMock()
    collection.get.return_value = {"metadatas": [{"total_files": 3, "last_indexed": "2026-11-01T00:00:00+00:00"}]}
    return collection


@pytest.mark.asyncio
async def test_stats_route_carries_the_run_state(run_store):
    await _killed_after_a_completed_run()
    with patch.object(stats_mod, "get_code_collection", return_value=_stats_collection()):
        body = json.loads((await stats_mod.get_codebase_stats(source_id="src")).body)
    assert body["stats"]["total_files"] == 3
    assert (body["partial"], body["run"]["status"]) == (True, "killed")


@pytest.mark.asyncio
async def test_stats_route_for_a_source_without_a_record_is_not_partial(run_store):
    with patch.object(stats_mod, "get_code_collection", return_value=_stats_collection()):
        body = json.loads((await stats_mod.get_codebase_stats(source_id="src")).body)
    assert (body["partial"], body["run"]) == (False, None)


async def _report(source="src"):
    with (
        patch.object(report_mod, "resolve_scan_root", new=AsyncMock(return_value=Path("."))),
        patch.object(report_mod, "_fetch_problems_from_chromadb", return_value=[]),
    ):
        return await report_mod.generate_analysis_report(source_id=source, quick=True)


@pytest.mark.asyncio
async def test_report_of_a_killed_run_opens_with_a_partial_banner_and_says_so_in_headers(run_store):
    await _killed_after_a_completed_run()
    response = await _report()
    text = response.body.decode("utf-8")
    assert text.startswith("> **Partial results.**")
    assert "Last completed run:" in text
    assert (response.headers["x-run-partial"], response.headers["x-run-status"]) == ("true", "killed")
    assert response.headers["x-source-id"] == "src"


@pytest.mark.asyncio
async def test_report_without_a_record_is_unlabelled(run_store):
    response = await _report()
    assert not response.body.decode("utf-8").startswith(">")
    assert response.headers["x-run-partial"] == "false"
    assert "x-run-status" not in response.headers


def test_a_completed_run_has_no_banner():
    run = {"partial": False, "status": "completed", "last_completed_at": "t"}
    assert partial_report_banner(run) == ""
    assert partial_report_banner(None) == ""
    assert report_response("body", {"partial": False, "run": run}, "src").body == b"body"
