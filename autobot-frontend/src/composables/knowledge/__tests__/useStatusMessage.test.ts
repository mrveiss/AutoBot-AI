// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest'
import { STATUS_SUCCESS_DISMISS_MS, useStatusMessage } from '../useStatusMessage'

describe('useStatusMessage (#19669)', () => {
  it('shows a line, gives each show a new id, and clears', () => {
    const { statusMessage, showStatus, clearStatus } = useStatusMessage()
    showStatus('error', 'boom')
    const first = statusMessage.value?.id
    showStatus('error', 'boom')
    expect(statusMessage.value).toMatchObject({ type: 'error', text: 'boom' })
    expect(statusMessage.value?.id).not.toBe(first)
    clearStatus()
    expect(statusMessage.value).toBeNull()
  })

  it('auto-dismisses only a success line', () => {
    const { showStatus, statusAutoDismiss } = useStatusMessage()
    expect(statusAutoDismiss.value).toBe(0)
    showStatus('success', 'done')
    expect(statusAutoDismiss.value).toBe(STATUS_SUCCESS_DISMISS_MS)
    showStatus('warning', 'careful')
    expect(statusAutoDismiss.value).toBe(0)
  })
})
