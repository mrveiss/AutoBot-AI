// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * The chat attachment upload transport (#20133).
 *
 * The route (`/conversation-files/conversation/{id}/upload`) admits an admin or the user who owns the
 * conversation (#20133); it resolves a bearer JWT, `X-Session-ID`, a dev header or an internal key, and
 * no cookie, so the request carries the stored bearer, read through the canonical reader `readStoredAuthToken`.
 * It stays a raw XHR rather than `ApiClient.uploadFile` because the chat UI needs the byte-level
 * progress (for ETA), the response's `file_info`/`upload_id`, and an exact `200` success check,
 * none of which the kit method exposes.
 */
import { getApiBase } from '@/config/ssot-config'
import type { components } from '@/types/generated/api'
import { readStoredAuthToken } from '@/utils/authToken'

export type ConversationUploadResponse = components['schemas']['FileUploadResponse']

export type UploadErrorCode =
  | 'http'
  | 'invalid_response'
  | 'network'
  | 'cancelled'
  | 'file_too_large'
  | 'quota_exceeded'

/**
 * The figures the server attaches to a 413 (`detail`, `conversation_file_quota.py`, #20217). `detail.code`
 * is stable; the server's English `message` is never shown. Bytes are what the server measured.
 */
export interface UploadRefusal {
  max_bytes?: number
  limit_bytes?: number
  live_bytes?: number
  pending_removal_bytes?: number
  remaining_bytes?: number
}

const SERVER_REFUSALS: Record<string, UploadErrorCode> = {
  conversation_file_too_large: 'file_too_large',
  conversation_file_quota_exceeded: 'quota_exceeded',
}

/**
 * Why a chat attachment upload failed. `message` is a diagnostic for logs, never UI text:
 * the chat shows `describeUploadError(error, t)` so the wording is translated.
 */
export class ConversationUploadError extends Error {
  constructor(
    readonly code: UploadErrorCode,
    readonly status?: number,
    readonly refusal?: UploadRefusal
  ) {
    super(`conversation upload failed: ${code}${status === undefined ? '' : ` (${status})`}`)
    this.name = 'ConversationUploadError'
  }
}

type Translate = (key: string, params?: Record<string, unknown>) => string

const UPLOAD_ERROR_KEYS: Record<UploadErrorCode, string> = {
  http: 'chat.input.uploadError.http',
  invalid_response: 'chat.input.uploadError.invalidResponse',
  network: 'chat.input.uploadError.network',
  cancelled: 'chat.input.uploadError.cancelled',
  file_too_large: 'chat.input.uploadError.fileTooLarge',
  quota_exceeded: 'chat.input.uploadError.quotaExceeded',
}

const BYTES_PER_MB = 1024 * 1024
const toMb = (bytes = 0) => Math.ceil(bytes / BYTES_PER_MB)

/** Translation parameters for a server refusal; used space rounds up and space left rounds down, so neither is overstated. */
function refusalParams(refusal: UploadRefusal = {}): Record<string, unknown> {
  return {
    maxMb: toMb(refusal.max_bytes),
    limitMb: toMb(refusal.limit_bytes),
    liveMb: toMb(refusal.live_bytes),
    pendingMb: toMb(refusal.pending_removal_bytes),
    remainingMb: Math.floor((refusal.remaining_bytes ?? 0) / BYTES_PER_MB),
  }
}

/** The translated text the chat shows for a rejected upload; any other rejection gets the generic key. */
export function describeUploadError(error: unknown, t: Translate): string {
  if (!(error instanceof ConversationUploadError)) return t('chat.input.uploadError.unknown')
  if (error.code === 'http') return t(UPLOAD_ERROR_KEYS.http, { status: error.status })
  if (error.code === 'quota_exceeded' && (error.refusal?.pending_removal_bytes ?? 0) > 0) {
    return t('chat.input.uploadError.quotaExceededPendingRemoval', refusalParams(error.refusal))
  }
  if (error.code === 'file_too_large' || error.code === 'quota_exceeded') {
    return t(UPLOAD_ERROR_KEYS[error.code], refusalParams(error.refusal))
  }
  return t(UPLOAD_ERROR_KEYS[error.code])
}

/** The typed rejection for a non-200: a recognised server reason (`detail.code` on a 413), else a plain http one. */
function rejectionFor(status: number, responseText: string): ConversationUploadError {
  try {
    const detail = JSON.parse(responseText)?.detail
    const code = status === 413 && detail ? SERVER_REFUSALS[detail.code] : undefined
    if (code) return new ConversationUploadError(code, status, detail as UploadRefusal)
  } catch {
    // an unreadable error body is still an http failure
  }
  return new ConversationUploadError('http', status)
}

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
      if (xhr.status !== 200) return reject(rejectionFor(xhr.status, xhr.responseText))
      try {
        resolve(JSON.parse(xhr.responseText) as ConversationUploadResponse)
      } catch {
        reject(new ConversationUploadError('invalid_response'))
      }
    })
    xhr.addEventListener('error', () => reject(new ConversationUploadError('network')))
    xhr.addEventListener('abort', () => reject(new ConversationUploadError('cancelled')))
    xhr.open('POST', `${getApiBase()}/conversation-files/conversation/${sessionId}/upload`)
    const token = readStoredAuthToken()
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    xhr.send(formData)
  })
}

let sessionBeingCreated: Promise<string> | null = null

/**
 * The conversation a chat attachment uploads into, creating one first when the chat has none.
 *
 * A chat with no current session only gets one when its first message is sent, but the upload route
 * answers 404 for a conversation that does not exist (a non-admin names one they own, #20133), so the
 * attachment cannot ride a made-up id such as `default`. Files picked together share one creation.
 */
export function ensureUploadSession(
  store: { currentSessionId: string | null },
  controller: { createNewSession: () => Promise<string> },
): Promise<string> {
  if (store.currentSessionId) return Promise.resolve(store.currentSessionId)
  sessionBeingCreated ??= controller.createNewSession().finally(() => {
    sessionBeingCreated = null
  })
  return sessionBeingCreated
}
