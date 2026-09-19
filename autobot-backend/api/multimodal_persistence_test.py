# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A refused memory write is visible in the HTTP response, not only in the log (#16926).

`MultiModalProcessor.process()` knew whether its result was stored and the API
dropped it, so a tenancy refusal answered 200 `success: true`. These tests go
through the endpoint on purpose: the processor-level tests already passed while
the gap was open, because they stopped one layer below it.

Everything below the HTTP request is real (the endpoint, `process()`,
`_store_result`, the response model) except two seams. The modality processor is
canned, since there is no model to run. `store_memory` runs only the real
tenancy guard, since the guard raises before any storage is touched.
"""

import ast
import inspect
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.multimodal as multimodal_api
from auth_middleware import get_current_user
from memory.storage.general_storage import LEGACY_UNSCOPED_OWNER, _require_user_id
from multimodal_processor.models import ModalityType, ProcessingIntent, ProcessingResult
from multimodal_processor.processor import MultiModalProcessor
from multimodal_processor.types import PersistenceOutcome


def _processed(modality=ModalityType.TEXT):
    return ProcessingResult(
        result_id="r-1",
        input_id="i-1",
        modality_type=modality,
        intent=ProcessingIntent.DECISION_MAKING,
        success=True,
        confidence=0.9,
        result_data={"summary": "ok"},
        processing_time=0.1,
    )


async def _guarded_store(**kwargs):
    """The real tenancy guard, which is all of the write that runs before storage is touched."""
    _require_user_id(kwargs["user_id"], for_write=True)


def _client(principal) -> TestClient:
    app = FastAPI()
    app.include_router(multimodal_api.router, prefix="/api/multimodal")
    app.dependency_overrides[get_current_user] = lambda: principal
    return TestClient(app)


@pytest.fixture
def proc():
    real = MultiModalProcessor()
    with (
        patch.object(multimodal_api, "processor", real),
        # A fresh result per call: process() stamps the owner onto it, and a shared one would carry it across requests.
        patch.object(real, "_route_to_processor", new=AsyncMock(side_effect=lambda *_: _processed())),
    ):
        yield real


# (principal, what store_memory does, the persistence the caller must see)
CASES = {
    "stored": ({"sub": "alice"}, None, "stored"),
    "tenancy refusal": ({"sub": LEGACY_UNSCOPED_OWNER}, _guarded_store, "refused"),
    "transient failure": ({"sub": "alice"}, RuntimeError("redis unavailable"), "failed"),
    "service key, no user": ({"role": "service"}, None, "unowned"),
}


class TestTheProcessEndpointReportsPersistence:
    @pytest.mark.parametrize("case", list(CASES))
    def test_each_outcome_reaches_the_response(self, proc, case):
        principal, store_effect, expected = CASES[case]
        with patch.object(proc.memory_manager, "store_memory", new=AsyncMock(side_effect=store_effect)):
            response = _client(principal).post("/api/multimodal/process/text", json={"text": "hello"})

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True, "processing succeeded in every case; only the write differs"
        assert body["persistence"] == expected

    def test_the_refusal_comes_from_the_real_guard_on_the_principal_owner(self, proc):
        with patch.object(proc.memory_manager, "store_memory", new=AsyncMock(side_effect=_guarded_store)) as store:
            body = (
                _client({"sub": LEGACY_UNSCOPED_OWNER}).post("/api/multimodal/process/text", json={"text": "x"}).json()
            )

        assert store.await_args.kwargs["user_id"] == LEGACY_UNSCOPED_OWNER
        assert body["persistence"] == "refused"

    def test_a_refusal_and_a_transient_failure_are_different_on_the_wire(self, proc):
        """The outcome the issue is about: two different events must not share one answer."""
        answers = {}
        for case in ("tenancy refusal", "transient failure"):
            principal, store_effect, _ = CASES[case]
            with patch.object(proc.memory_manager, "store_memory", new=AsyncMock(side_effect=store_effect)):
                answers[case] = _client(principal).post("/api/multimodal/process/text", json={"text": "x"}).json()

        assert answers["tenancy refusal"]["persistence"] != answers["transient failure"]["persistence"]

    def test_a_failed_processing_run_reports_no_persistence(self, proc):
        """Nothing was produced, so nothing was stored or refused: None, not a guess."""
        with patch.object(proc, "_route_to_processor", new=AsyncMock(side_effect=RuntimeError("model crashed"))):
            body = _client({"sub": "alice"}).post("/api/multimodal/process/text", json={"text": "x"}).json()

        assert body["success"] is False
        assert body["persistence"] is None


class TestTheFusionEndpointReportsPersistence:
    def test_each_individual_result_carries_its_outcome(self, proc):
        with (
            patch.object(proc.memory_manager, "store_memory", new=AsyncMock(side_effect=_guarded_store)),
            patch.object(proc, "_process_combined", new=AsyncMock(return_value=_processed(ModalityType.COMBINED))),
        ):
            response = _client({"sub": LEGACY_UNSCOPED_OWNER}).post(
                "/api/multimodal/fusion/combine", data={"text": "hi", "intent": "decision_making"}
            )

        assert response.status_code == 200
        assert [r["persistence"] for r in response.json()["individual_results"]] == ["refused"]


class TestTheWireValuesAreTheOutcomes:
    def test_the_response_literal_matches_the_enum(self):
        """The schema module stays free of processor imports, so the values are spelled twice. Pin them."""
        from typing import get_args

        from api.schemas_ai_stack import MultiModalResponse

        literal = get_args(MultiModalResponse.model_fields["persistence"].annotation)[0]
        assert set(get_args(literal)) == {o.value for o in PersistenceOutcome}


class TestNoProcessEndpointBuildsASuccessByHand:
    """A success response built outside `_processed_response` could drop `persistence` again (#16926).

    Every other `MultiModalResponse(...)` in the module must be an error response: `success=False`.
    """

    def _constructions(self):
        tree = ast.parse(inspect.getsource(multimodal_api))
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(fn):
                if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "MultiModalResponse":
                    yield fn.name, node

    @staticmethod
    def _is_error_response(call):
        return any(
            kw.arg == "success" and isinstance(kw.value, ast.Constant) and kw.value.value is False
            for kw in call.keywords
        )

    def test_success_responses_come_only_from_the_shared_builder(self):
        found = list(self._constructions())
        assert any(name == "_processed_response" for name, _ in found), "the scan did not find the builder"
        stray = [name for name, call in found if name != "_processed_response" and not self._is_error_response(call)]
        assert stray == []

    def test_the_scan_flags_a_hand_built_success(self):
        """Negative control: a success response built by hand must be reported by the predicate."""
        call = ast.parse("MultiModalResponse(success=result.success, result_id='r')").body[0].value
        assert not self._is_error_response(call)
