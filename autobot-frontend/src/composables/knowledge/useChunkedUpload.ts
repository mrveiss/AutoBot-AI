// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #19713: a large file goes up one chunk at a time and survives a dropped connection.
 *
 * The server's `received` is the only record of progress: after any failure the client asks it, and
 * carries on from there. The session id is kept for this browser tab, so reloading the page and
 * choosing the same file again resumes too.
 */
import { computed, ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'
import { useI18n } from 'vue-i18n'

const logger = createLogger('useChunkedUpload')

export interface UploadLimits {
  chunk_bytes: number
  document_max_bytes: number
  media_max_bytes: number
  media_extensions: string[]
}

interface UploadState {
  upload_id: string
  received: number
  total_size: number
  state: string
  expired: boolean
  error: string
  chunk_bytes: number
  result: { document_id?: string; word_count?: number }
}

export interface ChunkedUploadFields {
  target: 'document' | 'transcript'
  title?: string
  category?: string
  tags?: string[]
}

/** An answer from the server that retrying won't change; `code` is what the person is told. */
export class UploadRefused extends Error {
  constructor(readonly code: string) {
    super(code)
  }
}

const REASON_KEYS: Record<string, string> = {
  'upload.no_space': 'noSpace',
  'upload.too_large': 'tooLarge',
  'upload.busy': 'busy',
  'upload.checksum_mismatch': 'checksum',
  'upload.keeps_failing': 'keepsFailing',
  'upload.still_processing': 'stillProcessing',
}

const CHUNK_TIMEOUT_MS = 120_000
const HANDOFF_WATCH_MS = 6 * 60 * 60 * 1000
const RETRY_DELAY_MS = 2000
const MAX_RETRIES = 30
const POLL_DELAY_MS = 3000

const uploadsUrl = (): string => `${getApiBase()}/knowledge_base/uploads`
const wait = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms))

export function resumeKey(file: File): string {
  return `chunked-upload:${file.name}:${file.size}:${file.lastModified}`
}

function remembered(key: string): string | null {
  try {
    return sessionStorage.getItem(key)
  } catch {
    return null
  }
}

function remember(key: string, id: string | null): void {
  try {
    if (id) sessionStorage.setItem(key, id)
    else sessionStorage.removeItem(key)
  } catch {
    // Without storage an upload still resumes within this call; only a reload starts over.
  }
}

async function refusalFrom(response: Response): Promise<UploadRefused> {
  const body = await response.json().catch(() => ({}))
  return new UploadRefused(body.detail?.code || 'upload.refused')
}

async function sessionFor(file: File, fields: ChunkedUploadFields): Promise<UploadState> {
  const known = remembered(resumeKey(file))
  if (known) {
    try {
      const state: UploadState = await apiClient.get(`${uploadsUrl()}/${known}`)
      if (state.state === 'receiving' && !state.expired) return state
    } catch {
      // gone: start again
    }
    remember(resumeKey(file), null) // expired, failed or already done: a new session, never a dead end
  }
  const response = await apiClient.rawRequest(uploadsUrl(), {
    method: 'POST',
    body: { filename: file.name, total_size: file.size, ...fields },
  })
  if (!response.ok) throw await refusalFrom(response)
  const created: UploadState = await response.json()
  remember(resumeKey(file), created.upload_id)
  return created
}

/** Plain http has no WebCrypto; the server then relies on the chunk's length and the connection. */
async function checksumHeader(chunk: Blob): Promise<Record<string, string>> {
  if (!globalThis.crypto?.subtle) return {}
  const digest = await crypto.subtle.digest('SHA-256', await chunk.arrayBuffer())
  const hex = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('')
  return { 'X-Chunk-SHA256': hex }
}

/** Where to go next: the server's offset after a chunk is taken, or after it lost or refused one. */
async function sendChunk(id: string, file: File, offset: number, size: number, signal: AbortSignal): Promise<number> {
  const chunk = file.slice(offset, offset + size)
  const response = await apiClient.rawRequest(`${uploadsUrl()}/${id}/chunks?offset=${offset}`, {
    method: 'PUT',
    body: chunk,
    headers: { 'Content-Type': 'application/octet-stream', ...(await checksumHeader(chunk)) },
    timeout: CHUNK_TIMEOUT_MS,
    signal,
  })
  if (response.ok) return ((await response.json()) as UploadState).received
  if (response.status === 422) {
    const refusal = await refusalFrom(response)
    if (refusal.code === 'upload.chunk_checksum') return offset // changed on the way: send it again
    throw refusal
  }
  if (response.status === 409 || response.status >= 500) {
    if (response.status === 507) throw await refusalFrom(response)
    const state: UploadState = await apiClient.get(`${uploadsUrl()}/${id}`)
    return state.received
  }
  throw await refusalFrom(response)
}

async function sendAll(
  state: UploadState,
  file: File,
  onProgress: (percent: number) => void,
  signal: AbortSignal,
): Promise<void> {
  let offset = state.received
  let failures = 0
  while (offset < file.size) {
    if (signal.aborted) throw new UploadRefused('upload.cancelled')
    try {
      const next = await sendChunk(state.upload_id, file, offset, state.chunk_bytes, signal)
      failures = next > offset ? 0 : failures + 1
      offset = next
      onProgress(Math.floor((offset / file.size) * 100))
    } catch (error) {
      if (error instanceof UploadRefused) throw error
      failures += 1 // a dropped connection or a timeout: ask again, and carry on from the server's offset
    }
    if (failures > MAX_RETRIES) throw new UploadRefused('upload.keeps_failing')
    if (failures > 0) await wait(RETRY_DELAY_MS)
  }
}

async function handOver(id: string, signal: AbortSignal): Promise<UploadState> {
  await apiClient.post(`${uploadsUrl()}/${id}/complete`, {})
  const giveUpAt = Date.now() + HANDOFF_WATCH_MS
  while (Date.now() < giveUpAt && !signal.aborted) {
    const state: UploadState = await apiClient.get(`${uploadsUrl()}/${id}`)
    if (state.state === 'done') return state
    if (state.state === 'failed') throw new UploadRefused(state.error || 'upload.handoff_failed')
    await wait(POLL_DELAY_MS)
  }
  throw new UploadRefused('upload.still_processing') // it goes on running on the server; this tab stops watching
}

export function useChunkedUpload(documentAccept = '') {
  const { t } = useI18n()
  const running = new Map<string, AbortController>()
  const limits = ref<UploadLimits | null>(null)

  async function loadLimits(): Promise<void> {
    try {
      limits.value = await apiClient.get(`${uploadsUrl()}/limits`)
    } catch (error) {
      logger.warn('Could not read the resumable upload limits; the server still enforces them', error)
    }
  }

  function isMedia(name: string): boolean {
    const dot = name.lastIndexOf('.')
    return dot >= 0 && !!limits.value?.media_extensions.includes(name.slice(dot).toLowerCase())
  }

  /** The most this file may be; null until the limits have been read. */
  function maxBytesFor(name: string): number | null {
    if (!limits.value) return null
    return isMedia(name) ? limits.value.media_max_bytes : limits.value.document_max_bytes
  }

  const uploadAccept = computed(() => [documentAccept, ...(limits.value?.media_extensions ?? [])].join(','))

  async function uploadInChunks(
    file: File,
    fields: ChunkedUploadFields,
    onProgress: (percent: number) => void = () => {},
  ): Promise<UploadState> {
    const controller = new AbortController()
    running.set(resumeKey(file), controller)
    try {
      const state = await sessionFor(file, fields)
      await sendAll(state, file, onProgress, controller.signal)
      const done = await handOver(state.upload_id, controller.signal)
      remember(resumeKey(file), null)
      return done
    } catch (error) {
      if (!(error instanceof UploadRefused)) throw error
      const reason = REASON_KEYS[error.code] ?? 'failed'
      throw new Error(t(`knowledge.upload.chunked.${reason}`))
    } finally {
      running.delete(resumeKey(file))
    }
  }

  /** The person gave up on this file: stop sending, and free what was staged. */
  async function cancelUpload(file: File): Promise<void> {
    running.get(resumeKey(file))?.abort()
    const id = remembered(resumeKey(file))
    if (!id) return
    remember(resumeKey(file), null)
    await apiClient.rawRequest(`${uploadsUrl()}/${id}`, { method: 'DELETE' }).catch((error: unknown) => {
      logger.warn('Could not cancel the upload; it stays on the review list', error)
    })
  }

  return { loadLimits, uploadInChunks, cancelUpload, isMedia, uploadAccept, maxBytesFor }
}
