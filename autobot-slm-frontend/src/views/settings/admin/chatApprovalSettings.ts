// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Pure helpers for the chat approval settings panel (#20465): the two SLM setting keys
 * and the stored value forms the backend accepts.
 */

/** Approval categories an administrator has relaxed; read by the chat approval baseline. */
export const RELAXED_CATEGORIES_KEY = 'chat.relaxed_approval_categories'

/** Chats that used an attached file run tools without asking (off unless explicitly true). */
export const AUTO_APPROVE_ATTACHMENT_KEY = 'chat.auto_approve_attachment_turns'

/**
 * The approval categories, mirroring `ApprovalCategory` in `autobot_shared/tool_catalogue.py`.
 * A backend test keeps the two lists equal (a category missing here cannot be relaxed from the UI).
 */
export const APPROVAL_CATEGORIES = [
  'pushing commits',
  'publishing',
  'destructive operations',
  'rotating credentials',
  'sending externally',
  'writing files',
  'executing code',
  'deploying infrastructure',
  'discarding local changes',
  'writing data',
  'browser actions',
  'delegating work',
] as const

export type ApprovalCategory = (typeof APPROVAL_CATEGORIES)[number]

/** Relaxed categories from a stored `["cat", ...]` or `{"categories": [...]}`; unknown entries are dropped. */
export function parseRelaxedCategories(stored: unknown): ApprovalCategory[] {
  const raw = stored !== null && typeof stored === 'object' && !Array.isArray(stored)
    ? (stored as { categories?: unknown }).categories
    : stored
  if (!Array.isArray(raw)) return []
  return APPROVAL_CATEGORIES.filter((c) => raw.includes(c))
}

/** Auto-approve flag from a stored `true` or `{"enabled": true}`; anything else is off. */
export function parseAutoApprove(stored: unknown): boolean {
  if (stored === true) return true
  return (
    stored !== null && typeof stored === 'object' && (stored as { enabled?: unknown }).enabled === true
  )
}
