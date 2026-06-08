# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Shared Prompt Rules and Constants

Provides unified, reusable prompt rules and blocks that enforce critical
behavior patterns across all agents. This module eliminates prompt duplication
and ensures behavioral consistency.

Issue #7380: LEDGER vs EXECUTOR rule to clarify coordination tool semantics.
"""

LEDGER_VS_EXECUTOR_RULE = """
LEDGER vs EXECUTOR
- Coordination/planning tools (workflow_plan, agent_register, memory_store, swarm_init)
  return *records*, not deliverables. They complete instantly with no file written,
  no command run, no test executed.
- After ANY coordination call, IMMEDIATELY continue with the actual work yourself
  using your file/shell/code tools. Do not wait for the coordinator to "finish" —
  it already finished by returning the record.
- If you need something BUILT or EXECUTED, YOU build it. The coordinator just tracks.
"""
