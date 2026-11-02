# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A feature nobody wrote a check for must not report implemented (#17559).

``_validate_single_feature`` ended with a bare ``return True`` for any feature
name the validator map did not know -- indistinguishable from a feature that
was checked and found present, and the same inversion #17089 removed one layer
up, where a phase reached 100% because two files existed. Three names were in
that state: ``containerization``, ``scalability`` and ``deployment_automation``
were declared in ``PHASE_CRITERIA['production_features']`` and matched nothing
in ``_get_feature_validators()``.

The correspondence check is the part that matters more than the three names.
Adding validators fixes today's instance; asserting that every declared feature
HAS one is what stops the next name being added without a check, which is how
those three arrived. ``TestTheSkipListStaysInStepWithWhatIsSkipped`` in
``phase_validation_paths_and_skips_17089_test.py`` is the pattern followed here.

WHY THE MODULE IS READ WITH ``ast`` RATHER THAN IMPORTED. ``phase_validation_system``
imports ``aiohttp``, ``psutil``, ``requests`` and ``autobot_shared.redis_client``
at module scope, and the last of those WRITES secret key material when none is
configured. A guard must not mutate the tree it guards.
"""

from __future__ import annotations

import ast
from pathlib import Path

from repo_tests._paths import repo_root

_SYSTEM = Path("autobot-infrastructure/shared/scripts/phase_validation_system.py")


def _system_tree() -> ast.Module:
    return ast.parse((repo_root() / _SYSTEM).read_text(encoding="utf-8"))


class TestEveryDeclaredFeatureHasAValidator:
    """#17559: a feature with no validator used to report implemented."""

    @staticmethod
    def _criteria_block() -> ast.Dict:
        return next(
            stmt.value
            for node in ast.walk(_system_tree())
            if isinstance(node, ast.ClassDef)
            for stmt in node.body
            if isinstance(stmt, ast.Assign) and any(getattr(t, "id", "") == "PHASE_CRITERIA" for t in stmt.targets)
        )

    @classmethod
    def _declared_features(cls) -> set[str]:
        found: set[str] = set()
        for criteria in cls._criteria_block().values:
            for key, value in zip(criteria.keys, criteria.values):
                # `performance_metrics` is a dict of thresholds handled by its
                # own validator, not a list of feature names.
                if ast.literal_eval(key).endswith("_features"):
                    found.update(ast.literal_eval(element) for element in value.elts)
        return found

    @staticmethod
    def _validator_names() -> set[str]:
        function = next(
            node
            for node in ast.walk(_system_tree())
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_get_feature_validators"
        )
        returned = next(stmt for stmt in ast.walk(function) if isinstance(stmt, ast.Return))
        return {ast.literal_eval(key) for key in returned.value.keys}

    def test_the_parse_found_both_sides(self) -> None:
        assert len(self._declared_features()) >= 20, "the criteria parse collapsed -- this guard would pass vacuously"
        assert len(self._validator_names()) >= 20, "the validator-map parse collapsed"

    def test_no_declared_feature_is_unvalidated(self) -> None:
        missing = sorted(self._declared_features() - self._validator_names())
        assert not missing, (
            "these features are declared in PHASE_CRITERIA with no entry in _get_feature_validators(), so "
            f"nothing checks them: {missing}. Give each one a validator, or remove the claim (#17559)"
        )

    def test_an_unvalidated_feature_is_not_reported_implemented(self) -> None:
        # Read as data rather than imported: see the module docstring.
        function = next(
            node
            for node in ast.walk(_system_tree())
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_validate_single_feature"
        )
        returned = [
            stmt.value.value
            for stmt in ast.walk(function)
            if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Constant)
        ]
        assert returned, "no literal return found in _validate_single_feature -- the parse missed the fallback"
        assert True not in returned, (
            "_validate_single_feature returns a literal True. A feature nobody wrote a check for would "
            "then be indistinguishable from one that was checked and found present (#17559)"
        )
