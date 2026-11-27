// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/** Pure helpers of the Knowledge upload screen (#747, #18244): file names, types, previews, categories. */

const PREVIEWABLE_EXTENSIONS = ['.txt', '.md', '.json', '.csv', '.yaml', '.yml', '.xml', '.html']
const VALID_DROP_TYPES = [
  'text/plain', 'text/markdown', 'text/csv', 'text/html', 'text/xml',
  'application/json', 'application/pdf', 'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/x-yaml', 'text/yaml',
]

// Category detection patterns, first match wins
const CATEGORY_PATTERNS: Record<string, RegExp[]> = {
  Documentation: [/readme/i, /doc/i, /guide/i, /manual/i, /\.md$/i],
  API: [/api/i, /swagger/i, /openapi/i, /endpoint/i],
  Configuration: [/config/i, /\.yaml$/i, /\.yml$/i, /\.json$/i, /settings/i],
  Code: [/\.py$/i, /\.js$/i, /\.ts$/i, /script/i, /function/i],
  Data: [/\.csv$/i, /data/i, /dataset/i, /export/i],
  'Web Content': [/\.html$/i, /\.xml$/i, /web/i, /page/i],
}

/** A dragged MIME type is acceptable when empty (the browser may not say) or a known document type. */
export const isValidFileType = (mimeType: string): boolean => mimeType === '' || VALID_DROP_TYPES.includes(mimeType)

export function getFileExtension(filename: string): string {
  const lastDot = filename.lastIndexOf('.')
  return lastDot >= 0 ? filename.substring(lastDot) : ''
}

export const isPreviewableFile = (filename: string): boolean =>
  PREVIEWABLE_EXTENSIONS.includes(getFileExtension(filename).toLowerCase())

export function truncateFileName(name: string, maxLength: number): string {
  if (name.length <= maxLength) return name
  const ext = getFileExtension(name)
  const baseName = name.substring(0, name.length - ext.length)
  return `${baseName.substring(0, maxLength - ext.length - 3)}...${ext}`
}

export function detectCategory(filename: string): string | null {
  for (const [category, patterns] of Object.entries(CATEGORY_PATTERNS)) {
    if (patterns.some((pattern) => pattern.test(filename))) return category
  }
  return null
}

export const generateFileId = (): string => `file-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`

export function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = () => reject(reader.error)
    reader.readAsText(file, 'utf-8')
  })
}

/** An i18n key when the visibility needs a field the form does not collect yet, else null (#685). */
export function accessLevelErrorKey(
  visibility: string,
  fields: { org_id?: string; team_ids?: string[]; shared_with?: string[] },
): string | null {
  if (visibility === 'organization' && !fields.org_id) return 'knowledge.upload.errorOrgRequired'
  if (visibility === 'group' && !fields.team_ids?.length) return 'knowledge.upload.errorTeamRequired'
  if (visibility === 'shared' && !fields.shared_with?.length) return 'knowledge.upload.errorSharedRequired'
  return null
}
