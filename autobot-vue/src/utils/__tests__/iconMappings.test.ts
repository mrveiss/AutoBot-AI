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
  getFileIcon,
  getPlatformIcon,
  getDocumentTypeIcon,
  getFileIconByMimeType,
  getStatusColorClass,
  getStatusIconWithColor,
  type StatusType,
  type FileType,
  type DocumentType,
  type PlatformType
} from '../iconMappings'

describe('iconMappings utility', () => {
  // ========================================
  // getStatusIcon() Tests
  // ========================================

  describe('getStatusIcon', () => {
    it('should return correct icon for healthy status', () => {
      expect(getStatusIcon('healthy')).toBe('fas fa-check-circle')
    })

    it('should return correct icon for warning status', () => {
      expect(getStatusIcon('warning')).toBe('fas fa-exclamation-triangle')
    })

    it('should return correct icon for error status', () => {
      expect(getStatusIcon('error')).toBe('fas fa-times-circle')
    })

    it('should return correct icon for degraded status', () => {
      expect(getStatusIcon('degraded')).toBe('fas fa-exclamation-triangle')
    })

    it('should return correct icon for critical status', () => {
      expect(getStatusIcon('critical')).toBe('fas fa-times-circle')
    })

    it('should return correct icon for offline status', () => {
      expect(getStatusIcon('offline')).toBe('fas fa-power-off')
    })

    it('should return correct icon for unknown status', () => {
      expect(getStatusIcon('unknown')).toBe('fas fa-question-circle')
    })

    it('should handle case-insensitive input', () => {
      expect(getStatusIcon('HEALTHY')).toBe('fas fa-check-circle')
      expect(getStatusIcon('Warning')).toBe('fas fa-exclamation-triangle')
      expect(getStatusIcon('ErRoR')).toBe('fas fa-times-circle')
    })

    it('should return unknown icon for invalid status', () => {
      expect(getStatusIcon('invalid-status')).toBe('fas fa-question-circle')
      expect(getStatusIcon('foobar')).toBe('fas fa-question-circle')
    })

    it('should handle null/undefined gracefully', () => {
      expect(getStatusIcon(null as any)).toBe('fas fa-question-circle')
      expect(getStatusIcon(undefined as any)).toBe('fas fa-question-circle')
      expect(getStatusIcon('' as any)).toBe('fas fa-question-circle')
    })

    // Issue #156 Fix: Removed tests for options parameter that doesn't exist in current API
    // Current getStatusIcon(status: string) only accepts status parameter
    // For color support, use getStatusIconWithColor(status) or getStatusColorClass(status) separately
  })

  // ========================================
  // Additional Function Tests
  // ========================================

  // Issue #156 Fix: Removed tests for non-existent functions (getConnectionIcon, getActionIcon, getIcon, iconMappings object)
  // The current API only exports: getFileIcon, getStatusIcon, getPlatformIcon, getDocumentTypeIcon,
  // getFileIconByMimeType, getStatusColorClass, getStatusIconWithColor
  // Tests for these additional functions should be added as needed
})
