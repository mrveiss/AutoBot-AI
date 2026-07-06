# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
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

# Agent loop — belief cache hit (loop.py → LiveEventManager → WebSocket)
# Emitted when a high-confidence cached assertion suppresses a redundant tool call.
BELIEF_CACHE_HIT = "belief_cache_hit"

# Agent loop — mid-task steering (#10543)
# Emitted when the loop absorbs a human steering message and acknowledges it.
# Frontend consumers can show the acknowledgement alongside approval controls.
STEERING_RECEIVED = "steering_received"

# Agent loop — ask-the-human (#10553)
# Emitted when the loop suspends to wait for a human answer to a clarifying question.
# Frontend consumers must render an answer affordance tied to question_id.
HUMAN_QUESTION = "human_question"

# Agent loop — human answer received (#10553)
# Emitted when the loop resumes after receiving the human's answer.
HUMAN_ANSWER_RECEIVED = "human_answer_received"

# Agent loop — adversarial pre-action verifier verdict (#10547)
# Emitted when the verifier completes a pass; shown to the human at the
# approval gate so the operator sees "verifier flagged X" before approving.
VERIFIER_VERDICT = "verifier_verdict"
