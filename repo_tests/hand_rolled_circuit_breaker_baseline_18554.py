# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Frozen allowlist of the circuit-breaker-shaped classes that exist today (#18554).

Each key is `<repo path>::<class>::<kind>`; the value is the reason it is not a second generic
breaker. The list may only SHRINK: a new match fails the guard, and an entry whose class
left the tree (or stopped matching) fails it too until the line is deleted. `FROZEN_TOTAL`
caps the length so a stale-then-refilled list cannot grow quietly.

`CLASS` = a class carrying both a failure threshold/count and a recovery/cooldown timeout.
`ENUM`  = a non-canonical enum with CLOSED / OPEN / HALF_OPEN members.
"""

from __future__ import annotations

_P = "autobot-backend/"
_S = "autobot_shared/"

ALLOWLIST: dict[str, str] = {
    # Per-entity routing state, not a call wrapper (verdict D4).
    _P
    + "agents/agent_orchestration/distributed_management.py::DistributedAgentManager::CLASS": (
        "KEEP-EXCEPTION B6: per-agent routing state with half-open probe dispatch; enum already canonical"
    ),
    _P
    + "services/load_balancer.py::Worker::CLASS": (
        "KEEP-EXCEPTION B5: per-NPU-worker breaker fields held in a dataclass"
    ),
    _P
    + "services/load_balancer.py::NPULoadBalancer::CLASS": (
        "KEEP-EXCEPTION B5: threads the per-worker threshold/timeout into each Worker"
    ),
    _P
    + "services/load_balancer.py::CircuitBreakerState::ENUM": (
        "B5 private enum with the same members as CircuitState; MIGRATE to CircuitState in a later slice"
    ),
    _S
    + "npu/integration.py::NPUWorkerPool::CLASS": (
        "KEEP-EXCEPTION B7: per-worker state; CIRCUIT_FAILURE_THRESHOLD / COOLDOWN, enum already canonical"
    ),
    _S
    + "service_registry_core.py::ServiceHealth::CLASS": (
        "KEEP-EXCEPTION B11: per-service health record with circuit_open_until skip window"
    ),
    _P
    + "utils/service_registry.py::ServiceRegistry::CLASS": (
        "KEEP-EXCEPTION B11: health-record skip window; thresholds from config circuit_breaker.service_registry.*"
    ),
    _P
    + "utils/service_registry.py::ServiceConfig::CLASS": (
        "KEEP-EXCEPTION B11: declarative per-service threshold/timeout fields, no breaker logic"
    ),
    # Redis-specific breaker, out of scope for the generic one (B4).
    _S
    + "redis_management/connection_manager.py::RedisConnectionManager::CLASS": (
        "KEEP-EXCEPTION B4: per-db Redis breaker with Prometheus events and pool semantics"
    ),
    _S
    + "redis_management/config.py::PoolConfig::CLASS": (
        "KEEP-EXCEPTION B4: carries the per-db Redis breaker threshold and timeout"
    ),
    # Hand-rolled copies awaiting migration or absorption.
    _P
    + "services/slack_approval_integration.py::SlackApprovalManager::CLASS": (
        "MIGRATE B8: genuine hand-rolled Redis-call breaker; moves onto CircuitBreaker.call_async in a later slice"
    ),
    _P
    + "error_handler.py::CircuitBreakerDecorator::CLASS": (
        "ABSORB B2: zero-caller duplicate of the shared breaker, retired under #14426"
    ),
    # Configures or defines the canonical breaker; not a second implementation.
    _P
    + "orchestration/workflow_executor.py::LegacyWorkflowExecutor::CLASS": (
        "reads CircuitBreakerDefaults to configure the canonical breaker; no state machine of its own"
    ),
    _S + "ssot_constants.py::CircuitBreakerDefaults::CLASS": "the SSOT default values, not a breaker",
    _S + "ssot_constants.py::CircuitState::ENUM": "the canonical CircuitState enum (#12656) every breaker shares",
}

#: The ceiling. Lower it with the list; raising it needs the guard's contrast pair re-read.
FROZEN_TOTAL = 15
