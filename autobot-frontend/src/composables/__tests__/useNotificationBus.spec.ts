// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useNotificationBus } from '../useNotificationBus'

const mockShowToast = vi.fn()
const mockExtractApiErrorMessage = vi.fn()

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    showToast: mockShowToast,
    toasts: { value: [] },
    removeToast: vi.fn(),
    clearAllToasts: vi.fn(),
  }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  }),
}))

vi.mock('@/utils/errorExtract', () => ({
  extractApiErrorMessage: (...args: unknown[]) => mockExtractApiErrorMessage(...args),
}))

describe('useNotificationBus', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockShowToast.mockReset()
    mockExtractApiErrorMessage.mockReset()
    mockExtractApiErrorMessage.mockImplementation((_err: unknown, fallback: string) => fallback)
  })

  describe('notifyError', () => {
    it('shows a sticky error toast (duration 0)', () => {
      const bus = useNotificationBus()
      bus.notifyError('Something broke')
      expect(mockShowToast).toHaveBeenCalledWith('Something broke', 'error', 0)
    })

    it('sets lastError', () => {
      const bus = useNotificationBus()
      bus.notifyError('boom')
      expect(bus.lastError.value?.message).toBe('boom')
    })
  })

  describe('notifySuccess', () => {
    it('shows an auto-dismiss success toast', () => {
      const bus = useNotificationBus()
      bus.notifySuccess('Done')
      expect(mockShowToast).toHaveBeenCalledWith('Done', 'success', undefined)
    })
  })

  describe('notifyWarning', () => {
    it('shows a warning toast', () => {
      const bus = useNotificationBus()
      bus.notifyWarning('Watch out')
      expect(mockShowToast).toHaveBeenCalledWith('Watch out', 'warning', undefined)
    })
  })

  describe('notifyInfo', () => {
    it('shows an info toast', () => {
      const bus = useNotificationBus()
      bus.notifyInfo('FYI')
      expect(mockShowToast).toHaveBeenCalledWith('FYI', 'info', undefined)
    })
  })

  describe('notifyApiError', () => {
    it('extracts message via errorExtract', () => {
      mockExtractApiErrorMessage.mockReturnValue('Extracted message')
      const bus = useNotificationBus()
      bus.notifyApiError(new Error('raw'), { context: 'Loading data' })
      expect(mockExtractApiErrorMessage).toHaveBeenCalled()
      expect(mockShowToast).toHaveBeenCalledWith('Extracted message', 'error', 0)
    })

    it('uses retryable flag to pick warning toast', () => {
      mockExtractApiErrorMessage.mockReturnValue('timeout')
      const bus = useNotificationBus()
      bus.notifyApiError(new Error('timeout'), { retryable: true })
      expect(mockShowToast).toHaveBeenCalledWith('timeout', 'warning', undefined)
    })

    it('suppresses toast when silent=true', () => {
      const bus = useNotificationBus()
      bus.notifyApiError(new Error('quiet'), { silent: true })
      expect(mockShowToast).not.toHaveBeenCalled()
    })

    it('still sets lastError when silent', () => {
      const bus = useNotificationBus()
      bus.notifyApiError(new Error('quiet'), { silent: true })
      // lastError holds the original Error object (not the extracted string)
      expect(bus.lastError.value?.message).toBe('quiet')
    })
  })

  describe('clearError', () => {
    it('resets lastError to null', () => {
      const bus = useNotificationBus()
      bus.notifyError('err')
      expect(bus.lastError.value).not.toBeNull()
      bus.clearError()
      expect(bus.lastError.value).toBeNull()
    })
  })
})
