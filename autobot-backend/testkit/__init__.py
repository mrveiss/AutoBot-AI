# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Test-support helpers importable from any conftest (#13451).

Named ``testkit`` rather than ``testing`` or ``test_support``: pytest collects
``test_*.py``, and a top-level ``testing`` package risks colliding with
third-party names. ``autobot-backend`` is on pytest.ini's ``pythonpath``, so
``from testkit.module_stubs import StubSet`` resolves from any conftest.
"""
