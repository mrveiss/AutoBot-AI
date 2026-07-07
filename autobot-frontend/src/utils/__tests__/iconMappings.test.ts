// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Unit Tests for iconMappings.ts
 *
 * Test coverage for centralized icon mapping utility.
 * Target: 100% code coverage
 */

import { describe, it, expect } from 'vitest'
// Issue #156 Fix: Import only exported members from iconMappings
import {
  getStatusIcon,
  normalizeServiceStatus
} from '../iconMappings'

describe('iconMappings utility', () => {
  // ========================================
  // getStatusIcon() Tests
  // ========================================

  describe('getStatusIcon', () => {
    it('should return correct icon for healthy status', () => {
      expect(getStatusIcon('healthy')).toBe('check-circle')
    })

    it('should return correct icon for warning status', () => {
      expect(getStatusIcon('warning')).toBe('exclamation-triangle')
    })

    it('should return correct icon for error status', () => {
      expect(getStatusIcon('error')).toBe('times-circle')
    })

    it('should return correct icon for degraded status', () => {
      expect(getStatusIcon('degraded')).toBe('exclamation-triangle')
    })

    it('should return correct icon for critical status', () => {
      // 'critical' is not a direct key in statusIcons — falls through to unknown
      expect(getStatusIcon('critical')).toBe('question-circle')
    })

    it('should return correct icon for offline status', () => {
      expect(getStatusIcon('offline')).toBe('times-circle')
    })

    it('should return correct icon for unknown status', () => {
      expect(getStatusIcon('unknown')).toBe('question-circle')
    })

    it('should handle case-insensitive input', () => {
      expect(getStatusIcon('HEALTHY')).toBe('check-circle')
      expect(getStatusIcon('Warning')).toBe('exclamation-triangle')
      expect(getStatusIcon('ErRoR')).toBe('times-circle')
    })

    it('should return unknown icon for invalid status', () => {
      expect(getStatusIcon('invalid-status')).toBe('question-circle')
      expect(getStatusIcon('foobar')).toBe('question-circle')
    })

    it('should handle empty string gracefully', () => {
      expect(getStatusIcon('')).toBe('question-circle')
    })

    it('should throw on null/undefined input', () => {
      expect(() => getStatusIcon(null as unknown as string)).toThrow()
      expect(() => getStatusIcon(undefined as unknown as string)).toThrow()
    })

    // Issue #156 Fix: Removed tests for options parameter that doesn't exist in current API
    // Current getStatusIcon(status: string) only accepts status parameter
    // For color support, use getStatusIconWithColor(status) or getStatusColorClass(status) separately
  })

  // ========================================
  // Additional Function Tests
  // ========================================

  // Issue #156 Fix: Removed tests for non-existent functions (getConnectionIcon, getActionIcon, getIcon, iconMappings object)
  // The current API only exports:  getStatusIcon,
  //    normalizeServiceStatus
  // Tests for these additional functions should be added as needed

  // ========================================
  // normalizeServiceStatus() Tests (#2076)
  // ========================================

  describe('normalizeServiceStatus', () => {
    it('should map backend healthy values to healthy', () => {
      expect(normalizeServiceStatus('healthy')).toBe('healthy')
      expect(normalizeServiceStatus('online')).toBe('healthy')
      expect(normalizeServiceStatus('up')).toBe('healthy')
      expect(normalizeServiceStatus('running')).toBe('healthy')
      expect(normalizeServiceStatus('available')).toBe('healthy')
      expect(normalizeServiceStatus('connected')).toBe('healthy')
    })

    it('should map backend degraded values to warning', () => {
      expect(normalizeServiceStatus('degraded')).toBe('warning')
      expect(normalizeServiceStatus('warning')).toBe('warning')
      expect(normalizeServiceStatus('pending')).toBe('warning')
    })

    it('should map backend unhealthy values to error', () => {
      expect(normalizeServiceStatus('unhealthy')).toBe('error')
      expect(normalizeServiceStatus('error')).toBe('error')
      expect(normalizeServiceStatus('offline')).toBe('error')
      expect(normalizeServiceStatus('down')).toBe('error')
      expect(normalizeServiceStatus('unavailable')).toBe('error')
      expect(normalizeServiceStatus('not_configured')).toBe('error')
      expect(normalizeServiceStatus('not_initialized')).toBe('error')
      expect(normalizeServiceStatus('import_error')).toBe('error')
    })

    it('should handle case-insensitive input', () => {
      expect(normalizeServiceStatus('HEALTHY')).toBe('healthy')
      expect(normalizeServiceStatus('Degraded')).toBe('warning')
      expect(normalizeServiceStatus('UNHEALTHY')).toBe('error')
    })

    it('should return error for unknown status values', () => {
      expect(normalizeServiceStatus('unknown-value')).toBe('error')
      expect(normalizeServiceStatus('')).toBe('error')
    })
  })
})
