// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * @autobot/ui — the audit query envelope as the backend serves it, declared once (#20173).
 *
 * `AuditQueryResponse` (`autobot-backend/api/schemas_audit.py`) carries untyped entry dicts, so
 * each app narrows the row (`E`) and the echoed query (`Q`) to the shape it reads.
 */

export interface AuditQueryResponse<E = Record<string, unknown>, Q = Record<string, unknown>> {
  success: boolean
  total_returned: number
  has_more: boolean
  entries: E[]
  query: Q
}
