# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Each failure-analysis intervention carries the one risk ladder the badge renders (#13422)."""

from services.causal_inference_engine import CausalAnalysisReport, Intervention, RecommendationType


class TestInterventionRiskTier:
    """#13422: each intervention carries the one risk ladder the frontend badge renders."""

    def _report(self, *risk_levels: str) -> dict:
        interventions = [
            Intervention(
                name=f"fix-{level}",
                description="",
                mechanism="",
                predicted_success_rate=0.5,
                cost_level="low",
                risk_level=level,
                recommendation_type=RecommendationType.IMMEDIATE,
                impact_rank=1,
                confidence=0.5,
            )
            for level in risk_levels
        ]
        return CausalAnalysisReport(task_id="t", error_description="e", interventions=interventions).to_dict()

    def test_risk_tier_sits_beside_the_unchanged_risk_level(self):
        rows = self._report("low", "medium", "HIGH")["interventions"]
        assert [(r["risk_level"], r["risk_tier"]) for r in rows] == [
            ("low", "low"),
            ("medium", "medium"),
            ("HIGH", "high"),
        ]

    def test_an_ungradable_risk_level_gives_no_tier_instead_of_failing_the_report(self):
        (row,) = self._report("unknown")["interventions"]
        assert row["risk_level"] == "unknown"
        assert row["risk_tier"] is None
