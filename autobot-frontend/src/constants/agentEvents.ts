// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Agent Event Constants
 *
 * WebSocket event types for agent lifecycle and abstention (GH#6626).
 *
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 */

/**
 * Event emitted when an agent abstains from a task due to low confidence
 * across multiple iterations (GH#6626).
 *
 * Payload:
 * - task_id: string
 * - abstained: true
 * - abstention_reason: string
 * - iterations: number
 * - think_count: number
 */
export const AGENT_ABSTAINED = 'agent_abstained' as const

/**
 * Union type of all agent event types
 */
export type AgentEventType = typeof AGENT_ABSTAINED

/**
 * Payload structure for AGENT_ABSTAINED event
 */
export interface AgentAbstainedPayload {
  task_id: string
  abstained: true
  abstention_reason: string
  iterations: number
  think_count: number
}
