// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest'
import { mapFileList } from '../conversationFileList'

const BASE = '/api/conversation-files/conversation/s1'

describe('mapFileList (#20195)', () => {
  it('maps the backend list to the shape the file panel reads', () => {
    const { files, stats } = mapFileList(
      {
        files: [
          { file_id: 'f1', filename: 'a.txt', original_filename: 'My A.txt', size: 5, mime_type: 'text/plain', uploaded_at: '2026-10-31T10:00:00Z', uploaded_by: 'alice' },
          { file_id: 'f2', filename: 'b.md', size: 7, mime_type: null, uploaded_at: '2026-10-31T11:00:00Z', uploaded_by: null },
        ],
        total_files: 2,
        total_size: 12,
      },
      BASE,
    )
    expect(files[0]).toEqual({
      file_id: 'f1',
      filename: 'My A.txt',
      file_type: 'upload',
      mime_type: 'text/plain',
      size_bytes: 5,
      upload_timestamp: '2026-10-31T10:00:00Z',
      download_url: `${BASE}/download/f1`,
      preview_url: `${BASE}/preview/f1`,
    })
    expect(files[1].file_type).toBe('generated')
    expect(files[1].mime_type).toBe('application/octet-stream')
    expect(stats).toEqual({ total_files: 2, total_size_bytes: 12, uploads_count: 1, generated_count: 1 })
  })

  it('an empty or missing list is zero stats, not a throw', () => {
    expect(mapFileList(undefined, BASE)).toEqual({
      files: [],
      stats: { total_files: 0, total_size_bytes: 0, uploads_count: 0, generated_count: 0 },
    })
  })
})
