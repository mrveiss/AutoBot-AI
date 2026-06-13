// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Centralized Icon and Status Mappings
 *
 * This utility provides consistent icon mappings across the application,
 * reducing duplication and ensuring UI consistency.
 */

import { createLogger } from '@/utils/debugUtils'
import { ICONS } from '@/components/ui/Icon.vue'
import type { IconName } from '@/components/ui/Icon.vue'

// ============================================================================
// STATUS ICONS
// ============================================================================

export const statusIcons: Record<string, IconName> = {
  // Health/Status States
  healthy: 'check-circle',
  success: 'check-circle',
  online: 'check-circle',
  active: 'circle',

  warning: 'exclamation-triangle',
  degraded: 'exclamation-triangle',
  pending: 'clock',

  error: 'times-circle',
  unhealthy: 'times-circle',
  failed: 'times-circle',
  offline: 'times-circle',
  disconnected: 'plug',

  unknown: 'question-circle',
  // Note: loading spin is handled at the call site via :spin="true" on <Icon>
  loading: 'sync-alt',
}

// ============================================================================
// FILE TYPE ICONS
// ============================================================================

// Note: file-type icons use Font Awesome class strings because many icons
// (file-pdf, file-word, fab fa-*, etc.) have no SVG equivalent in Icon.vue.
// Callers use <i :class="getFileIcon(...)"> and are outside the SVG migration scope.
export const fileTypeIcons = {
  // Documents
  pdf: 'fas fa-file-pdf',
  doc: 'fas fa-file-word',
  docx: 'fas fa-file-word',
  txt: 'fas fa-file-alt',
  md: 'fas fa-file-alt',
  xls: 'fas fa-file-excel',
  xlsx: 'fas fa-file-excel',
  csv: 'fas fa-file-csv',

  // Code Files
  js: 'fab fa-js-square',
  ts: 'fab fa-js-square',
  jsx: 'fab fa-js-square',
  tsx: 'fab fa-js-square',
  vue: 'fab fa-vuejs',
  py: 'fab fa-python',
  rb: 'fas fa-file-code',
  go: 'fas fa-file-code',
  java: 'fas fa-file-code',
  c: 'fas fa-file-code',
  cpp: 'fas fa-file-code',
  h: 'fas fa-file-code',
  html: 'fab fa-html5',
  css: 'fab fa-css3',
  json: 'fas fa-code',
  yaml: 'fas fa-code',
  yml: 'fas fa-code',
  toml: 'fas fa-code',

  // Images
  png: 'fas fa-file-image',
  jpg: 'fas fa-file-image',
  jpeg: 'fas fa-file-image',
  gif: 'fas fa-file-image',
  svg: 'fas fa-file-image',
  webp: 'fas fa-file-image',

  // Archives
  zip: 'fas fa-file-archive',
  tar: 'fas fa-file-archive',
  gz: 'fas fa-file-archive',
  rar: 'fas fa-file-archive',
  '7z': 'fas fa-file-archive',

  // Media - Video
  mp4: 'fas fa-file-video',
  avi: 'fas fa-file-video',
  mov: 'fas fa-file-video',
  webm: 'fas fa-file-video',

  // Media - Audio
  mp3: 'fas fa-file-audio',
  wav: 'fas fa-file-audio',
  ogg: 'fas fa-file-audio',

  // Other
  folder: 'fas fa-folder',
  folderOpen: 'fas fa-folder-open',
  file: 'fas fa-file'
} as const

// ============================================================================
// DOCUMENT TYPE ICONS (for knowledge base entries)
// ============================================================================

// Note: these use Font Awesome class strings — callers use <i :class="...">
export const documentTypeIcons = {
  document: 'fas fa-file-alt',
  webpage: 'fas fa-globe',
  api: 'fas fa-code',
  upload: 'fas fa-upload',
  file: 'fas fa-file'
} as const

// ============================================================================
// PLATFORM ICONS
// ============================================================================

// Note: brand icons (fab fa-*) have no SVG equivalent in Icon.vue
export const platformIcons = {
  linux: 'fab fa-linux',
  windows: 'fab fa-windows',
  macos: 'fab fa-apple',
  docker: 'fab fa-docker',
  unknown: 'fas fa-server'
} as const

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

// #6796: telemetry — log (with stack trace) the first time getFileIcon
// receives a non-string `filename`, so the upstream serialization bug can
// be found from a real session. We only warn once per page load to avoid
// drowning the logger.
const _logger = createLogger('iconMappings')
let _nonStringFilenameWarned = false
function _warnNonStringFilenameOnce(value: unknown): void {
  if (_nonStringFilenameWarned) return
  _nonStringFilenameWarned = true
  _logger.warn(
    '[#6796] getFileIcon received non-string filename — ' +
      'upstream payload (likely TreeNode.name) is not a string. ' +
      `typeof=${typeof value} value=${String(value).slice(0, 80)}`,
    new Error('iconMappings non-string trace'),
  )
}

/**
 * Get icon for file based on extension
 */
export function getFileIcon(filename: string, isFolder: boolean = false): string {
  if (isFolder) return fileTypeIcons.folder
  // #6645: defensive type check — TS types don't survive the JSON network
  // boundary, and TreeNode.name occasionally arrives as null/number/undefined,
  // which crashed KnowledgeBrowser with "t.split is not a function".
  if (typeof filename !== 'string' || filename.length === 0) {
    if (typeof filename !== 'string') _warnNonStringFilenameOnce(filename)
    return fileTypeIcons.file
  }

  const ext = filename.split('.').pop()?.toLowerCase()
  if (!ext) return fileTypeIcons.file

  return fileTypeIcons[ext as keyof typeof fileTypeIcons] || fileTypeIcons.file
}

// ============================================================================
// SVG ICON-NAME VARIANTS (#9724)
// ============================================================================
// IconName-returning equivalents of the Font Awesome helpers above, for
// callers that render through <Icon :name="...">. Passing an FA class string
// to <Icon> silently renders an empty SVG, so Icon consumers MUST use these.

const fileExtensionIconNames: Record<string, IconName> = {
  pdf: 'file-pdf',
  doc: 'file-word',
  docx: 'file-word',
  txt: 'file-alt',
  md: 'file-alt',
  xls: 'file-excel',
  xlsx: 'file-excel',
  csv: 'file-csv',
  js: 'file-code',
  ts: 'file-code',
  jsx: 'file-code',
  tsx: 'file-code',
  vue: 'file-code',
  py: 'file-code',
  rb: 'file-code',
  go: 'file-code',
  java: 'file-code',
  c: 'file-code',
  cpp: 'file-code',
  h: 'file-code',
  html: 'file-code',
  css: 'file-code',
  json: 'file-code',
  yaml: 'file-code',
  yml: 'file-code',
  toml: 'file-code',
  png: 'file-image',
  jpg: 'file-image',
  jpeg: 'file-image',
  gif: 'file-image',
  svg: 'file-image',
  webp: 'file-image',
  zip: 'file-archive',
  tar: 'file-archive',
  gz: 'file-archive',
  rar: 'file-archive',
  '7z': 'file-archive',
  mp4: 'file-video',
  avi: 'file-video',
  mov: 'file-video',
  webm: 'file-video',
  mp3: 'file-audio',
  wav: 'file-audio',
  ogg: 'file-audio',
}

/**
 * Get an <Icon> name for a file based on its extension.
 */
export function getFileIconName(filename: string, isFolder: boolean = false): IconName {
  if (isFolder) return 'folder'
  if (typeof filename !== 'string' || filename.length === 0) {
    if (typeof filename !== 'string') _warnNonStringFilenameOnce(filename)
    return 'file'
  }
  const ext = filename.split('.').pop()?.toLowerCase()
  if (!ext) return 'file'
  return fileExtensionIconNames[ext] ?? 'file'
}

/**
 * Get an <Icon> name for a file based on its MIME type.
 */
export function getFileIconNameByMimeType(mimeType: string): IconName {
  if (typeof mimeType !== 'string' || mimeType.length === 0) return 'file'
  const type = mimeType.toLowerCase()
  if (type.startsWith('image/')) return 'image'
  if (type.startsWith('video/')) return 'video'
  if (type.startsWith('audio/')) return 'music'
  if (type.includes('pdf')) return 'file-pdf'
  if (type.includes('word') || type.includes('msword') || type.includes('document')) return 'file-word'
  if (type.includes('excel') || type.includes('spreadsheet')) return 'file-excel'
  if (type.includes('zip') || type.includes('compressed') || type.includes('archive')) return 'file-archive'
  if (type.includes('json')) return 'file-code'
  if (type.includes('text')) return 'file-alt'
  return 'file'
}

/**
 * Validate a dynamic (e.g. backend-provided) icon name at runtime.
 * Returns the name when it exists in the ICONS registry, else the fallback.
 */
export function asIconName(name: string | undefined | null, fallback: IconName): IconName {
  return name && name in ICONS ? (name as IconName) : fallback
}

const documentTypeIconNames: Record<string, IconName> = {
  document: 'file-alt',
  webpage: 'globe',
  api: 'code',
  upload: 'upload',
  file: 'file',
}

/**
 * Get an <Icon> name for a knowledge-base document type.
 */
export function getDocumentTypeIconName(type: string): IconName {
  const normalizedType = typeof type === 'string' ? type.toLowerCase() : ''
  return documentTypeIconNames[normalizedType] ?? 'file'
}

/**
 * Get icon for status — returns an IconName for use with <Icon :name="...">
 */
export function getStatusIcon(status: string): IconName {
  const normalizedStatus = status.toLowerCase()
  return statusIcons[normalizedStatus] || statusIcons['unknown']
}

/**
 * Get icon for platform
 */
export function getPlatformIcon(platform: string): string {
  const normalizedPlatform = platform.toLowerCase()
  return platformIcons[normalizedPlatform as keyof typeof platformIcons] || platformIcons.unknown
}

/**
 * Get icon for document type (knowledge base)
 */
export function getDocumentTypeIcon(type: string): string {
  const normalizedType = type.toLowerCase()
  return documentTypeIcons[normalizedType as keyof typeof documentTypeIcons] || documentTypeIcons.file
}

/**
 * Get icon for file based on MIME type
 * Useful for uploaded files where MIME type is available
 */
export function getFileIconByMimeType(mimeType: string): string {
  // #6645: same defensive check as getFileIcon — non-string inputs from the
  // network boundary should not crash the page.
  if (typeof mimeType !== 'string' || mimeType.length === 0) {
    return 'fas fa-file'
  }
  const type = mimeType.toLowerCase()

  // Images
  if (type.startsWith('image/')) return 'fas fa-image'

  // Video
  if (type.startsWith('video/')) return 'fas fa-video'

  // Audio
  if (type.startsWith('audio/')) return 'fas fa-music'

  // Documents
  if (type.includes('pdf')) return 'fas fa-file-pdf'
  if (type.includes('word') || type.includes('msword')) return 'fas fa-file-word'
  if (type.includes('excel') || type.includes('spreadsheet')) return 'fas fa-file-excel'
  if (type.includes('text')) return 'fas fa-file-alt'

  // Archives
  if (type.includes('zip') || type.includes('compressed')) return 'fas fa-file-archive'

  // Default
  return 'fas fa-file'
}

/**
 * Get status color class (Tailwind CSS)
 */
export function getStatusColorClass(status: string): string {
  const normalizedStatus = status.toLowerCase()

  const colorMap: Record<string, string> = {
    healthy: 'text-green-600',
    success: 'text-green-600',
    online: 'text-green-600',

    warning: 'text-yellow-600',
    degraded: 'text-yellow-600',
    pending: 'text-yellow-600',

    error: 'text-red-600',
    unhealthy: 'text-red-600',
    failed: 'text-red-600',
    offline: 'text-red-600',

    unknown: 'text-gray-400',
    loading: 'text-blue-600'
  }

  return colorMap[normalizedStatus] || 'text-gray-400'
}

/**
 * Get status icon name with color class (combined for backward compatibility)
 * Returns "<iconName> <colorClass>" — note: icon is now an IconName, not an FA class string.
 * @deprecated Use getStatusIcon() + getStatusColorClass() separately for better flexibility
 */
export function getStatusIconWithColor(status: string): string {
  const icon = getStatusIcon(status)
  const color = getStatusColorClass(status)
  return `${icon} ${color}`
}

/**
 * Normalize a backend health status string to a frontend display status.
 *
 * Backend health endpoint returns: 'healthy', 'unhealthy', 'degraded'.
 * Frontend display layer uses: 'healthy', 'warning', 'error'.
 * Legacy/VM values ('online', 'offline') are also handled.
 *
 * Issue #2076: Centralised mapping for all service status consumers.
 */
export function normalizeServiceStatus(
  backendStatus: string,
): 'healthy' | 'warning' | 'error' {
  const normalized = backendStatus.toLowerCase()
  switch (normalized) {
    case 'healthy':
    case 'online':
    case 'up':
    case 'running':
    case 'available':
    case 'connected':
      return 'healthy'
    case 'degraded':
    case 'warning':
    case 'pending':
      return 'warning'
    case 'unhealthy':
    case 'error':
    case 'offline':
    case 'down':
    case 'unavailable':
    case 'not_configured':
    case 'not_initialized':
    case 'import_error':
      return 'error'
    default:
      return 'error'
  }
}

export type StatusType = keyof typeof statusIcons
export type FileType = keyof typeof fileTypeIcons
export type DocumentType = keyof typeof documentTypeIcons
export type PlatformType = keyof typeof platformIcons
