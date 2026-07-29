# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Closest-match suggestions and baseline health for the API wiring audit (#12738).

The gate already fails on a frontend call with no backing route, but it never
said what the route was *renamed to* — detection without repair guidance. And a
call whose endpoint was removed *after* it was baselined stayed green forever,
because the baseline cannot tell "not implemented yet" from "deleted last week".

These tests pin both behaviours, including the removed -> renamed case the
issue's acceptance criteria name explicitly.
"""

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("audit_api_wiring", Path(__file__).parent / "audit_api_wiring.py")
audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit)


class TestSuggestRoutes:
    """`suggest_routes` — "did you mean …?" for a dead call."""

    BACKEND = {
        "/api/devices/paired",
        "/api/devices/{p}",
        "/api/knowledge/search",
        "/api/knowledge/documents",
        "/api/chat/sessions",
    }

    def test_renamed_endpoint_suggests_its_replacement(self):
        """The acceptance case: removed path -> the surviving sibling."""
        assert audit.suggest_routes("/api/devices/pairing", self.BACKEND)[0] == "/api/devices/paired"

    def test_suggestions_are_capped_and_ordered_best_first(self):
        suggestions = audit.suggest_routes("/api/knowledge/searches", self.BACKEND, limit=2)

        assert suggestions[0] == "/api/knowledge/search"
        assert len(suggestions) <= 2

    def test_unrelated_path_suggests_nothing(self):
        """Better silent than sending someone to rewire against a wrong route."""
        assert audit.suggest_routes("/api/completely/unrelated/thing", self.BACKEND) == []

    def test_api_stripped_routes_still_match(self):
        """Static mode's route table has no /api prefix — suggestions must still work."""
        stripped = {"/devices/paired", "/knowledge/search"}

        assert audit.suggest_routes("/api/devices/pairing", stripped) == ["/devices/paired"]

    def test_empty_backend_is_not_an_error(self):
        """A failed OpenAPI dump must not turn every finding into a crash."""
        assert audit.suggest_routes("/api/devices/pairing", set()) == []

    def test_segment_agreement_beats_raw_string_length(self):
        """Pure difflib favours long look-alikes; the renamed sibling must win."""
        backend = {"/api/agents/status", "/api/agents/status/history/detailed/report"}

        assert audit.suggest_routes("/api/agents/state", backend)[0] == "/api/agents/status"


class TestAuditBaseline:
    """`audit_baseline` — stop the baseline from absorbing removals."""

    BACKEND = {"/api/devices/paired", "/api/devices/v2/pairing", "/api/chat/sessions"}

    def test_removed_endpoint_in_baseline_is_surfaced_for_rematch(self):
        """Gap 2: a baselined call whose endpoint was renamed must not stay hidden.

        Only the route that still serves the ``pairing`` resource counts as the
        rename; the similarly-named ``/api/devices/paired`` neighbour is not it.
        """
        baseline = {"/api/devices/pairing"}
        unwired_all = {"/api/devices/pairing": {"src/x.ts"}}
        frontend = {"/api/devices/pairing": {"src/x.ts"}}

        health = audit.audit_baseline(baseline, unwired_all, frontend, self.BACKEND)

        assert health["rematch"] == [("/api/devices/pairing", ["/api/devices/v2/pairing"])]
        assert health["resolved"] == []

    def test_baselined_call_that_now_has_a_route_is_prunable(self):
        """Otherwise the baseline only ever grows."""
        baseline = {"/api/chat/sessions"}
        frontend = {"/api/chat/sessions": {"src/x.ts"}}

        health = audit.audit_baseline(baseline, {}, frontend, self.BACKEND)

        assert [p for p, _ in health["resolved"]] == ["/api/chat/sessions"]

    def test_baselined_call_no_longer_made_is_prunable(self):
        """Residue from frontend code that moved on."""
        health = audit.audit_baseline({"/api/gone/away"}, {}, {}, self.BACKEND)

        assert [p for p, _ in health["absent"]] == ["/api/gone/away"]

    def test_genuinely_unimplemented_call_stays_suppressed(self):
        """The baseline's legitimate use must keep working — no new noise."""
        baseline = {"/api/future/feature"}
        unwired_all = {"/api/future/feature": {"src/x.ts"}}
        frontend = {"/api/future/feature": {"src/x.ts"}}

        health = audit.audit_baseline(baseline, unwired_all, frontend, self.BACKEND)

        assert health == {
            "rematch": [],
            "namespace_only": [],
            "resolved": [],
            "absent": [],
        }

    def _health_for(self, path, backend):
        """Classify a single still-unwired baselined *path* against *backend*."""
        return audit.audit_baseline({path}, {path: {"src/x.ts"}}, {path: {"src/x.ts"}}, backend)

    def test_surviving_sibling_is_not_reported_as_a_rename(self):
        """#12894: an unimplemented endpoint beside implemented siblings is not drift.

        ``_similarity`` weights leading-segment agreement, so every sibling in a
        live namespace clears the suggestion floor. Treating that as a rename
        turned a baseline of never-built endpoints into "29 renamed endpoints".
        """
        health = self._health_for("/api/system/restart", {"/api/system/health"})

        assert health["rematch"] == []
        assert health["namespace_only"] == [("/api/system/restart", ["/api/system/health"])]

    def test_same_resource_in_another_namespace_is_not_a_rename(self):
        """``/api/browser/execute`` is not served by ``/api/workflow/execute``."""
        health = self._health_for("/api/browser/execute", {"/api/workflow/execute"})

        assert health["rematch"] == []
        assert [p for p, _ in health["namespace_only"]] == ["/api/browser/execute"]

    def test_pluralised_resource_is_a_rename(self):
        """``category`` -> ``categories`` is the real drift #12894 found."""
        health = self._health_for(
            "/api/knowledge_base/category/{p}", {"/api/knowledge_base/categories/{p}"}
        )

        assert health["rematch"] == [
            ("/api/knowledge_base/category/{p}", ["/api/knowledge_base/categories/{p}"])
        ]

    @pytest.mark.parametrize(
        "call,route",
        [
            ("/api/monitor/services", "/api/monitor/v2/service"),
            ("/api/monitor/service", "/api/monitor/v2/services"),
        ],
    )
    def test_plurality_matches_in_both_directions(self, call, route):
        """``services``/``service`` must match however the pair is ordered."""
        health = self._health_for(call, {route})

        assert health["rematch"] == [(call, [route])]

    def test_relocated_resource_is_a_rename(self):
        """Same namespace, same resource, deeper path — the classic rename."""
        health = self._health_for("/api/browser/click", {"/api/browser/mcp/click"})

        assert health["rematch"] == [("/api/browser/click", ["/api/browser/mcp/click"])]


@pytest.mark.parametrize("path", ["/api/devices/pairing", "/api/knowledge/searches"])
def test_print_call_emits_suggestion_lines(capsys, path):
    """The audit output itself must carry the guidance, not just the API."""
    audit._print_call(path, {"src/x.ts"}, TestSuggestRoutes.BACKEND)

    out = capsys.readouterr().out
    assert "did you mean" in out
    assert "<- src/x.ts" in out
