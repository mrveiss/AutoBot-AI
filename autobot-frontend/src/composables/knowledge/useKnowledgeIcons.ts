// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useKnowledgeIcons Composable
 *
 * UI helpers for knowledge base components: type/file/OS/message icons
 * and a small time formatter. Split from useKnowledgeBase (#5122) so the
 * domain composables stay API-focused.
 */

import { getFileIconName } from '@/utils/iconMappings'
import type { IconName } from '@/components/ui/Icon.vue'
import { getCategoryIcon } from './useKnowledgeCategories'

export function useKnowledgeIcons() {
  /**
   * Get icon for document type.
   */
  // #9724: consumers render via <Icon :name="...">, which requires an SVG
  // IconName — the previous Font Awesome class strings rendered empty SVGs.
  const getTypeIcon = (type: string): IconName => {
    const typeLower = type.toLowerCase()

    if (typeLower.includes('pdf')) return 'file-pdf'
    if (typeLower.includes('word') || typeLower.includes('doc')) return 'file-word'
    if (typeLower.includes('excel') || typeLower.includes('xls')) return 'file-excel'
    if (typeLower.includes('image') || typeLower.includes('png') || typeLower.includes('jpg')) return 'file-image'
    if (typeLower.includes('video')) return 'file-video'
    if (typeLower.includes('audio')) return 'file-audio'
    if (typeLower.includes('json') || typeLower.includes('code')) return 'file-code'
    if (typeLower.includes('csv')) return 'file-csv'
    if (typeLower.includes('text') || typeLower.includes('txt')) return 'file-alt'
    if (typeLower.includes('markdown') || typeLower.includes('md')) return 'file-alt'

    return 'file'
  }

  /**
   * Get icon for file based on name and type.
   * Icon mapping centralized in @/utils/iconMappings; colors added here
   * for visual distinction in the knowledge base UI.
   */
  const getFileIcon = (name: string, isDir: boolean = false): IconName => {
    return getFileIconName(name, isDir)
  }

  const getOSBadgeClass = (osType: string): string => {
    switch (osType) {
      case 'linux': return 'badge-success'
      case 'windows': return 'badge-info'
      case 'macos': return 'badge-warning'
      default: return 'badge-secondary'
    }
  }

  const getMessageIcon = (type: string): IconName => {
    const icons: Record<string, IconName> = {
      info: 'info-circle',
      success: 'check-circle',
      warning: 'exclamation-triangle',
      error: 'times-circle',
    }
    return icons[type] || icons.info
  }

  const formatTime = (timestamp: string | Date): string => {
    const date = new Date(timestamp)
    return date.toLocaleTimeString()
  }

  return {
    getCategoryIcon,
    getTypeIcon,
    getFileIcon,
    getOSBadgeClass,
    getMessageIcon,
    formatTime,
  }
}
