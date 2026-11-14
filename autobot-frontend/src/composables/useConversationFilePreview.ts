// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Preview behaviour for conversation files (#20906, #21159): the server-built text pane, with the bytes
 * (authenticated blob tab or download) as the fallback. The pane state is owned by the latest request.
 */
import { ref, type Ref } from 'vue'
import type { ConversationFilePreview } from '@/utils/conversationFilePreview'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'
import { useLatestRequest } from './useLatestRequest'

const logger = createLogger('useConversationFilePreview')

/** The preview pane's content; `truncated` when the server sent only the head of a larger file (#20906). */
export interface PreviewPane {
  fileId: string
  filename: string
  data: ConversationFilePreview
  truncated: boolean
}

/** How long a preview tab's blob URL stays valid before it is revoked (#20195). */
export const PREVIEW_BLOB_REVOKE_MS = 60_000

/**
 * The type a preview blob is opened as, or null when it must not be opened in this origin (#20195).
 * A blob URL inherits the app's origin, so text-like uploads (HTML, XML, scripts) are shown as plain text and
 * SVG, which can carry script, is downloaded instead.
 */
export function previewBlobType(mimeType: string): string | null {
  const type = (mimeType || '').toLowerCase()
  if (type.startsWith('image/svg')) return null
  if (type.startsWith('text/') || type === 'application/json') return 'text/plain'
  return type || null
}

const PREVIEWABLE_TYPES = ['image/', 'text/', 'application/pdf', 'application/json', 'video/', 'audio/']

export const isPreviewable = (mimeType: string): boolean =>
  PREVIEWABLE_TYPES.some(type => mimeType.startsWith(type))

/** The slice of the file composable the preview needs. */
export interface PreviewFile {
  file_id: string
  filename: string
  mime_type: string
  size_bytes: number
}

export interface PreviewDeps {
  api: {
    get: <T>(url: string) => Promise<T>
    rawRequest: (url: string, init: { method: string }) => Promise<Response>
  }
  currentSessionId: () => string
  files: Ref<PreviewFile[]>
  error: Ref<string | null>
  tr: (key: string) => string
  failureText: (err: unknown, fallback: string) => string
  downloadFile: (fileId: string, filename?: string) => Promise<void>
}

/**
 * Open a file in a new tab through the authenticated client, then revoke the blob URL (#20195).
 * The tab is opened synchronously (a popup after an await is blocked), then pointed at the blob unless the
 * request was superseded or closed meanwhile, in which case the tab is closed instead (#21337).
 */
async function openAuthenticatedPreview(deps: PreviewDeps, fileId: string, shownType: string, isCurrent: () => boolean): Promise<void> {
  const tab = window.open('', '_blank')
  try {
    const response = await deps.api.rawRequest(`${getApiBase()}/conversation-files/conversation/${deps.currentSessionId()}/download/${fileId}`, { method: 'GET' })
    const blob = new Blob([await response.blob()], { type: shownType })
    if (!isCurrent()) {
      tab?.close()
      return
    }
    const url = window.URL.createObjectURL(blob)
    if (tab) tab.location.href = url
    setTimeout(() => window.URL.revokeObjectURL(url), PREVIEW_BLOB_REVOKE_MS)
  } catch (err) {
    tab?.close()
    throw err
  }
}

/** Open the bytes: previewable types as a blob URL (bearer-authenticated, #20195); anything else is downloaded. */
async function openBytesPreview(deps: PreviewDeps, file: PreviewFile, isCurrent: () => boolean): Promise<void> {
  const shownType = previewBlobType(file.mime_type)
  if (shownType && isPreviewable(file.mime_type)) {
    await openAuthenticatedPreview(deps, file.file_id, shownType, isCurrent)
  } else {
    await deps.downloadFile(file.file_id, file.filename)
  }
}

/** The preview route's answer: `failed` (request error, logged) is kept apart from `data: null` (no inline preview) (#21337). */
type PreviewFetch = { failed: false; data: ConversationFilePreview | null } | { failed: true }

async function fetchPreview(deps: PreviewDeps, fileId: string): Promise<PreviewFetch> {
  try {
    const data: ConversationFilePreview | null = await deps.api.get(`${getApiBase()}/conversation-files/conversation/${deps.currentSessionId()}/preview/${fileId}`)
    return { failed: false, data }
  } catch (err: unknown) {
    logger.warn('Preview route failed, falling back to the bytes:', err)
    return { failed: true }
  }
}

/** What the pane attempt decided: `done` (shown, or superseded), `fallback` (no inline text), `failed` (route error). */
type PaneOutcome = 'done' | 'fallback' | 'failed'

export function useConversationFilePreview(deps: PreviewDeps) {
  const preview = ref<PreviewPane | null>(null)
  /** True while the latest preview request is in flight, so the pane can show progress (#20906). */
  const previewLoading = ref(false)
  const request = useLatestRequest()
  /** The file whose preview is loading, so deleting or renaming it can revoke the request (#21337). */
  let pendingFileId: string | null = null

  const closePreview = (): void => {
    request.invalidate()
    pendingFileId = null
    previewLoading.value = false
    preview.value = null
  }

  /** Close the pane, or revoke the load in flight, when it concerns one of these files (deleted or renamed). */
  const dropPreviewOf = (fileIds: string[]): void => {
    const shown = preview.value !== null && fileIds.includes(preview.value.fileId)
    const loading = pendingFileId !== null && fileIds.includes(pendingFileId)
    if (shown || loading) closePreview()
  }

  /**
   * Show the server-built preview of a text file in the pane. A superseded request is `done`: the newer call
   * owns the outcome, including `previewLoading`.
   */
  const openPreviewPane = async (file: PreviewFile, token: number): Promise<PaneOutcome> => {
    const result = await fetchPreview(deps, file.file_id)
    if (!request.isCurrent(token)) return 'done'
    previewLoading.value = false
    if (result.failed) return 'failed'
    const data = result.data
    if (!data?.preview_available || typeof data.preview_content !== 'string') return 'fallback'
    const shown = new TextEncoder().encode(data.preview_content).length
    preview.value = { fileId: file.file_id, filename: file.filename, data, truncated: file.size_bytes > shown }
    return 'done'
  }

  /** Run one preview: the pane for text, the bytes as the fallback; only the latest request writes state. */
  const runPreview = async (file: PreviewFile, token: number): Promise<void> => {
    const isCurrent = (): boolean => request.isCurrent(token)
    let routeFailed = false
    try {
      if (file.mime_type.startsWith('text/')) {
        const outcome = await openPreviewPane(file, token)
        if (outcome === 'done') return
        routeFailed = outcome === 'failed'
      }
      await openBytesPreview(deps, file, isCurrent)
    } catch (err: unknown) {
      logger.error('Preview error:', err)
      if (!isCurrent()) return
      previewLoading.value = false
      const fallback = deps.tr('previewFailed')
      // When the preview request itself failed too, the bytes error is not the whole story: say the preview failed.
      deps.error.value = routeFailed ? fallback : deps.failureText(err, fallback)
    } finally {
      if (isCurrent()) pendingFileId = null
    }
  }

  const previewFile = async (fileId: string): Promise<void> => {
    if (!deps.currentSessionId() || !fileId) {
      deps.error.value = deps.tr('missingParameters')
      return
    }
    const file = deps.files.value.find(f => f.file_id === fileId)
    if (!file) {
      deps.error.value = deps.tr('fileNotFound')
      return
    }
    const token = request.begin()
    pendingFileId = fileId
    // The pane shows one file: a different preview starting clears the previous one while this loads.
    if (preview.value && preview.value.fileId !== fileId) preview.value = null
    // Loading belongs to this request: a non-text file never shows it, and a superseded one is cleared here.
    previewLoading.value = file.mime_type.startsWith('text/')
    await runPreview(file, token)
  }

  return { preview, previewLoading, previewFile, closePreview, dropPreviewOf }
}
