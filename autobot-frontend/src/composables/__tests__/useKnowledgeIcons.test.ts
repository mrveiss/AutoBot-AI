// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useKnowledgeIcons Composable Tests
 *
 * Split from useKnowledgeBase.test.ts (#5122).
 */

import { describe, it, expect, vi } from 'vitest'
import { useKnowledgeIcons } from '../knowledge/useKnowledgeIcons'

vi.mock('@/utils/iconMappings', () => ({
  getFileIcon: () => 'fas fa-file',
}))

describe('useKnowledgeIcons', () => {
  describe('getTypeIcon', () => {
    it('should return PDF icon for PDF documents', () => {
      const { getTypeIcon } = useKnowledgeIcons()
      expect(getTypeIcon('pdf')).toBe('fas fa-file-pdf')
    })

    it('should return code icon for JSON types', () => {
      const { getTypeIcon } = useKnowledgeIcons()
      expect(getTypeIcon('json')).toBe('fas fa-file-code')
    })

    it('should return image icon for image types', () => {
      const { getTypeIcon } = useKnowledgeIcons()
      expect(getTypeIcon('png')).toBe('fas fa-file-image')
      expect(getTypeIcon('jpg')).toBe('fas fa-file-image')
    })

    it('should return default file icon for unknown type', () => {
      const { getTypeIcon } = useKnowledgeIcons()
      expect(getTypeIcon('unknown')).toBe('fas fa-file')
    })
  })

  describe('getFileIcon', () => {
    it('should return folder icon for directories', () => {
      const { getFileIcon } = useKnowledgeIcons()
      const icon = getFileIcon('mydir', true)
      expect(icon).toContain('fas fa-folder')
    })

    it('should return styled icon for file with color class', () => {
      const { getFileIcon } = useKnowledgeIcons()
      const icon = getFileIcon('script.js', false)
      expect(icon).toContain('text-')
    })

    it('should apply different colors for different file types', () => {
      const { getFileIcon } = useKnowledgeIcons()
      const jsIcon = getFileIcon('app.js', false)
      const pyIcon = getFileIcon('script.py', false)
      const pdfIcon = getFileIcon('document.pdf', false)

      expect(jsIcon).not.toEqual(pyIcon)
      expect(pyIcon).not.toEqual(pdfIcon)
    })
  })

  describe('getOSBadgeClass', () => {
    it('should return success class for Linux', () => {
      const { getOSBadgeClass } = useKnowledgeIcons()
      expect(getOSBadgeClass('linux')).toBe('badge-success')
    })

    it('should return info class for Windows', () => {
      const { getOSBadgeClass } = useKnowledgeIcons()
      expect(getOSBadgeClass('windows')).toBe('badge-info')
    })

    it('should return warning class for macOS', () => {
      const { getOSBadgeClass } = useKnowledgeIcons()
      expect(getOSBadgeClass('macos')).toBe('badge-warning')
    })

    it('should return secondary class for unknown OS', () => {
      const { getOSBadgeClass } = useKnowledgeIcons()
      expect(getOSBadgeClass('unknown')).toBe('badge-secondary')
    })
  })

  describe('getMessageIcon', () => {
    it('should return info icon for info type', () => {
      const { getMessageIcon } = useKnowledgeIcons()
      const icon = getMessageIcon('info')
      expect(icon).toContain('fas fa-info-circle')
      expect(icon).toContain('text-blue-500')
    })

    it('should return success icon for success type', () => {
      const { getMessageIcon } = useKnowledgeIcons()
      const icon = getMessageIcon('success')
      expect(icon).toContain('fas fa-check-circle')
      expect(icon).toContain('text-green-500')
    })

    it('should return warning icon for warning type', () => {
      const { getMessageIcon } = useKnowledgeIcons()
      const icon = getMessageIcon('warning')
      expect(icon).toContain('fas fa-exclamation-triangle')
      expect(icon).toContain('text-yellow-500')
    })

    it('should return error icon for error type', () => {
      const { getMessageIcon } = useKnowledgeIcons()
      const icon = getMessageIcon('error')
      expect(icon).toContain('fas fa-times-circle')
      expect(icon).toContain('text-red-500')
    })

    it('should default to info icon for unknown type', () => {
      const { getMessageIcon } = useKnowledgeIcons()
      const icon = getMessageIcon('unknown')
      expect(icon).toContain('fas fa-info-circle')
    })
  })

  describe('formatTime', () => {
    it('should format timestamp to locale time string', () => {
      const { formatTime } = useKnowledgeIcons()
      const formatted = formatTime('2025-04-12T10:30:45Z')
      expect(typeof formatted).toBe('string')
      expect(formatted).toMatch(/\d{1,2}:\d{2}:\d{2}/)
    })

    it('should handle Date objects', () => {
      const { formatTime } = useKnowledgeIcons()
      const formatted = formatTime(new Date('2025-04-12T10:30:45Z'))
      expect(typeof formatted).toBe('string')
    })
  })
})
