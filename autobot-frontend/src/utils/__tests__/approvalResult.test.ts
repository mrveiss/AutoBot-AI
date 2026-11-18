// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest'
import { approvalErrorMessage, APPROVAL_STATE_UNAVAILABLE } from '../approvalResult'

const t = (key: string) => `t:${key}`

describe('approvalErrorMessage (#21174)', () => {
  it('is null for a successful answer', () => {
    expect(approvalErrorMessage({ status: 'approved' }, t)).toBeNull()
    expect(approvalErrorMessage(null, t)).toBeNull()
  })

  it('translates the retry refusal', () => {
    expect(approvalErrorMessage({ status: 'error', error: APPROVAL_STATE_UNAVAILABLE }, t)).toBe(
      't:ui.commandPermission.approvalStateUnavailable'
    )
  })

  it('shows any other error text, or the generic failure', () => {
    expect(approvalErrorMessage({ status: 'error', error: 'boom' }, t)).toBe('boom')
    expect(approvalErrorMessage({ status: 'error' }, t)).toBe('t:ui.commandPermission.executionFailed')
  })

  it('treats an HTTP-200 comment answer with status error as a refusal (ChatInterface.onCommandCommented)', () => {
    const body = { status: 'error', error: APPROVAL_STATE_UNAVAILABLE }
    expect(approvalErrorMessage(body, t)).not.toBeNull()
  })
})
