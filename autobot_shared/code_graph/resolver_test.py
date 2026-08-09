# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for the canonical callee resolver (#13470)."""

from autobot_shared.code_graph.resolver import (
    ImportContext,
    is_external_module,
    resolve_call,
    resolve_callee,
    resolve_callee_by_suffix,
)


class TestResolveCallee:
    def test_module_level_direct_match(self) -> None:
        known_ids = {"pkg.module.helper", "pkg.module.other"}
        callee_id, is_external = resolve_callee("helper", "pkg.module", None, known_ids)
        assert callee_id == "pkg.module.helper"
        assert is_external is False

    def test_class_method_direct_match(self) -> None:
        known_ids = {"pkg.module.MyClass.helper"}
        callee_id, is_external = resolve_callee("helper", "pkg.module", "MyClass", known_ids)
        assert callee_id == "pkg.module.MyClass.helper"
        assert is_external is False

    def test_no_match_returns_none(self) -> None:
        callee_id, is_external = resolve_callee("missing", "pkg.module", None, set())
        assert callee_id is None
        assert is_external is False

    def test_import_context_cross_module_resolution(self) -> None:
        ctx = ImportContext()
        ctx.add_import(module="pkg.other", name="helper")
        known_ids = {"pkg.other.helper"}
        callee_id, is_external = resolve_callee("helper", "pkg.module", None, known_ids, ctx)
        assert callee_id == "pkg.other.helper"
        assert is_external is False

    def test_import_context_external_call(self) -> None:
        ctx = ImportContext()
        ctx.add_import(module="json")
        callee_id, is_external = resolve_callee("json", "pkg.module", None, set(), ctx)
        assert callee_id is None
        assert is_external is True


class TestResolveCalleeBySuffix:
    def test_zero_candidates(self) -> None:
        resolved_id, count = resolve_callee_by_suffix("process", set())
        assert resolved_id is None
        assert count == 0

    def test_single_candidate(self) -> None:
        known_ids = {"pkg.a.process", "pkg.a.other"}
        resolved_id, count = resolve_callee_by_suffix("process", known_ids)
        assert resolved_id == "pkg.a.process"
        assert count == 1

    def test_multiple_candidates_are_ambiguous(self) -> None:
        known_ids = {"pkg.a.process", "pkg.b.process"}
        resolved_id, count = resolve_callee_by_suffix("process", known_ids)
        assert resolved_id is None
        assert count == 2


class TestResolveCall:
    def test_direct_match_is_extracted(self) -> None:
        known_ids = {"pkg.module.helper"}
        result = resolve_call("helper", "pkg.module", None, known_ids)
        assert result.target_id == "pkg.module.helper"
        assert result.origin == "extracted"
        assert result.resolved is True

    def test_single_suffix_candidate_is_inferred(self) -> None:
        known_ids = {"pkg.other.process"}
        result = resolve_call("process", "pkg.module", None, known_ids)
        assert result.target_id == "pkg.other.process"
        assert result.origin == "inferred"
        assert result.resolved is True

    def test_ambiguous_candidates_are_not_resolved(self) -> None:
        known_ids = {"pkg.a.process", "pkg.b.process"}
        result = resolve_call("process", "pkg.module", None, known_ids)
        assert result.target_id is None
        assert result.origin == "ambiguous"
        assert result.candidate_count == 2
        assert result.resolved is False

    def test_zero_candidates_is_inferred_unresolved(self) -> None:
        result = resolve_call("nowhere", "pkg.module", None, set())
        assert result.target_id is None
        assert result.origin == "inferred"
        assert result.candidate_count == 0
        assert result.resolved is False

    def test_external_call_is_inferred_unresolved(self) -> None:
        ctx = ImportContext()
        ctx.add_import(module="json")
        result = resolve_call("json", "pkg.module", None, set(), ctx)
        assert result.target_id is None
        assert result.origin == "inferred"


class TestIsExternalModule:
    def test_stdlib_is_external(self) -> None:
        assert is_external_module("json") is True

    def test_internal_prefix_is_not_external(self) -> None:
        assert is_external_module("services.knowledge.code_indexer") is False

    def test_unknown_top_level_defaults_external(self) -> None:
        assert is_external_module("some_unknown_package") is True
