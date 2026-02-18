/**
 * Centralized Icon and Status Mappings
 *
 * This utility provides consistent icon mappings across the application,
 * reducing duplication and ensuring UI consistency.
 */

// ============================================================================
// STATUS ICONS
// ============================================================================

export const statusIcons = {
  // Health/Status States
  healthy: 'fas fa-check-circle',
  success: 'fas fa-check-circle',
  online: 'fas fa-check-circle',
  active: 'fas fa-circle',

  warning: 'fas fa-exclamation-triangle',
  pending: 'fas fa-clock',

  error: 'fas fa-times-circle',
  failed: 'fas fa-times-circle',
  offline: 'fas fa-times-circle',
  disconnected: 'fas fa-plug',

  unknown: 'fas fa-question-circle',
  loading: 'fas fa-spinner fa-spin'
} as const

// ============================================================================
// FILE TYPE ICONS
// ============================================================================

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

/**
 * Get icon for file based on extension
 */
export function getFileIcon(filename: string, isFolder: boolean = false): string {
  if (isFolder) return fileTypeIcons.folder

  const ext = filename.split('.').pop()?.toLowerCase()
  if (!ext) return fileTypeIcons.file

  return fileTypeIcons[ext as keyof typeof fileTypeIcons] || fileTypeIcons.file
}

/**
 * Get icon for status
 */
export function getStatusIcon(status: string): string {
  const normalizedStatus = status.toLowerCase()
  return statusIcons[normalizedStatus as keyof typeof statusIcons] || statusIcons.unknown
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
    pending: 'text-yellow-600',

    error: 'text-red-600',
    failed: 'text-red-600',
    offline: 'text-red-600',

    unknown: 'text-gray-400',
    loading: 'text-blue-600'
  }

  return colorMap[normalizedStatus] || 'text-gray-400'
}

/**
 * Get status icon with color class (combined for backward compatibility)
 * @deprecated Use getStatusIcon() + getStatusColorClass() separately for better flexibility
 */
export function getStatusIconWithColor(status: string): string {
  const icon = getStatusIcon(status)
  const color = getStatusColorClass(status)
  return `${icon} ${color}`
}

export type StatusType = keyof typeof statusIcons
export type FileType = keyof typeof fileTypeIcons
export type DocumentType = keyof typeof documentTypeIcons
export type PlatformType = keyof typeof platformIcons
