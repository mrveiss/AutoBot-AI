# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Conftest for the autobot-backend/tests/ directory.

Re-exports shared fixtures so pytest discovers them for every test file under
this directory.  A direct import is used instead of ``pytest_plugins`` because
pytest ≥9 hard-fails on ``pytest_plugins`` in any non-root conftest whenever
the conftest is loaded after configure — which depends on fragile testpath
glob details (#11521 review).

Heavy deps must NOT be imported at module scope here — see
``tests/helpers/llm_judge_fixture.py`` for the lazy-import pattern (the module
below imports only ``os``/``logging``/``pytest`` at module scope).
"""

from tests.helpers.llm_judge_fixture import llm_judge  # noqa: F401
