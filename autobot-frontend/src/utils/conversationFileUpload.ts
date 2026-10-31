// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * The chat attachment upload transport (#20133).
 *
 * The route (`/conversation-files/conversation/{id}/upload`) is gated by `check_admin_permission`,
 * which accepts a bearer JWT, `X-Session-ID`, a dev header or an internal key, and no cookie, so the
 * request carries the stored bearer, read through the canonical reader `readStoredAuthToken`.
 * It stays a raw XHR rather than `ApiClient.uploadFile` because the chat UI needs the byte-level
 * progress (for ETA), the response's `file_info`/`upload_id`, and an exact `200` success check,
 * none of which the kit method exposes.
 */
import { getApiBase } from '@/config/ssot-config'
import type { components } from '@/types/generated/api'
import { readStoredAuthToken } from '@/utils/authToken'

export type ConversationUploadResponse = components['schemas']['FileUploadResponse']

/** POST `file` to the conversation's upload route; rejects on a non-200, a bad body, a network error or an abort. */
export function postConversationUpload(
  sessionId: string,
  file: File,
  onProgress: (loaded: number, total: number) => void
): Promise<ConversationUploadResponse> {
  const formData = new FormData()
  formData.append('file', file)
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable) onProgress(event.loaded, event.total)
    })
    xhr.addEventListener('load', () => {
      if (xhr.status !== 200) return reject(new Error(`Upload failed with status: ${xhr.status}`))
      try {
        resolve(JSON.parse(xhr.responseText) as ConversationUploadResponse)
      } catch {
        reject(new Error('Invalid response from server'))
      }
    })
    xhr.addEventListener('error', () => reject(new Error('Network error during upload')))
    xhr.addEventListener('abort', () => reject(new Error('Upload cancelled')))
    xhr.open('POST', `${getApiBase()}/conversation-files/conversation/${sessionId}/upload`)
    const token = readStoredAuthToken()
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    xhr.send(formData)
  })
}
