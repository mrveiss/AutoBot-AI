// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Adapt the conversation-file list response to the shape the file panel and the delete dialog read (#20195).
 *
 * The backend returns `{ files: [{ size, uploaded_at, uploaded_by, ... }], total_files, total_size }`;
 * the panel reads `size_bytes`, `upload_timestamp`, `file_type` and a `stats` block that the backend never
 * sent, so an owner who could now list their files saw rows with no size, date or type.
 */

import type { ConversationFile, FileStats } from '@/composables/useConversationFiles'

export interface BackendConversationFile {
  file_id: string
  filename: string
  original_filename?: string
  size: number
  mime_type?: string | null
  uploaded_at: string
  uploaded_by?: string | null
}

export interface BackendFileList {
  files?: BackendConversationFile[]
  total_files?: number
  total_size?: number
}

/** An agent-created file has no uploader in storage; everything a person uploaded has one. */
export function mapConversationFile(raw: BackendConversationFile, base: string): ConversationFile {
  return {
    file_id: raw.file_id,
    filename: raw.original_filename || raw.filename,
    file_type: raw.uploaded_by ? 'upload' : 'generated',
    mime_type: raw.mime_type || 'application/octet-stream',
    size_bytes: raw.size,
    upload_timestamp: raw.uploaded_at,
    download_url: `${base}/download/${raw.file_id}`,
    preview_url: `${base}/preview/${raw.file_id}`,
  }
}

export function mapFileStats(data: BackendFileList | null | undefined, files: ConversationFile[]): FileStats {
  const generated = files.filter((f) => f.file_type === 'generated').length
  return {
    total_files: data?.total_files ?? files.length,
    total_size_bytes: data?.total_size ?? files.reduce((sum, f) => sum + f.size_bytes, 0),
    uploads_count: files.length - generated,
    generated_count: generated,
  }
}

export function mapFileList(
  data: BackendFileList | null | undefined,
  base: string,
): { files: ConversationFile[]; stats: FileStats } {
  const files = (data?.files ?? []).map((f) => mapConversationFile(f, base))
  return { files, stats: mapFileStats(data, files) }
}
