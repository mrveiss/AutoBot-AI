# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared fixtures for the orchestration test suite.

Issue #11754: circuit-breaker state is process-global (``CircuitBreakerManager``
singleton via ``lazy_singleton``), so step failures driven by one test file
(e.g. ``execution_modes_test.py`` exercising real failing steps through the
``workflow_step_execution`` breaker) tripped the breaker OPEN and made
unrelated tests fail with ``CircuitBreakerOpenError`` in group runs while
passing standalone.  Every orchestration test starts with all breakers CLOSED.
"""

import pytest


@pytest.fixture(autouse=True)
def _reset_circuit_breakers():
    """Reset all registered circuit breakers before each test (#11754).

    Import is deferred to test time so the fixture binds to the same
    ``circuit_breaker`` module object the production code uses (the root
    conftest real-loads/stubs modules during its own import).
    """
    from circuit_breaker import get_circuit_breaker_manager

    get_circuit_breaker_manager().reset_all_circuit_breakers()
    yield
