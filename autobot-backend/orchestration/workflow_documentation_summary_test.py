# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Contract tests for ``WorkflowDocumenter._generate_llm_summary`` (#7042).

After the #3185 LLMInterface retirement, the documenter still called
``self.llm_interface.chat_completion(...)`` — a method that doesn't exist
on LLMService (LLMService exposes ``chat()``). The summary path raised
AttributeError silently behind the broad ``except Exception`` guard at
the call site, so workflow documentation always shipped without the
``generated_summary`` field.

These tests pin the migrated shape:

  - Param renamed ``llm_interface`` → ``llm_service``
  - Method call renamed ``chat_completion`` → ``chat``
  - Response is read via ``.content`` / ``.error`` (LLMResponse contract)
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest

from orchestration.types import DocumentationType, WorkflowDocumentation
from orchestration.workflow_documentation import WorkflowDocumenter
from tests.fixtures import make_llm_response as _make_llm_response_factory


@pytest.fixture
def make_llm_response():
    """Canonical LLMResponse factory (#7134) — wraps the shared
    ``tests.fixtures.make_llm_response`` so the test sees the real
    LLMResponse field shape, not a hand-rolled stub that could drift.
    """
    return _make_llm_response_factory


def _make_workflow_doc(workflow_id: str = "wf-1") -> WorkflowDocumentation:
    """Minimal WorkflowDocumentation suitable for the summary path."""
    now = datetime.now(tz=timezone.utc)
    return WorkflowDocumentation(
        workflow_id=workflow_id,
        title="Test workflow",
        description="A test workflow for the summary path",
        created_at=now,
        updated_at=now,
        documentation_type=DocumentationType.WORKFLOW_SUMMARY,
        content={},
    )


# ---------------------------------------------------------------------------
# Constructor contract — param rename + attribute rename
# ---------------------------------------------------------------------------


def test_constructor_accepts_llm_service_keyword() -> None:
    """The post-#7042 keyword is ``llm_service`` (renamed from
    ``llm_interface`` to match LLMService convention)."""
    sig = inspect.signature(WorkflowDocumenter.__init__)
    params = list(sig.parameters.keys())
    assert "llm_service" in params
    assert "llm_interface" not in params, (
        "param must be renamed to 'llm_service' — orchestrator.py and any " "future caller depend on the new name"
    )


def test_attribute_renamed_to_llm_service() -> None:
    """Stored attribute must be ``self.llm_service`` (not the old
    ``self.llm_interface``)."""
    documenter = WorkflowDocumenter(llm_service=object())
    assert hasattr(documenter, "llm_service")
    assert not hasattr(documenter, "llm_interface")


# ---------------------------------------------------------------------------
# Method-call contract — chat() not chat_completion()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summary_calls_llm_service_chat_not_chat_completion(make_llm_response: Any) -> None:
    """Regression pin for the original #7042 bug: the helper must call
    ``llm_service.chat(...)``, never the legacy ``chat_completion``.
    """
    llm_service = AsyncMock()
    llm_service.chat = AsyncMock(return_value=make_llm_response(content="Summary text", error=None))
    # If a future change resurrects the legacy method call, fail loudly.
    llm_service.chat_completion = AsyncMock(side_effect=AssertionError("legacy method"))

    documenter = WorkflowDocumenter(llm_service=llm_service)
    workflow_doc = _make_workflow_doc()

    await documenter._generate_llm_summary(workflow_doc, {"status": "completed"})

    llm_service.chat.assert_awaited_once()
    llm_service.chat_completion.assert_not_awaited()
    assert workflow_doc.content.get("generated_summary") == "Summary text"


@pytest.mark.asyncio
async def test_summary_skipped_when_no_llm_service(make_llm_response: Any) -> None:
    """No LLM configured → early-return, no exception, no summary field."""
    documenter = WorkflowDocumenter(llm_service=None)
    workflow_doc = _make_workflow_doc()

    await documenter._generate_llm_summary(workflow_doc, {"status": "completed"})

    assert "generated_summary" not in workflow_doc.content


@pytest.mark.asyncio
async def test_summary_skipped_on_llm_response_error(make_llm_response: Any) -> None:
    """LLMResponse.error truthy → skip (no partial/poisoned summary written)."""
    llm_service = AsyncMock()
    llm_service.chat = AsyncMock(return_value=make_llm_response(content="", error="rate limit"))

    documenter = WorkflowDocumenter(llm_service=llm_service)
    workflow_doc = _make_workflow_doc()

    await documenter._generate_llm_summary(workflow_doc, {"status": "completed"})

    assert "generated_summary" not in workflow_doc.content


@pytest.mark.asyncio
async def test_summary_swallows_exception_and_logs(make_llm_response: Any, caplog) -> None:
    """The broad except-guard remains — ensures one bad summary call
    doesn't break the rest of the documentation pipeline.
    """
    import logging

    llm_service = AsyncMock()
    llm_service.chat = AsyncMock(side_effect=RuntimeError("boom"))

    documenter = WorkflowDocumenter(llm_service=llm_service)
    workflow_doc = _make_workflow_doc()

    with caplog.at_level(logging.WARNING):
        await documenter._generate_llm_summary(workflow_doc, {"status": "completed"})

    assert "generated_summary" not in workflow_doc.content
    assert any("Failed to generate workflow summary" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Migration pin — #3185 retired LLMService.chat_completion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summary_never_reaches_for_the_retired_chat_completion(make_llm_response: Any) -> None:
    """``chat_completion`` no longer exists on LLMService, so calling it would
    raise AttributeError at runtime and the broad except-guard would swallow it
    into a missing summary — silently, exactly like the original defect.

    This replaces ``assert ".chat_completion(" not in inspect.getsource(...)``
    (#13311): a comment mentioning the old name failed that grep, and moving
    the call into a helper failed it too, while neither told us what the
    method actually calls.
    """
    llm_service = AsyncMock()
    llm_service.chat = AsyncMock(return_value=make_llm_response(content="a summary", error=None))
    llm_service.chat_completion = AsyncMock(side_effect=AssertionError("retired LLMService.chat_completion called"))

    documenter = WorkflowDocumenter(llm_service=llm_service)
    workflow_doc = _make_workflow_doc()

    await documenter._generate_llm_summary(workflow_doc, {"status": "completed"})

    assert workflow_doc.content["generated_summary"] == "a summary"
    llm_service.chat.assert_awaited_once()
    llm_service.chat_completion.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_service_without_chat_produces_no_summary_and_logs(caplog) -> None:
    """The mirror of the guard above: pin that an absent ``chat`` is visible.

    ``spec=[]`` gives an object with no attributes at all, so any method name
    the documenter reaches for raises — the observable is the warning, not a
    silently empty document.
    """
    import logging
    from unittest.mock import MagicMock

    documenter = WorkflowDocumenter(llm_service=MagicMock(spec=[]))
    workflow_doc = _make_workflow_doc()

    with caplog.at_level(logging.WARNING):
        await documenter._generate_llm_summary(workflow_doc, {"status": "completed"})

    assert "generated_summary" not in workflow_doc.content
    assert any("Failed to generate workflow summary" in r.message for r in caplog.records)
