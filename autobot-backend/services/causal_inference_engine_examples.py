# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
# flake8: noqa: E501
"""
CausalInferenceEngine Examples - Production scenarios and expected outputs.

Long descriptive strings in this examples file intentionally exceed
line-length=120 for readability (file-level noqa above).

Issue #4069: Real-world examples showing how the engine analyzes failures.

This file demonstrates:
1. Database pool exhaustion cascade
2. Memory leak (gradual degradation)
3. Multi-factor failure (confounders)
4. Single cause (clear root cause)
5. Sparse data (graceful degradation)

Each scenario includes:
- Error event
- Causal chain
- Confounders
- Interventions
- Recommendations
- CausalSeverity assessment
"""

from services.causal_inference_engine import (
    CausalAnalysisReport,
    CausalSeverity,
    Intervention,
    RecommendationType,
)
from services.root_cause_analyzer import CausalEvent

# =============================================================================
# Scenario 1: Database Pool Exhaustion Cascade
# =============================================================================
# Real-world scenario:
#   - Traffic spike hits service at 10:00 AM
#   - Slow database query is introduced in deployment at 9:50 AM
#   - Query holds connections longer than before
#   - Connection pool exhausts within 10 minutes
#   - New requests queue, increasing latency exponentially
#   - Cascades to dependent services (timeout, retry storms)
#
# Causal chain: Traffic spike → Slow query → Held connections → Pool exhaustion → Cascading timeouts
#
# Root cause: The deployment at 9:50 AM introduced an N+1 query pattern
# Confounders: Simultaneous traffic spike (amplified the issue)
# Expected severity: CRITICAL (cascading, multi-factor)

EXAMPLE_1_POOL_EXHAUSTION = {
    "scenario": "Database Pool Exhaustion",
    "timeline": "2026-04-10T10:00:00Z to 2026-04-10T10:15:00Z",
    "error_description": "Critical: Database connection pool exhausted, requests queuing, latency spike 200ms → 5000ms",
    "causal_chain": [
        {
            "depth": 0,
            "event_type": "timeout",
            "name": "Request timeout",
            "description": "HTTP request timeout waiting for database connection from pool",
            "timestamp": "2026-04-10T10:12:00Z",
            "confidence": 0.95,
        },
        {
            "depth": 1,
            "event_type": "resource_exhaustion",
            "name": "Connection pool exhausted",
            "description": "All 30 connections in pool are in use, queue at 150+ waiting requests",
            "timestamp": "2026-04-10T10:10:00Z",
            "confidence": 0.98,
        },
        {
            "depth": 2,
            "event_type": "slow_query",
            "name": "Slow database query",
            "description": "Query takes 45-60 seconds instead of 5 seconds, holds connection for too long",
            "timestamp": "2026-04-10T10:05:00Z",
            "confidence": 0.92,
        },
        {
            "depth": 3,
            "event_type": "code_change",
            "name": "N+1 query pattern introduced",
            "description": "Deployment at 2026-04-10T09:50:00Z added nested loops over related entities",
            "timestamp": "2026-04-10T09:50:00Z",
            "confidence": 0.85,
        },
    ],
    "confounders": [
        {
            "event_type": "traffic_spike",
            "name": "Simultaneous traffic spike",
            "description": "Request rate increased from 500 QPS to 3000 QPS at 10:00 AM",
            "confidence": 0.9,
        }
    ],
    "confounding_strength": 0.35,  # Moderate; issue exists without spike, but spike triggers it
    "interventions": [
        {
            "name": "Increase connection pool size",
            "description": "Grow pool from 30 to 100 connections",
            "mechanism": "More connections available, reduces queueing and timeout rate",
            "predicted_success_rate": 0.85,
            "cost_level": "medium",
            "risk_level": "low",
            "recommendation_type": "short_term",
            "impact_rank": 1,
            "confidence": 0.9,
            "evidence": ["Direct metric: all 30 connections exhausted within 10min"],
        },
        {
            "name": "Optimize N+1 query pattern",
            "description": "Batch queries or use JOINs instead of nested loops",
            "mechanism": "Fewer queries per request, shorter connection hold time",
            "predicted_success_rate": 0.95,
            "cost_level": "high",
            "risk_level": "low",
            "recommendation_type": "long_term",
            "impact_rank": 2,
            "confidence": 0.92,
            "evidence": [
                "Deployment log shows code change",
                "Query time increased 10x",
            ],
        },
        {
            "name": "Implement query timeout",
            "description": "Cancel any query taking >10 seconds",
            "mechanism": "Prevents held connections from blocking pool indefinitely",
            "predicted_success_rate": 0.7,
            "cost_level": "low",
            "risk_level": "medium",
            "recommendation_type": "short_term",
            "impact_rank": 3,
            "confidence": 0.75,
            "evidence": ["Queries now hold connections 45-60 seconds"],
        },
    ],
    "severity": "critical",
    "confidence": 0.88,
    "recommendations": [
        "[URGENT] SHORT-TERM: Increase connection pool size from 30 to 100 connections (85% success likelihood). Reason: More connections available reduces queueing and timeout rate",
        "LONG-TERM: Optimize N+1 query pattern via batching or JOINs (95% success likelihood). Reason: Fewer queries per request, shorter connection hold time",
    ],
}


# =============================================================================
# Scenario 2: Memory Leak (Gradual Degradation)
# =============================================================================
# Real-world scenario:
#   - Service gradually consumes more memory over 48 hours
#   - Each request leaks ~100 bytes (not returned to OS)
#   - At 1000 QPS, this accumulates to ~400 MB/day
#   - After 48 hours, process consumes 10 GB of 12 GB available
#   - OOM killer terminates process at 2:15 AM (outside business hours)
#
# Causal chain: Memory leak → Gradual growth → Near limit → Allocation fails → OOM
#
# Root cause: Unreleased buffer in request handler
# Confounders: None (single-factor failure)
# Expected severity: DEGRADED (kills one instance, others handle requests)

EXAMPLE_2_MEMORY_LEAK = {
    "scenario": "Memory Leak",
    "timeline": "2026-04-08T02:00:00Z (48-hour accumulation)",
    "error_description": "Out of memory: Process killed by OOM killer after 48-hour memory leak accumulation",
    "causal_chain": [
        {
            "depth": 0,
            "event_type": "out_of_memory",
            "name": "OOM killer terminates process",
            "description": "Process tried to allocate memory but system was at 99% capacity (11.8 GB / 12 GB used)",
            "timestamp": "2026-04-08T02:15:30Z",
            "confidence": 0.99,
        },
        {
            "depth": 1,
            "event_type": "memory_pressure",
            "name": "Memory usage at critical level",
            "description": "Process memory grew from 2 GB at startup to 10 GB over 48 hours",
            "timestamp": "2026-04-08T02:00:00Z",
            "confidence": 0.98,
        },
        {
            "depth": 2,
            "event_type": "memory_leak",
            "name": "Memory leak in request handler",
            "description": "Each request leaks ~100 bytes (unreleased buffer). 1000 QPS × 100 bytes = 100 KB/sec = 400 MB/day",
            "timestamp": "2026-04-06T02:00:00Z",
            "confidence": 0.85,
        },
    ],
    "confounders": [],
    "confounding_strength": 0.0,  # Single-factor failure
    "interventions": [
        {
            "name": "Increase memory allocation to system",
            "description": "Add 16 GB RAM (increase from 12 GB to 28 GB)",
            "mechanism": "Process can grow larger before hitting OOM limit",
            "predicted_success_rate": 0.95,
            "cost_level": "medium",
            "risk_level": "low",
            "recommendation_type": "short_term",
            "impact_rank": 1,
            "confidence": 0.95,
            "evidence": ["Direct 48-hour growth from 2 GB to 10 GB"],
        },
        {
            "name": "Find and fix memory leak",
            "description": "Profile memory usage with pprof, identify unreleased buffers",
            "mechanism": "Fix the source of the leak, memory stops accumulating",
            "predicted_success_rate": 0.92,
            "cost_level": "high",
            "risk_level": "low",
            "recommendation_type": "long_term",
            "impact_rank": 2,
            "confidence": 0.88,
            "evidence": [
                "Memory growth is linear over time",
                "Leak rate ~100 bytes/request",
            ],
        },
        {
            "name": "Implement memory limits via cgroup",
            "description": "Set hard memory limit, restart process when approaching limit",
            "mechanism": "Graceful restart before OOM, better than kill by OOM killer",
            "predicted_success_rate": 0.8,
            "cost_level": "low",
            "risk_level": "low",
            "recommendation_type": "short_term",
            "impact_rank": 3,
            "confidence": 0.82,
            "evidence": ["OOM killer is heavy-handed, graceful restart is cleaner"],
        },
    ],
    "severity": "degraded",
    "confidence": 0.92,
    "recommendations": [
        "SHORT-TERM: Increase memory allocation to system from 12 GB to 28 GB (95% success likelihood). Reason: Process can grow larger before hitting OOM limit",
        "LONG-TERM: Find and fix memory leak via pprof profiling (92% success likelihood). Reason: Fix the source of the leak, memory stops accumulating",
    ],
}


# =============================================================================
# Scenario 3: Multi-Factor Failure (Cascading + Confounding)
# =============================================================================
# Real-world scenario:
#   - Service deployment at 3:00 PM introduces subtle bug: max_retries set to 0
#   - With normal load, retries are rare, so nobody notices initially
#   - At 6:00 PM, coordinated test/staging team simultaneously runs tests
#   - Traffic spikes to 10x normal (combines prod + test load on shared database)
#   - Transient network failures (normal 0.1% rate) now cause permanent failures (no retries)
#   - Database connection pool exhaustion (under test load)
#   - Multiple independent causes: buggy retry logic + network instability + test load
#
# Causal chain:
#   Primary: max_retries=0 (introduced in deployment)
#   Triggering: Network flakiness (0.1% of requests fail temporarily)
#   Amplifying: Traffic spike (test load) overwhelms database
#
# Root cause: max_retries=0 disables resilience
# Confounders: Network flakiness, test load spike
# Expected severity: CRITICAL (cascading, multi-factor, production impact)

EXAMPLE_3_MULTI_FACTOR = {
    "scenario": "Multi-Factor Failure (Cascading + Confounding)",
    "timeline": "2026-04-10T18:00:00Z",
    "error_description": "Critical: 45% request failure rate. Combination of buggy retry logic, network instability, and traffic spike.",
    "causal_chain": [
        {
            "depth": 0,
            "event_type": "high_error_rate",
            "name": "45% of requests failing",
            "description": "Sudden jump from 0.1% to 45% error rate at 6:00 PM",
            "timestamp": "2026-04-10T18:00:00Z",
            "confidence": 0.99,
        },
        {
            "depth": 1,
            "event_type": "no_retries",
            "name": "Retry logic disabled",
            "description": "max_retries=0 in deployment at 3:00 PM disables all retry attempts",
            "timestamp": "2026-04-10T15:00:00Z",
            "confidence": 0.95,
        },
        {
            "depth": 2,
            "event_type": "code_change",
            "name": "Deployment introduced bug",
            "description": "Commit hash 7f3a2c: Changed max_retries from 3 to 0 (intended for testing)",
            "timestamp": "2026-04-10T15:00:00Z",
            "confidence": 0.98,
        },
    ],
    "confounders": [
        {
            "event_type": "network_flakiness",
            "name": "Network transient failures",
            "description": "Normal ~0.1% of requests experience transient network errors (normally retried and succeeded)",
            "confidence": 0.88,
        },
        {
            "event_type": "traffic_spike",
            "name": "Coordinated test load",
            "description": "Staging team ran full system test at 6:00 PM, adding 10x traffic to shared database",
            "confidence": 0.92,
        },
    ],
    "confounding_strength": 0.68,  # High; multiple independent factors contribute
    "interventions": [
        {
            "name": "Revert problematic deployment",
            "description": "Roll back commit 7f3a2c, restore max_retries=3",
            "mechanism": "Retry logic restored, transient failures now succeed on retry",
            "predicted_success_rate": 0.98,
            "cost_level": "low",
            "risk_level": "low",
            "recommendation_type": "immediate",
            "impact_rank": 1,
            "confidence": 0.98,
            "evidence": ["Root cause: max_retries=0", "Revert restores 99.9% uptime"],
        },
        {
            "name": "Separate test/staging database",
            "description": "Provision isolated database for test load",
            "mechanism": "Test traffic no longer competes with production load",
            "predicted_success_rate": 0.85,
            "cost_level": "high",
            "risk_level": "low",
            "recommendation_type": "long_term",
            "impact_rank": 2,
            "confidence": 0.80,
            "evidence": ["Confounding factor: shared database amplified impact"],
        },
        {
            "name": "Improve network resilience",
            "description": "Add circuit breakers, implement exponential backoff",
            "mechanism": "Transient failures handled gracefully even with high load",
            "predicted_success_rate": 0.75,
            "cost_level": "high",
            "risk_level": "low",
            "recommendation_type": "long_term",
            "impact_rank": 3,
            "confidence": 0.75,
            "evidence": ["Confounder: network flakiness normally tolerated via retries"],
        },
    ],
    "severity": "critical",
    "confidence": 0.90,
    "recommendations": [
        "[URGENT] IMMEDIATE: Revert problematic deployment (commit 7f3a2c) to restore max_retries=3 (98% success likelihood). Reason: Retry logic restored, transient failures now succeed on retry",
        "LONG-TERM: Separate test/staging database from production (85% success likelihood). Reason: Test traffic no longer competes with production load",
    ],
}


# =============================================================================
# Scenario 4: Single Clear Cause
# =============================================================================
# Real-world scenario:
#   - Service fails at exactly 2:00 AM (scheduled maintenance time)
#   - Dependency service (user DB) is rebooted for maintenance
#   - All user service calls fail with "connection refused"
#   - Alerts fire, on-call engineer checks calendar, sees maintenance scheduled
#   - Not a bug; expected behavior during maintenance window
#
# Causal chain: Dependency maintenance → Service down → Connection refused → Failures
#
# Root cause: Expected scheduled maintenance (not a bug)
# Confounders: None
# Expected severity: WARNING (expected behavior, no action needed)

EXAMPLE_4_SINGLE_CLEAR_CAUSE = {
    "scenario": "Single Clear Cause (Scheduled Maintenance)",
    "timeline": "2026-04-10T02:00:00Z",
    "error_description": "Service unavailable: User database rebooting for maintenance",
    "causal_chain": [
        {
            "depth": 0,
            "event_type": "connection_error",
            "name": "Connection refused to user database",
            "description": "Socket error: [Errno 111] Connection refused",
            "timestamp": "2026-04-10T02:00:15Z",
            "confidence": 0.99,
        },
        {
            "depth": 1,
            "event_type": "service_down",
            "name": "User database service is down",
            "description": "Database service not responding to connection attempts",
            "timestamp": "2026-04-10T02:00:00Z",
            "confidence": 0.98,
        },
        {
            "depth": 2,
            "event_type": "scheduled_maintenance",
            "name": "Scheduled maintenance window",
            "description": "User database scheduled reboot 2026-04-10T02:00:00Z - 2026-04-10T02:30:00Z (maintenance calendar)",
            "timestamp": "2026-04-10T02:00:00Z",
            "confidence": 0.99,
        },
    ],
    "confounders": [],
    "confounding_strength": 0.0,
    "interventions": [
        {
            "name": "Wait for maintenance to complete",
            "description": "Service will be back online at 2:30 AM",
            "mechanism": "Maintenance window ends, service restores normal connectivity",
            "predicted_success_rate": 1.0,
            "cost_level": "low",
            "risk_level": "low",
            "recommendation_type": "immediate",
            "impact_rank": 1,
            "confidence": 0.99,
            "evidence": ["Scheduled maintenance confirmed in calendar"],
        },
    ],
    "severity": "warning",
    "confidence": 0.99,
    "recommendations": [
        "WAIT: Scheduled maintenance in progress (ends 2026-04-10T02:30:00Z). Service will return to normal. No action needed.",
    ],
}


# =============================================================================
# Scenario 5: Sparse Data (Low Confidence)
# =============================================================================
# Real-world scenario:
#   - Rare error occurs once every few days
#   - Insufficient causal information to determine root cause
#   - Chain is shallow (only immediate error visible)
#   - Multiple plausible causes
#   - System recommends monitoring/profiling
#
# Causal chain: [Error] (no visible upstream causes)
#
# Root cause: Unknown (insufficient data)
# Confounders: Unknown
# Expected severity: WARNING (insufficient data to act)

EXAMPLE_5_SPARSE_DATA = {
    "scenario": "Sparse Data (Low Confidence)",
    "timeline": "2026-04-10T11:45:00Z (intermittent)",
    "error_description": "Intermittent error: Nil pointer exception in worker process (occurs ~1x per week)",
    "causal_chain": [
        {
            "depth": 0,
            "event_type": "panic",
            "name": "Nil pointer dereference",
            "description": "Runtime panic: attempt to read field of nil pointer",
            "timestamp": "2026-04-10T11:45:00Z",
            "confidence": 0.7,  # Low confidence; insufficient context
        },
    ],
    "confounders": [],
    "confounding_strength": 0.0,
    "interventions": [
        {
            "name": "Enable detailed logging and profiling",
            "description": "Collect stack traces, memory dumps, goroutine state before next occurrence",
            "mechanism": "Better data will reveal upstream cause",
            "predicted_success_rate": 0.8,
            "cost_level": "low",
            "risk_level": "low",
            "recommendation_type": "immediate",
            "impact_rank": 1,
            "confidence": 0.75,
            "evidence": ["Sparse data; need more information to diagnose"],
        },
        {
            "name": "Add nil checks in identified code path",
            "description": "Defensive nil checks on all pointer dereferences",
            "mechanism": "Catches underlying issue, prevents panic",
            "predicted_success_rate": 0.6,
            "cost_level": "medium",
            "risk_level": "low",
            "recommendation_type": "short_term",
            "impact_rank": 2,
            "confidence": 0.5,  # Low confidence; may not fix root cause
            "evidence": ["Without root cause data, defensive approach is best guess"],
        },
    ],
    "severity": "warning",
    "confidence": 0.35,  # Low confidence
    "recommendations": [
        "ENABLE PROFILING: Collect detailed logs and stack traces on next occurrence (80% likelihood improves diagnosis). Reason: Current data insufficient to identify root cause",
        "ADD DEFENSIVE CHECKS: Nil checks on pointer dereferences in worker process (60% likelihood prevents panic). Reason: May mitigate symptoms while investigating root cause",
    ],
}


# =============================================================================
# Helper Function: Generate Example Report
# =============================================================================


def create_example_report_1() -> CausalAnalysisReport:
    """Create example report: Database pool exhaustion."""
    return CausalAnalysisReport(
        task_id="task-pool-exhaustion-1",
        error_description=EXAMPLE_1_POOL_EXHAUSTION["error_description"],
        root_cause=CausalEvent(
            event_id="root-1",
            event_type="code_change",
            name="N+1 query pattern introduced",
            description="Deployment at 2026-04-10T09:50:00Z added nested loops over related entities",
            timestamp="2026-04-10T09:50:00Z",
            confidence=0.85,
            depth=3,
        ),
        causal_chain=[
            CausalEvent(
                event_id=f"e{i}",
                event_type=chain["event_type"],
                name=chain["name"],
                description=chain["description"],
                timestamp=chain["timestamp"],
                confidence=chain["confidence"],
                depth=chain["depth"],
            )
            for i, chain in enumerate(EXAMPLE_1_POOL_EXHAUSTION["causal_chain"])
        ],
        confounders=[
            CausalEvent(
                event_id="c1",
                event_type=conf["event_type"],
                name=conf["name"],
                description=conf["description"],
                timestamp="2026-04-10T10:00:00Z",
                confidence=conf["confidence"],
            )
            for conf in EXAMPLE_1_POOL_EXHAUSTION["confounders"]
        ],
        interventions=[
            Intervention(
                name=interv["name"],
                description=interv["description"],
                mechanism=interv["mechanism"],
                predicted_success_rate=interv["predicted_success_rate"],
                cost_level=interv["cost_level"],
                risk_level=interv["risk_level"],
                recommendation_type=RecommendationType(interv["recommendation_type"]),
                impact_rank=interv["impact_rank"],
                confidence=interv["confidence"],
                evidence=interv["evidence"],
            )
            for interv in EXAMPLE_1_POOL_EXHAUSTION["interventions"]
        ],
        severity=CausalSeverity(EXAMPLE_1_POOL_EXHAUSTION["severity"]),
        confidence=EXAMPLE_1_POOL_EXHAUSTION["confidence"],
        chain_depth=len(EXAMPLE_1_POOL_EXHAUSTION["causal_chain"]),
        confounding_strength=EXAMPLE_1_POOL_EXHAUSTION["confounding_strength"],
        recommendations=EXAMPLE_1_POOL_EXHAUSTION["recommendations"],
        analysis_status="success",
    )


if __name__ == "__main__":
    # Print example report
    example = create_example_report_1()
    import json

    print(json.dumps(example.to_dict(), indent=2))
