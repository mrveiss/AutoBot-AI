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

async function sessionFor(file: File, fields: ChunkedUploadFields): Promise<UploadState> {
  const known = remembered(resumeKey(file))
  if (known) {
    try {
      return await apiClient.get(`${uploadsUrl()}/${known}`)
    } catch {
      remember(resumeKey(file), null) // gone, or expired away: start again
    }
  }
  const created: UploadState = await apiClient.post(uploadsUrl(), {
    filename: file.name,
    total_size: file.size,
    ...fields,
  })
  remember(resumeKey(file), created.upload_id)
  return created
}

/** Where to go next: the server's offset after a chunk is taken, or after it refused or lost one. */
async function sendChunk(id: string, file: File, offset: number, size: number): Promise<number> {
  const response = await apiClient.rawRequest(`${uploadsUrl()}/${id}/chunks?offset=${offset}`, {
    method: 'PUT',
    body: file.slice(offset, offset + size),
    headers: { 'Content-Type': 'application/octet-stream' },
  })
  if (response.ok) return ((await response.json()) as UploadState).received
  if (response.status === 409 || response.status >= 500) {
    const state: UploadState = await apiClient.get(`${uploadsUrl()}/${id}`)
    return state.received
  }
  const body = await response.json().catch(() => ({}))
  throw new Error(body.detail || `Upload refused (${response.status})`)
}

async function sendAll(state: UploadState, file: File, onProgress: (percent: number) => void): Promise<void> {
  let offset = state.received
  let failures = 0
  while (offset < file.size) {
    try {
      const next = await sendChunk(state.upload_id, file, offset, state.chunk_bytes)
      failures = next > offset ? 0 : failures + 1
      offset = next
      onProgress(Math.floor((offset / file.size) * 100))
    } catch (error) {
      if (!(error instanceof TypeError)) throw error // a network failure is a TypeError; the rest are answers
      failures += 1
    }
    if (failures > MAX_RETRIES) throw new Error('The upload keeps failing; try again to resume it')
    if (failures > 0) await wait(RETRY_DELAY_MS)
  }
}

async function handOver(id: string): Promise<UploadState> {
  await apiClient.post(`${uploadsUrl()}/${id}/complete`, {})
  for (;;) {
    const state: UploadState = await apiClient.get(`${uploadsUrl()}/${id}`)
    if (state.state === 'done') return state
    if (state.state === 'failed') throw new Error(state.error || 'The file could not be processed')
    await wait(POLL_DELAY_MS)
  }
}

export function useChunkedUpload(documentAccept = '') {
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
    const state = await sessionFor(file, fields)
    await sendAll(state, file, onProgress)
    const done = await handOver(state.upload_id)
    remember(resumeKey(file), null)
    return done
  }

  return { loadLimits, uploadInChunks, isMedia, uploadAccept, maxBytesFor }
}
