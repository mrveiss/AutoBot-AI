# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18094: the similarity-threshold triple has one owner, pinned by identity.

The repo-wide restatement sweep is ``repo_tests/defined_twice_18094_test.py``; this pins the
readers' bindings to the owner's objects.
"""

import ast
from pathlib import Path

_OWNER = "code_intelligence.similarity_thresholds"
_DETECTOR = Path(__file__).parent / "cross_language_patterns" / "detector.py"
_NAMES = {"SIMILARITY_HIGH", "SIMILARITY_MEDIUM", "SIMILARITY_LOW"}


def test_detector_imports_the_threshold_instead_of_redefining_it():
    # The package is stubbed by the top-level conftest, so read the source.
    tree = ast.parse(_DETECTOR.read_text(encoding="utf-8"))
    assigned = {t.id for n in tree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
    imported = {a.name for n in tree.body if isinstance(n, ast.ImportFrom) and n.module == _OWNER for a in n.names}

    assert assigned & _NAMES == set()
    assert "SIMILARITY_MEDIUM" in imported


def test_readers_share_the_owners_object():
    from code_intelligence import analytics_infrastructure
    from code_intelligence import similarity_thresholds as owner
    from code_intelligence.shared import analysis_base

    assert analysis_base.SIMILARITY_MEDIUM is owner.SIMILARITY_MEDIUM
    assert analytics_infrastructure.SIMILARITY_MEDIUM is owner.SIMILARITY_MEDIUM
    assert analytics_infrastructure.SIMILARITY_LOW is owner.SIMILARITY_LOW
