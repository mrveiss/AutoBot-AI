# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One canonical CircuitState (#12656, part of #12645).

Three byte-identical definitions existed: `circuit_breaker.py`,
`agents/agent_orchestration/types.py`, and the npu-worker's copy in
`core/npu_integration.py`.

Duplication was not the only cost. Three separate `Enum` classes with the same
member names are **not interchangeable** — `A.OPEN == B.OPEN` is False even
though both carry `"open"`. Any state passed across those boundaries compared
unequal, silently, and no test would notice because each module only ever
compared against its own copy.

These tests pin the convergence and that property.
"""

import ast
from pathlib import Path

import pytest

from autobot_shared.ssot_constants import CircuitState

_REPO = Path(__file__).resolve().parents[1]


def _class_defs(rel_path: str, name: str) -> list[ast.ClassDef]:
    """Top-level (module-scope) class definitions of *name* in *rel_path*."""
    tree = ast.parse((_REPO / rel_path).read_text(encoding="utf-8"))
    return [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name]


class TestCanonicalDefinition:
    def test_members_are_unchanged(self):
        """Convergence must not quietly alter any state's wire value."""
        assert [s.value for s in CircuitState] == ["closed", "open", "half_open"]

    @pytest.mark.parametrize("member", ["CLOSED", "OPEN", "HALF_OPEN"])
    def test_every_member_survives(self, member):
        assert hasattr(CircuitState, member)


class TestForksConverged:
    """Each former copy must now resolve to the canonical enum."""

    @pytest.mark.parametrize(
        "rel_path",
        [
            "autobot-backend/circuit_breaker.py",
            "autobot-backend/agents/agent_orchestration/types.py",
        ],
    )
    def test_backend_copies_are_gone(self, rel_path):
        assert not _class_defs(rel_path, "CircuitState"), f"{rel_path} still defines its own CircuitState"

    @pytest.mark.parametrize(
        "rel_path",
        [
            "autobot-backend/circuit_breaker.py",
            "autobot-backend/agents/agent_orchestration/types.py",
            "autobot-npu-worker/core/npu_integration.py",
        ],
    )
    def test_each_module_imports_the_canonical_one(self, rel_path):
        source = (_REPO / rel_path).read_text(encoding="utf-8")

        assert "from autobot_shared.ssot_constants import CircuitState" in source

    def test_worker_has_no_fork_left(self):
        """#12656 went further than a fallback: the worker re-exports from shared.

        The PyInstaller concern that justified a local fallback now lives in
        autobot_shared/npu, which imports the enum directly — so there is no
        second definition to keep in step.
        """
        rel = "autobot-npu-worker/core/npu_integration.py"
        source = (_REPO / rel).read_text(encoding="utf-8")

        assert not _class_defs(rel, "CircuitState"), "no CircuitState definition should remain"
        assert "from autobot_shared.ssot_constants import CircuitState" in source


def test_cross_module_identity_now_holds():
    """The bug the fork could cause: same member, different class, never equal."""
    import sys

    sys.path.insert(0, str(_REPO / "autobot-backend"))
    from circuit_breaker import CircuitState as FromBreaker

    assert FromBreaker is CircuitState
    assert FromBreaker.OPEN == CircuitState.OPEN
