"""Canonical event_type strings for LiveEventManager payloads.

Frontend consumers filter on these values; backend publishers must import
from here rather than using string literals, to prevent casing drift (#5014).

Only event types that are *actually published today* via publish_live_event
are listed here.  Speculative / future types must not be added until a
real call-site exists.
"""

# Agent loop — approval bridge (loop.py → LiveEventManager → WebSocket)
# Frontend: autobot-frontend/src/composables/useToolApproval.ts
APPROVAL_REQUIRED = "APPROVAL_REQUIRED"

# Heartbeat scheduler (services/heartbeat_scheduler.py)
HEARTBEAT_RUN_STARTED = "heartbeat_run_started"
HEARTBEAT_RUN_COMPLETED = "heartbeat_run_completed"

# RAG service retrieval feedback (services/rag_service.py)
RAG_RETRIEVAL = "rag_retrieval"

# Agent loop — abstention outcome (loop.py → LiveEventManager → WebSocket)
# Emitted when confidence stays below floor for confidence_window iterations.
# Frontend consumers can surface a distinct "abstained" badge for the task.
AGENT_ABSTAINED = "agent_abstained"
