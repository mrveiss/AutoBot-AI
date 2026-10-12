# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Local pytest configuration for agents tests (#18094).

``agents/npu_code_search_patterns.detect_language`` delegates to the canonical
``code_intelligence.base_analyzer.detect_language``. The top-level conftest stubs
the ``code_intelligence.base_analyzer`` submodule as a MagicMock (the package
itself is no longer stubbed, #18070); a mock detector would hand every agents
test a ``MagicMock`` language. ``base_analyzer`` is a leaf (stdlib plus
``autobot_shared``), so it is real-loaded around each agents test
and the previous ``sys.modules`` entry (and the parent-package attribute)
is put back afterwards, so nothing leaks into later modules.

Test modules here must import ``code_intelligence.base_analyzer`` inside tests,
not at module level: collection happens before the fixture runs.
"""

import sys
from pathlib import Path

import pytest

from testkit.module_stubs import real_load_and_bind

_NAME = "code_intelligence.base_analyzer"
_PATH = Path(__file__).resolve().parent.parent / "code_intelligence" / "base_analyzer.py"
_ABSENT = object()


@pytest.fixture(autouse=True)
def _real_base_analyzer():
    parent = sys.modules.get("code_intelligence")
    previous_module = sys.modules.get(_NAME, _ABSENT)
    previous_attr = getattr(parent, "base_analyzer", _ABSENT) if parent is not None else _ABSENT
    real_load_and_bind(_NAME, _PATH)
    try:
        yield
    finally:
        if previous_module is _ABSENT:
            sys.modules.pop(_NAME, None)
        else:
            sys.modules[_NAME] = previous_module
        if parent is not None:
            if previous_attr is _ABSENT:
                parent.__dict__.pop("base_analyzer", None)
            else:
                setattr(parent, "base_analyzer", previous_attr)
