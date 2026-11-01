// Copyright (c) 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Whether a Company OS write answered 202 `pending_approval` (#8214): a request for the board exists, and
 * what it asked for (a hire, a higher budget limit) has not happened yet.
 */
export function isPendingApproval(result: unknown): boolean {
  return (result as { status?: string } | null)?.status === 'pending_approval'
}
