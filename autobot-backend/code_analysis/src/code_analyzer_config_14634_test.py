# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression test for CodeAnalyzer.__init__'s undefined-name bug (#14634).

``self.config = config`` referenced a name never imported or defined anywhere
in ``code_analyzer.py``, so every ``CodeAnalyzer()`` construction raised
``NameError`` -- and ``analyze_duplicates.py`` constructs one unconditionally,
so the "duplicates" analysis category could never complete a single run.

Same root pattern, same day (2026-02-06), as ``anti_pattern_detector.py``'s
own ``self.config = config`` (#6733, already removed there) -- the fix here
follows that precedent: the assignment is dead (no call site reads
``self.config`` anywhere in this module or the rest of the repo), so it is
removed rather than importing an unused symbol.
"""

import importlib.util

import pytest

_MODULE_PATH = "autobot-backend/code_analysis/src/code_analyzer.py"


def _load_code_analyzer_module():
    """Import code_analyzer.py by path; skip if its real dep chain (sklearn,
    numpy) isn't installed in this environment rather than failing the suite
    on an unrelated missing package."""
    spec = importlib.util.spec_from_file_location("code_analyzer_under_test", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except ImportError as exc:
        pytest.skip(f"code_analyzer.py's dependency chain unavailable: {exc}")
    return module


def test_construction_does_not_raise_nameerror():
    """#14634: constructing CodeAnalyzer() must not raise NameError on 'config'."""
    module = _load_code_analyzer_module()

    analyzer = module.CodeAnalyzer(redis_client=None, use_npu=False)

    assert analyzer.use_npu is False
    assert analyzer.similarity_threshold == 0.85
    assert not hasattr(analyzer, "config")
