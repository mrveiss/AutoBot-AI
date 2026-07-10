# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Top-level conftest for the autobot-backend/tests/ directory.

Registers shared test fixtures used across multiple test files under this
directory, including the llm_judge fixture added in #11521.

Heavy deps must NOT be imported at module scope here — see
``tests/helpers/llm_judge_fixture.py`` for the lazy-import pattern.
"""

pytest_plugins = [
    "tests.helpers.llm_judge_fixture",
]
