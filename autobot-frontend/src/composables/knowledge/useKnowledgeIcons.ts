// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useKnowledgeIcons Composable
 *
 * UI helpers for knowledge base components: type/file/OS/message icons
 * and a small time formatter. Split from useKnowledgeBase (#5122) so the
 * domain composables stay API-focused.
 */

import { getFileIcon as getFileIconUtil } from '@/utils/iconMappings'
import { getCategoryIcon } from './useKnowledgeCategories'

export function useKnowledgeIcons() {
  /**
   * Get icon for document type.
   */
  const getTypeIcon = (type: string): string => {
    const typeLower = type.toLowerCase()

    if (typeLower.includes('pdf')) return 'fas fa-file-pdf'
    if (typeLower.includes('word') || typeLower.includes('doc')) return 'fas fa-file-word'
    if (typeLower.includes('excel') || typeLower.includes('xls')) return 'fas fa-file-excel'
    if (typeLower.includes('image') || typeLower.includes('png') || typeLower.includes('jpg')) return 'fas fa-file-image'
    if (typeLower.includes('video')) return 'fas fa-file-video'
    if (typeLower.includes('audio')) return 'fas fa-file-audio'
    if (typeLower.includes('json') || typeLower.includes('code')) return 'fas fa-file-code'
    if (typeLower.includes('csv')) return 'fas fa-file-csv'
    if (typeLower.includes('text') || typeLower.includes('txt')) return 'fas fa-file-alt'
    if (typeLower.includes('markdown') || typeLower.includes('md')) return 'fas fa-file-alt'

    return 'fas fa-file'
  }

  /**
   * Get icon for file based on name and type.
   * Icon mapping centralized in @/utils/iconMappings; colors added here
   * for visual distinction in the knowledge base UI.
   */
  const getFileIcon = (name: string, isDir: boolean = false): string => {
    if (isDir) {
      return 'fas fa-folder'
    }

    const icon = getFileIconUtil(name, false)
    const extension = name.split('.').pop()?.toLowerCase() || ''

    const colorMap: Record<string, string> = {
      // Code files — blue/green
      js: 'text-blue-500',
      ts: 'text-blue-500',
      jsx: 'text-blue-500',
      tsx: 'text-blue-500',
      vue: 'text-blue-500',
      py: 'text-green-500',
      rb: 'text-green-500',
      go: 'text-green-500',
      java: 'text-green-500',
      c: 'text-green-500',
      cpp: 'text-green-500',
      h: 'text-green-500',
      // Data files — orange
      json: 'text-orange-500',
      yaml: 'text-orange-500',
      yml: 'text-orange-500',
      toml: 'text-orange-500',
      // Documents — varied
      md: 'text-gray-600',
      txt: 'text-gray-600',
      pdf: 'text-red-600',
      doc: 'text-blue-600',
      docx: 'text-blue-600',
      xls: 'text-green-600',
      xlsx: 'text-green-600',
      csv: 'text-green-600',
      // Images — purple
      png: 'text-purple-500',
      jpg: 'text-purple-500',
      jpeg: 'text-purple-500',
      gif: 'text-purple-500',
      svg: 'text-purple-500',
      webp: 'text-purple-500',
      // Archives — yellow
      zip: 'text-yellow-600',
      tar: 'text-yellow-600',
      gz: 'text-yellow-600',
      rar: 'text-yellow-600',
      '7z': 'text-yellow-600',
    }

    const color = colorMap[extension] || 'text-gray-600'
    return `${icon} ${color}`
  }

  const getOSBadgeClass = (osType: string): string => {
    switch (osType) {
      case 'linux': return 'badge-success'
      case 'windows': return 'badge-info'
      case 'macos': return 'badge-warning'
      default: return 'badge-secondary'
    }
  }

  const getMessageIcon = (type: string): string => {
    const icons: Record<string, string> = {
      info: 'fas fa-info-circle text-blue-500',
      success: 'fas fa-check-circle text-green-500',
      warning: 'fas fa-exclamation-triangle text-yellow-500',
      error: 'fas fa-times-circle text-red-500',
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
