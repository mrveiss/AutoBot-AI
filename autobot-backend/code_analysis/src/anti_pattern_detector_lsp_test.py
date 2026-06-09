# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for the Liskov Substitution Principle detector (Issue #6661).

The new analyzer adds two AntiPatternType entries — LSP_SIGNATURE_INCOMPATIBLE
and LSP_EXCEPTION_CONTRACT_CHANGED — that catch the same class of bug we
just shipped manually as #6658, #6659 and #6660.

Tests use temporary on-disk fixture files because the underlying class
parser is file-path driven.
"""

import importlib.util
import textwrap
from pathlib import Path

import pytest


def _load_detector_module():
    spec = importlib.util.spec_from_file_location(
        "apd_under_test",
        "autobot-backend/code_analysis/src/anti_pattern_detector.py",
    )
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # pragma: no cover — env-dependent
        pytest.skip(f"AntiPatternDetector dep chain unavailable: {exc}")
    # Pre-existing latent bug in this module: __init__ references the bare name
    # ``config`` which is never imported (line 273). Production callers tolerate
    # this because the import happens through a path where ``config`` is in
    # globals; isolated-load tests must inject it. Filed as discovery.
    if not hasattr(mod, "config"):
        mod.config = None
    return mod


@pytest.fixture
def fixture_root(tmp_path):
    """A throwaway codebase fixture for AntiPatternDetector to scan."""
    return tmp_path


def _write_module(root: Path, name: str, body: str) -> Path:
    p = root / f"{name}.py"
    p.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return p


@pytest.mark.asyncio
async def test_lsp_signature_incompatible_async_sync_mismatch(fixture_root):
    """Sync override of an async parent must be flagged (#6659 case)."""
    apd = _load_detector_module()
    _write_module(
        fixture_root,
        "agents",
        """
        class BaseAgent:
            async def is_available(self) -> bool:
                return True

        class LocalAgent(BaseAgent):
            def is_available(self) -> bool:  # sync override -> violation
                return True
        """,
    )

    detector = apd.AntiPatternDetector()
    report = await detector.analyze(
        root_path=str(fixture_root),
        patterns=["*.py"],
        exclude_patterns=["__pycache__"],  # truthy non-default — see analyze() `or` idiom
    )
    sig_issues = [ap for ap in report.anti_patterns if ap.pattern_type.value == "lsp_signature_incompatible"]
    assert sig_issues, "expected at least one LSP_SIGNATURE_INCOMPATIBLE finding"
    msg = sig_issues[0].description
    assert "sync" in msg and "async" in msg


@pytest.mark.asyncio
async def test_lsp_signature_incompatible_required_param_dropped(fixture_root):
    """Constructor that drops a required parent param must be flagged (#6660 case)."""
    apd = _load_detector_module()
    _write_module(
        fixture_root,
        "ag",
        """
        class StandardizedAgent:
            def __init__(self, agent_type, deployment_mode=None):
                self.agent_type = agent_type

        class LLMFailsafeAgent(StandardizedAgent):
            def __init__(self):              # drops required agent_type -> violation
                super().__init__("llm_failsafe")
        """,
    )

    detector = apd.AntiPatternDetector()
    report = await detector.analyze(
        root_path=str(fixture_root),
        patterns=["*.py"],
        exclude_patterns=["__pycache__"],  # truthy non-default — see analyze() `or` idiom
    )
    sig_issues = [
        ap
        for ap in report.anti_patterns
        if ap.pattern_type == apd.AntiPatternType.LSP_SIGNATURE_INCOMPATIBLE
        and "drops required positional params" in ap.description
    ]
    assert sig_issues, "expected required-param-removal finding"


@pytest.mark.asyncio
async def test_lsp_exception_contract_changed(fixture_root):
    """Child raising a type the parent doesn't must be flagged (#6658 case)."""
    apd = _load_detector_module()
    _write_module(
        fixture_root,
        "ints",
        """
        class BaseIntegration:
            async def execute_action(self, action, params):
                return {"ok": True}

        class SlackIntegration(BaseIntegration):
            async def execute_action(self, action, params):
                if action == "x":
                    raise ValueError("boom")  # not in parent's contract
                return {}
        """,
    )

    detector = apd.AntiPatternDetector()
    report = await detector.analyze(
        root_path=str(fixture_root),
        patterns=["*.py"],
        exclude_patterns=["__pycache__"],  # truthy non-default — see analyze() `or` idiom
    )
    exc_issues = [
        ap for ap in report.anti_patterns if ap.pattern_type == apd.AntiPatternType.LSP_EXCEPTION_CONTRACT_CHANGED
    ]
    assert exc_issues
    assert "ValueError" in exc_issues[0].description


@pytest.mark.asyncio
async def test_lsp_skips_abstract_parent(fixture_root):
    """Subclass extending an @abstractmethod parent must NOT be flagged."""
    apd = _load_detector_module()
    _write_module(
        fixture_root,
        "abc_case",
        """
        from abc import abstractmethod

        class Base:
            @abstractmethod
            def run(self):
                ...

        class Concrete(Base):
            def run(self):
                if True:
                    raise ValueError("err")  # OK — parent is abstract stub
                return None
        """,
    )

    detector = apd.AntiPatternDetector()
    report = await detector.analyze(
        root_path=str(fixture_root),
        patterns=["*.py"],
        exclude_patterns=["__pycache__"],  # truthy non-default — see analyze() `or` idiom
    )
    lsp = [
        ap
        for ap in report.anti_patterns
        if ap.pattern_type
        in (
            apd.AntiPatternType.LSP_SIGNATURE_INCOMPATIBLE,
            apd.AntiPatternType.LSP_EXCEPTION_CONTRACT_CHANGED,
        )
    ]
    assert not lsp, f"unexpected LSP findings against abstract parent: {lsp}"


@pytest.mark.asyncio
async def test_lsp_skips_child_with_widened_preconditions(fixture_root):
    """Child override that widens the parent's signature (adds defaults)
    must NOT be flagged.

    Regression: #6755 dogfood pass produced 5 false-positive
    LSP_SIGNATURE_INCOMPATIBLE findings against ``BasePipeline`` subclasses
    AFTER they were correctly fixed to accept the parent's args with
    defaults. The original rule (``child_required < parent_required``)
    flagged this — but a child widening preconditions is correct LSP.
    The corrected rule compares child's TOTAL positional slots against
    parent's REQUIRED count.
    """
    apd = _load_detector_module()
    _write_module(
        fixture_root,
        "widening",
        """
        from typing import List

        class BasePipeline:
            def __init__(self, pipeline_name: str, supported_types: List[str]):
                self.pipeline_name = pipeline_name
                self.supported_types = supported_types

        class DocumentPipeline(BasePipeline):
            # Widens preconditions — accepts both as kwargs OR positional, with
            # defaults matching the historical hardcoded values. Factory call
            # `cls("doc", [])` still works against the parent contract.
            def __init__(
                self,
                pipeline_name: str = "document",
                supported_types: List[str] = None,
            ):
                super().__init__(
                    pipeline_name=pipeline_name,
                    supported_types=supported_types if supported_types is not None else ["DOCUMENT"],
                )
        """,
    )

    detector = apd.AntiPatternDetector()
    report = await detector.analyze(
        root_path=str(fixture_root),
        patterns=["*.py"],
        exclude_patterns=["__pycache__"],
    )
    sig_issues = [
        ap for ap in report.anti_patterns if ap.pattern_type == apd.AntiPatternType.LSP_SIGNATURE_INCOMPATIBLE
    ]
    assert not sig_issues, (
        f"child widening preconditions should NOT be flagged; got: "
        f"{[(ap.entity_name, ap.description[:80]) for ap in sig_issues]}"
    )


@pytest.mark.asyncio
async def test_lsp_skips_docstring_plus_raise_notimplemented_stub(fixture_root):
    """Parent body of ``\"docstring\"; raise NotImplementedError`` is a stub —
    children adding behaviour must NOT be flagged.

    Regression: dogfood pass over autobot-backend produced 2 false-positive
    LSP_EXCEPTION_CONTRACT_CHANGED findings against ``BaseModalProcessor.process``
    because the original detector only matched length-1 bodies and missed the
    very common ``\"\"\"docstring\"\"\"`` + ``raise NotImplementedError`` form.
    """
    apd = _load_detector_module()
    _write_module(
        fixture_root,
        "modal_case",
        '''
        class BaseModalProcessor:
            async def process(self, input_data):
                """Process input and return result"""
                raise NotImplementedError

        class VisionProcessor(BaseModalProcessor):
            async def process(self, input_data):
                if input_data is None:
                    raise ValueError("missing input")  # OK — parent is stub
                return "vision-result"
        ''',
    )

    detector = apd.AntiPatternDetector()
    report = await detector.analyze(
        root_path=str(fixture_root),
        patterns=["*.py"],
        exclude_patterns=["__pycache__"],
    )
    lsp = [
        ap
        for ap in report.anti_patterns
        if ap.pattern_type
        in (
            apd.AntiPatternType.LSP_SIGNATURE_INCOMPATIBLE,
            apd.AntiPatternType.LSP_EXCEPTION_CONTRACT_CHANGED,
        )
    ]
    assert not lsp, (
        f"docstring + raise NotImplementedError parent must be treated as a "
        f"stub; unexpected findings: {[(ap.pattern_type.value, ap.entity_name) for ap in lsp]}"
    )


@pytest.mark.asyncio
async def test_lsp_skips_mixin_classes(fixture_root):
    """Mixin classes are not subject to LSP overrides."""
    apd = _load_detector_module()
    _write_module(
        fixture_root,
        "mixin_case",
        """
        class CacheMixin:
            async def get(self, k):
                return None

        class FastCacheMixin(CacheMixin):
            def get(self, k):  # would be a sync/async mismatch normally
                return "fast"
        """,
    )

    detector = apd.AntiPatternDetector()
    report = await detector.analyze(
        root_path=str(fixture_root),
        patterns=["*.py"],
        exclude_patterns=["__pycache__"],  # truthy non-default — see analyze() `or` idiom
    )
    lsp = [ap for ap in report.anti_patterns if ap.pattern_type == apd.AntiPatternType.LSP_SIGNATURE_INCOMPATIBLE]
    assert not lsp, f"Mixin override should be ignored, got: {lsp}"


@pytest.mark.asyncio
async def test_lsp_no_false_positives_on_clean_code(fixture_root):
    """Identical signatures must not be flagged."""
    apd = _load_detector_module()
    _write_module(
        fixture_root,
        "clean",
        """
        class Base:
            async def f(self, x: int) -> int:
                return x

        class Concrete(Base):
            async def f(self, x: int) -> int:
                return x * 2
        """,
    )

    detector = apd.AntiPatternDetector()
    report = await detector.analyze(
        root_path=str(fixture_root),
        patterns=["*.py"],
        exclude_patterns=["__pycache__"],  # truthy non-default — see analyze() `or` idiom
    )
    lsp = [
        ap
        for ap in report.anti_patterns
        if ap.pattern_type
        in (
            apd.AntiPatternType.LSP_SIGNATURE_INCOMPATIBLE,
            apd.AntiPatternType.LSP_EXCEPTION_CONTRACT_CHANGED,
        )
    ]
    assert not lsp, f"clean code should produce no LSP findings, got: {lsp}"
