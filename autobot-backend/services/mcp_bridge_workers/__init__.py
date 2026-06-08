# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot MCP isolated bridge workers (#3229)

"""
MCP isolated bridge workers package (#3229).

Houses worker processes that run MCP tool calls in sandboxed subprocesses,
insulating the main backend from tool failures and resource exhaustion.
"""
