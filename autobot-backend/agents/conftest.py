# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Local pytest configuration for agents tests (#18094).

``agents/npu_code_search_patterns.language_name_for_extension`` delegates to the canonical
``code_intelligence.base_analyzer.detect_language``. The top-level conftest stubs
the ``code_intelligence.base_analyzer`` submodule as a MagicMock (the package
itself is no longer stubbed, #18070); a mock detector would hand every agents
test a ``MagicMock`` language. ``base_analyzer`` is a leaf (stdlib plus
``autobot_shared``), so it is real-loaded around each agents test
through ``StubSet``, whose ``restore`` puts the previous ``sys.modules`` entry
and the parent-package attribute back afterwards, so nothing leaks into later modules.

Test modules here must import ``code_intelligence.base_analyzer`` inside tests,
not at module level: collection happens before the fixture runs.
"""

from pathlib import Path

import pytest

from testkit.module_stubs import StubSet

_NAME = "code_intelligence.base_analyzer"
_PATH = Path(__file__).resolve().parent.parent / "code_intelligence" / "base_analyzer.py"


@pytest.fixture(autouse=True)
def _real_base_analyzer():
    stubs = StubSet()
    stubs.real_load(_NAME, _PATH)
    try:
        yield
    finally:
        stubs.restore()
