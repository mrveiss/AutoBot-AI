# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#11498: a provider whose completion breaker is OPEN and still cooling must be
treated as unavailable (registry routes to the fallback chain) and must fail
fast BEFORE burning a shared rate-limit token — without breaking OPEN->HALF_OPEN
recovery. The read-only ``CircuitBreaker.is_rejecting`` predicate underpins both."""

import time

from circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    get_circuit_breaker_manager,
)


def _open_breaker(name: str, *, cooling: bool) -> CircuitBreaker:
    cb = CircuitBreaker(name, CircuitBreakerConfig(failure_threshold=1, recovery_timeout=30))
    cb.state = CircuitState.OPEN
    cb.last_failure_time = time.time() if cooling else (time.time() - 31)
    return cb


def test_is_rejecting_true_only_while_open_and_cooling():
    assert _open_breaker("a_service", cooling=True).is_rejecting is True


def test_is_rejecting_false_when_open_but_ready_to_probe():
    # Ready to probe -> NOT rejecting, so a real call can transition to HALF_OPEN.
    assert _open_breaker("b_service", cooling=False).is_rejecting is False


def test_is_rejecting_false_for_closed_and_half_open():
    cb = CircuitBreaker("c_service", CircuitBreakerConfig())
    assert cb.is_rejecting is False  # CLOSED
    cb.state = CircuitState.HALF_OPEN
    assert cb.is_rejecting is False


def test_is_rejecting_read_only_does_not_transition_open_to_half_open():
    cb = _open_breaker("d_service", cooling=False)  # ready to probe
    _ = cb.is_rejecting
    # Must NOT have consumed the probe transition — still OPEN until a real call.
    assert cb.state is CircuitState.OPEN


def test_registry_helper_flags_rejecting_provider():
    from llm_shared.provider_registry import ProviderRegistry

    mgr = get_circuit_breaker_manager()
    mgr.circuit_breakers["prov9_service"] = _open_breaker("prov9_service", cooling=True)
    try:
        assert ProviderRegistry._completion_breaker_is_rejecting("prov9") is True
        assert ProviderRegistry._completion_breaker_is_rejecting("no_such_provider") is False
    finally:
        mgr.circuit_breakers.pop("prov9_service", None)
