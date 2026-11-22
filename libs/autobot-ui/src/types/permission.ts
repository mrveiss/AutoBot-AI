// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * @autobot/ui — a tool permission rule as the backend serves it, declared once (#19910).
 *
 * `PermissionRuleResponse` (`autobot-backend/api/schemas_system.py`) always carries a
 * `description` (the matcher's dataclass defaults it to ""), so a rule read from the
 * backend has one; an absent description is never a state a reader has to handle.
 */

export interface PermissionRule {
  tool: string
  pattern: string
  action: 'allow' | 'ask' | 'deny'
  description: string
}
