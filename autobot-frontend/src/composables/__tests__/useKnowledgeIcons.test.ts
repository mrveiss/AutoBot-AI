// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useKnowledgeIcons Composable Tests
 *
 * Split from useKnowledgeBase.test.ts (#5122).
 *
 * #9724: the icon helpers were migrated to return canonical SVG IconName
 * values (e.g. "file-pdf") instead of Font Awesome class strings
 * (e.g. "fas fa-file-pdf"), because consumers render via <Icon :name="...">.
 * Expectations below assert the IconName the helper actually returns.
 */

import { describe, it, expect, vi } from 'vitest'
import { useKnowledgeIcons } from '../knowledge/useKnowledgeIcons'

// getFileIcon delegates to getFileIconName (#9724 IconName migration).
// Both are stubbed so the test exercises the helper, not the real mapping.
vi.mock('@/utils/iconMappings', () => ({
  getFileIcon: () => 'fas fa-file',
  getFileIconName: (name: string, isDir = false): string => {
    if (isDir) return 'folder'
    const ext = name.split('.').pop()?.toLowerCase()
    const map: Record<string, string> = {
      js: 'file-code',
      py: 'file-code',
      pdf: 'file-pdf',
    }
    return (ext && map[ext]) || 'file'
  },
}))

describe('useKnowledgeIcons', () => {
  describe('getTypeIcon', () => {
    it('should return PDF icon for PDF documents', () => {
      const { getTypeIcon } = useKnowledgeIcons()
      expect(getTypeIcon('pdf')).toBe('file-pdf')
    })

    it('should return code icon for JSON types', () => {
      const { getTypeIcon } = useKnowledgeIcons()
      expect(getTypeIcon('json')).toBe('file-code')
    })

    it('should return image icon for image types', () => {
      const { getTypeIcon } = useKnowledgeIcons()
      expect(getTypeIcon('png')).toBe('file-image')
      expect(getTypeIcon('jpg')).toBe('file-image')
    })

    it('should return default file icon for unknown type', () => {
      const { getTypeIcon } = useKnowledgeIcons()
      expect(getTypeIcon('unknown')).toBe('file')
    })
  })

  describe('getFileIcon', () => {
    it('should return folder icon for directories', () => {
      const { getFileIcon } = useKnowledgeIcons()
      const icon = getFileIcon('mydir', true)
      expect(icon).toBe('folder')
    })

    it('should return a file-code icon name for a script file', () => {
      const { getFileIcon } = useKnowledgeIcons()
      const icon = getFileIcon('script.js', false)
      expect(icon).toBe('file-code')
    })

    it('should map distinct extensions to their IconName', () => {
      const { getFileIcon } = useKnowledgeIcons()
      const jsIcon = getFileIcon('app.js', false)
      const pdfIcon = getFileIcon('document.pdf', false)

      expect(jsIcon).toBe('file-code')
      expect(pdfIcon).toBe('file-pdf')
      expect(jsIcon).not.toEqual(pdfIcon)
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
      expect(getMessageIcon('info')).toBe('info-circle')
    })

    it('should return success icon for success type', () => {
      const { getMessageIcon } = useKnowledgeIcons()
      expect(getMessageIcon('success')).toBe('check-circle')
    })

    it('should return warning icon for warning type', () => {
      const { getMessageIcon } = useKnowledgeIcons()
      expect(getMessageIcon('warning')).toBe('exclamation-triangle')
    })

    it('should return error icon for error type', () => {
      const { getMessageIcon } = useKnowledgeIcons()
      expect(getMessageIcon('error')).toBe('times-circle')
    })

    it('should default to info icon for unknown type', () => {
      const { getMessageIcon } = useKnowledgeIcons()
      expect(getMessageIcon('unknown')).toBe('info-circle')
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
