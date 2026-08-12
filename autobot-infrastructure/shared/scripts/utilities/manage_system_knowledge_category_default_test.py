# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Coverage for the ``category`` default in ``_build_workflows_template`` (#14047).

The category is an unconditional template literal (no caller-supplied
override path) -- only the fallback value itself is asserted.

Loaded by explicit path (review of #14047): ``pytest.ini`` sets
``--import-mode=importlib``, which does NOT add a test's own directory to
``sys.path`` (documented at pytest.ini lines 10-13 for the same trap in
``pipeline-scripts``), so a bare ``from manage_system_knowledge import ...``
fails under real pytest invocation. ``autobot-infrastructure`` is also not
in ``pytest.ini`` testpaths, so this file does not run in CI yet (tracking
issue: wiring gap, filed alongside #14047) -- explicit-path loading makes it
individually correct so it starts passing the moment that gap closes, with
no further changes needed here.
"""

import importlib.util
from pathlib import Path

from constants.threshold_constants import CategoryDefaults

_MODULE_PATH = Path(__file__).parent / "manage_system_knowledge.py"


def _load_manage_system_knowledge():
    spec = importlib.util.spec_from_file_location("manage_system_knowledge_under_test", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_workflows_template_category_defaults_to_general():
    template = _load_manage_system_knowledge()._build_workflows_template("deploy")

    assert template["metadata"]["category"] == CategoryDefaults.GENERAL
