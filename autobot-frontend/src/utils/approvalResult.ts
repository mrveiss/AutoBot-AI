// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The answer to an approve/deny request is HTTP 200 even when it was refused, so
 * the body's `status` decides (#20674, #21174). `status: "error"` means the
 * approval is still pending: never report it as done.
 */

/** The backend's refusal when Redis cannot confirm the approval's state. */
export const APPROVAL_STATE_UNAVAILABLE = 'Approval state unavailable, retry'

export interface ApprovalResponseBody {
  status?: string
  error?: string
  [key: string]: unknown
}

/** The message to show for a refused approval answer, or `null` if the body is not an error. */
export function approvalErrorMessage(
  body: ApprovalResponseBody | null | undefined,
  t: (key: string) => string
): string | null {
  if (!body || body.status !== 'error') return null
  if (body.error === APPROVAL_STATE_UNAVAILABLE) return t('ui.commandPermission.approvalStateUnavailable')
  return body.error ?? t('ui.commandPermission.executionFailed')
}
