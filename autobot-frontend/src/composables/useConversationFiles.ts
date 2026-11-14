// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Vue Composable for Conversation-Specific File Management
 *
 * Provides reactive state and methods for managing files attached to chat conversations.
 * Integrates with ConversationFileManager backend for per-session file operations.
 */

import { saveBlob } from '@autobot/ui'
import { getFileIconNameByMimeType } from '@/utils/iconMappings'
import { formatFileSize } from '@/utils/formatHelpers'
import type { IconName } from '@/components/ui/Icon.vue'
import { ref, computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useApiClient } from '@/plugins/api'
import { useBatchSelection } from './useBatchSelection'
import { useLoadingState } from './useLoadingState'
import { createLogger } from '@/utils/debugUtils'
import { extractApiErrorMessage } from '@/utils/errorExtract'
import { describeApiRefusal } from '@/utils/conversationFileUpload'
import i18n from '@/i18n'
import { getApiBase } from '@/config/ssot-config'
import { mapFileList, type BackendFileList } from '@/utils/conversationFileList'
import { useLatestRequest } from './useLatestRequest'
import {
  useConversationFilePreview,
  isPreviewable,
  type PreviewPane
} from './useConversationFilePreview'

export type { PreviewPane }

// Create scoped logger for useConversationFiles
const logger = createLogger('useConversationFiles')

/** The translated text for a `chat.conversationFiles.*` key (#21159). */
function tr(key: string): string {
  return i18n.global.t(`chat.conversationFiles.${key}`)
}

/**
 * A failure's user-facing text, from the already-translated fallback: a recognised 413 refusal translated (#20723),
 * else the server's own detail when it sent one, else the fallback (#21159).
 */
function failureText(err: unknown, fallback: string): string {
  const t = (key: string, params?: Record<string, unknown>) => i18n.global.t(key, params ?? {})
  // An empty message (e.g. `new Error('')`) is no message: the translated fallback applies (#21185).
  return describeApiRefusal(err, t) ?? (extractApiErrorMessage(err, fallback) || fallback)
}

/**
 * File metadata interface matching backend ConversationFile model
 */
export interface ConversationFile {
  file_id: string
  filename: string
  file_type: 'upload' | 'generated' | 'created'
  mime_type: string
  size_bytes: number
  upload_timestamp: string
  download_url: string
}

/** Issue #70: Sort options for file list */
export type SortField = 'name' | 'date' | 'size' | 'type'
export type SortDirection = 'asc' | 'desc'

/**
 * File statistics for conversation
 */
export interface FileStats {
  total_files: number
  total_size_bytes: number
  uploads_count: number
  generated_count: number
}

export interface UploadProgressEvent {
  loaded: number
  total?: number
}

/**
 * Composable for conversation file management operations
 *
 * @param sessionIdSource - Chat session ID (string, ref or getter); resolved on every call
 */
export function useConversationFiles(sessionIdSource: MaybeRefOrGetter<string>) {
  const api = useApiClient()
  // Resolved per call so a conversation switch is honoured by every request.
  const currentSessionId = (): string => toValue(sessionIdSource)

  // Reactive state
  const files = ref<ConversationFile[]>([])
  const stats = ref<FileStats>({
    total_files: 0,
    total_size_bytes: 0,
    uploads_count: 0,
    generated_count: 0
  })
  /**
   * Mutations (upload, delete, ...) in flight for the CURRENT conversation (#21159). `resetOps()` on a conversation
   * switch drops those started in the previous one so they neither count toward `loading` nor settle the new count.
   */
  const { isLoading: opLoading, wrap, reset: resetOps } = useLoadingState()
  /** True while the latest list request is in flight; a superseded request never clears it (#21159). */
  const listLoading = ref(false)
  const loading = computed(() => opLoading.value || listLoading.value)
  const error = ref<string | null>(null)
  const listRequest = useLatestRequest()
  const uploadRequest = useLatestRequest()
  const uploadProgress = ref<number>(0)
  const searchQuery = ref('')
  const sortField = ref<SortField>('date')
  const sortDirection = ref<SortDirection>('desc')
  // Selection state is owned by the shared useBatchSelection primitive (#5322);
  // `files` is passed as the reactive items source so `allSelected`/`selectedCount`
  // stay in sync automatically when the file list changes.
  const fileSelection = useBatchSelection<ConversationFile, string>(
    files,
    (f) => f.file_id,
  )
  const selectedFileIds = fileSelection.selected
  const selectedCount = fileSelection.selectedCount
  const allSelected = fileSelection.allSelected

  // Computed
  const hasFiles = computed(() => files.value.length > 0)
  const totalSizeFormatted = computed(() => formatFileSize(stats.value.total_size_bytes))

  const sortedFiles = computed(() => {
    let result = [...files.value]
    if (searchQuery.value) {
      const q = searchQuery.value.toLowerCase()
      result = result.filter(f => f.filename.toLowerCase().includes(q))
    }
    result.sort((a, b) => {
      let cmp = 0
      switch (sortField.value) {
        case 'name': cmp = a.filename.localeCompare(b.filename); break
        case 'size': cmp = a.size_bytes - b.size_bytes; break
        case 'type': cmp = (a.mime_type || '').localeCompare(b.mime_type || ''); break
        default: cmp = new Date(a.upload_timestamp).getTime() - new Date(b.upload_timestamp).getTime()
      }
      return sortDirection.value === 'asc' ? cmp : -cmp
    })
    return result
  })

  const conversationApi = (): string =>
    `${getApiBase()}/conversation-files/conversation/${currentSessionId()}`

  const loadFiles = async (): Promise<void> => {
    if (!currentSessionId()) {
      listRequest.invalidate()
      listLoading.value = false
      error.value = tr('noSession')
      return
    }

    error.value = null
    const token = listRequest.begin()
    const requestedSession = currentSessionId()
    const base = conversationApi()
    listLoading.value = true
    try {
      const data = await api.get<BackendFileList>(`${getApiBase()}/conversation-files/conversation/${currentSessionId()}/list`)
      // Only the latest request may write: a reply for a conversation the user left, or an older one, is dropped.
      if (data && listRequest.isCurrent(token) && requestedSession === currentSessionId()) {
        const mapped = mapFileList(data, base)
        files.value = mapped.files
        stats.value = mapped.stats
      }
    } catch (err: unknown) {
      if (listRequest.isCurrent(token) && requestedSession === currentSessionId()) {
        error.value = failureText(err, tr('loadFailed'))
      }
      logger.error('Load error:', err)
    } finally {
      if (listRequest.isCurrent(token)) listLoading.value = false
    }
  }

  /** Run one upload; progress, errors and the reload belong to the session that started it (#21159). */
  const sendUpload = async (fileList: FileList | File[], session: string, token: number): Promise<boolean> => {
    const inSession = (): boolean => currentSessionId() === session
    // The token only gates the shared progress display; the reload and the error belong to the session.
    const owns = (): boolean => uploadRequest.isCurrent(token) && inSession()
    try {
      const formData = new FormData()
      Array.from(fileList).forEach((file) => formData.append('files', file))
      const data = await api.post<{ success: boolean }>(`${getApiBase()}/conversation-files/conversation/${currentSessionId()}/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (progressEvent: UploadProgressEvent) => {
          if (progressEvent.total && owns()) {
            uploadProgress.value = Math.round((progressEvent.loaded * 100) / progressEvent.total)
          }
        }
      })
      if (data?.success) {
        if (inSession()) await loadFiles()
        if (owns()) uploadProgress.value = 100
        return true
      }
      if (inSession()) error.value = i18n.global.t('chat.input.uploadError.unknown')
      return false
    } catch (err: unknown) {
      if (inSession()) error.value = failureText(err, i18n.global.t('chat.input.uploadError.unknown'))
      logger.error('Upload error:', err)
      return false
    } finally {
      // Reset progress after a short delay, unless a newer upload or a conversation switch took it over.
      setTimeout(() => { if (owns()) uploadProgress.value = 0 }, 2000)
    }
  }

  const uploadFiles = async (fileList: FileList | File[]): Promise<boolean> => {
    if (!currentSessionId()) {
      error.value = tr('noSession')
      return false
    }
    if (!fileList || fileList.length === 0) {
      error.value = tr('noFilesSelected')
      return false
    }
    error.value = null
    uploadProgress.value = 0
    const session = currentSessionId()
    const token = uploadRequest.begin()
    return wrap(() => sendUpload(fileList, session, token))
  }

  const deleteFile = async (fileId: string): Promise<boolean> => {
    if (!currentSessionId() || !fileId) {
      error.value = tr('missingParameters')
      return false
    }

    error.value = null
    const session = currentSessionId()

    return wrap(async () => {
      try {
        await api.delete<unknown>(`${getApiBase()}/conversation-files/conversation/${currentSessionId()}/files/${fileId}`)

        // A switch while the delete was pending: the new conversation's state is not ours to touch.
        if (currentSessionId() !== session) return true
        // Remove file from local state
        files.value = files.value.filter(f => f.file_id !== fileId)
        dropPreviewOf([fileId])

        // Update stats
        await loadFiles()

        return true

      } catch (err: unknown) {
        if (currentSessionId() === session) error.value = failureText(err, tr('deleteFailed'))
        logger.error('Delete error:', err)
        return false
      }
    })
  }

  const downloadFile = async (fileId: string, filename?: string): Promise<void> => {
    if (!currentSessionId() || !fileId) {
      error.value = tr('missingParameters')
      return
    }

    const session = currentSessionId()
    try {
      const response = await api.rawRequest(
        `${getApiBase()}/conversation-files/conversation/${currentSessionId()}/download/${fileId}`,
        { method: 'GET' }
      )

      const blob = await response.blob()
      // Use provided filename or get from file list
      const name = filename || files.value.find(f => f.file_id === fileId)?.filename || `file_${fileId}`
      saveBlob(blob, name)

    } catch (err: unknown) {
      if (currentSessionId() === session) error.value = failureText(err, tr('downloadFailed'))
      logger.error('Download error:', err)
    }
  }

  const { preview, previewLoading, previewFile, closePreview, dropPreviewOf } = useConversationFilePreview({
    api, currentSessionId, files, error, tr, failureText, downloadFile
  })

  /**
   * Conversation switch (#21159): drop everything that belongs to the previous conversation at once, and revoke
   * the in-flight list/upload/preview requests so none of their replies can land in the new one.
   */
  const resetForSession = (): void => {
    listRequest.invalidate()
    uploadRequest.invalidate()
    resetOps()
    listLoading.value = false
    uploadProgress.value = 0
    files.value = []
    stats.value = { total_files: 0, total_size_bytes: 0, uploads_count: 0, generated_count: 0 }
    fileSelection.clear()
    closePreview()
  }

  // #9724: consumed by <Icon :name="..."> (ChatFilePanel) — must return an
  // SVG IconName; the previous FA class strings rendered empty SVGs.
  const getFileIcon = (mimeType: string): IconName => {
    return getFileIconNameByMimeType(mimeType)
  }

  // Issue #70: New file manager operations

  const createFile = async (filename: string, content: string = '', mimeType: string = 'text/plain'): Promise<boolean> => {
    if (!currentSessionId()) { error.value = tr('noSession'); return false }
    error.value = null
    const session = currentSessionId()
    return wrap(async () => {
      try {
        const data = await api.post<{ success: boolean }>(`${getApiBase()}/conversation-files/conversation/${currentSessionId()}/files/create`, { filename, content, mime_type: mimeType })
        if (data?.success) { await loadFiles(); return true }
        if (currentSessionId() === session) error.value = tr('createFailed')
        return false
      } catch (err: unknown) {
        if (currentSessionId() === session) error.value = failureText(err, tr('createFailed'))
        logger.error('Create file error:', err)
        return false
      }
    })
  }

  const renameFile = async (fileId: string, newFilename: string): Promise<boolean> => {
    if (!currentSessionId() || !fileId) { error.value = tr('missingParameters'); return false }
    error.value = null
    const session = currentSessionId()
    try {
      const data = await api.put<{ success: boolean }>(`${getApiBase()}/conversation-files/conversation/${currentSessionId()}/files/${fileId}/rename`, { new_filename: newFilename })
      if (data?.success) {
        if (currentSessionId() !== session) return true
        const file = files.value.find(f => f.file_id === fileId)
        if (file) file.filename = newFilename
        dropPreviewOf([fileId])
        return true
      }
      if (currentSessionId() === session) error.value = tr('renameFailed')
      return false
    } catch (err: unknown) {
      if (currentSessionId() === session) error.value = failureText(err, tr('renameFailed'))
      logger.error('Rename error:', err)
      return false
    }
  }

  const getFileContent = async (fileId: string): Promise<string | null> => {
    if (!currentSessionId() || !fileId) { error.value = tr('missingParameters'); return null }
    const session = currentSessionId()
    try {
      const data = await api.get<{ content: string }>(`${getApiBase()}/conversation-files/conversation/${currentSessionId()}/files/${fileId}/content`)
      return data?.content ?? null
    } catch (err: unknown) {
      if (currentSessionId() === session) error.value = failureText(err, tr('readFailed'))
      logger.error('Get content error:', err)
      return null
    }
  }

  const updateFileContent = async (fileId: string, content: string): Promise<boolean> => {
    if (!currentSessionId() || !fileId) { error.value = tr('missingParameters'); return false }
    error.value = null
    const session = currentSessionId()
    try {
      const data = await api.put<{ success: boolean }>(`${getApiBase()}/conversation-files/conversation/${currentSessionId()}/files/${fileId}/content`, { content })
      if (data?.success) { await loadFiles(); return true }
      if (currentSessionId() === session) error.value = tr('saveFailed')
      return false
    } catch (err: unknown) {
      if (currentSessionId() === session) error.value = failureText(err, tr('saveFailed'))
      logger.error('Update content error:', err)
      return false
    }
  }

  const copyFile = async (fileId: string, newFilename?: string): Promise<boolean> => {
    if (!currentSessionId() || !fileId) { error.value = tr('missingParameters'); return false }
    error.value = null
    const session = currentSessionId()
    return wrap(async () => {
      try {
        const data = await api.post<{ success: boolean }>(`${getApiBase()}/conversation-files/conversation/${currentSessionId()}/files/${fileId}/copy`, { new_filename: newFilename || null })
        if (data?.success) { await loadFiles(); return true }
        if (currentSessionId() === session) error.value = tr('copyFailed')
        return false
      } catch (err: unknown) {
        if (currentSessionId() === session) error.value = failureText(err, tr('copyFailed'))
        logger.error('Copy error:', err)
        return false
      }
    })
  }

  const isEditable = (mimeType: string): boolean => {
    const editableTypes = ['text/', 'application/json', 'application/xml', 'application/javascript']
    return editableTypes.some(type => mimeType.startsWith(type))
  }

  // Bulk & sort operations

  const toggleFileSelection = (fileId: string) => {
    fileSelection.toggleByKey(fileId)
  }

  const selectAllFiles = () => {
    if (fileSelection.allSelected.value) {
      fileSelection.clear()
    } else {
      fileSelection.selectAll()
    }
  }

  /** Delete each id in the session that started the bulk delete; returns the ids that were deleted and the first failure (#21337). */
  const deleteEach = async (ids: string[], session: string): Promise<{ deleted: string[]; failure: unknown }> => {
    const deleted: string[] = []
    let failure: unknown = null
    for (const fid of ids) {
      try {
        await api.call('delete', '/api/conversation-files/conversation/{session_id}/files/{file_id}', { path: { session_id: session, file_id: fid } })
        deleted.push(fid)
      } catch (err: unknown) {
        failure ??= err
        logger.error('Bulk delete error:', err)
      }
    }
    return { deleted, failure }
  }

  const deleteSelectedFiles = async (): Promise<boolean> => {
    const ids = Array.from(fileSelection.selected.value)
    if (ids.length === 0) return false
    error.value = null
    const session = currentSessionId()
    return wrap(async () => {
      const { deleted, failure } = await deleteEach(ids, session)
      // A switch mid-loop already reset the new conversation's state; only report into the session that asked.
      if (currentSessionId() !== session) return failure === null
      dropPreviewOf(deleted)
      deleted.forEach(fid => fileSelection.deselectByKey(fid))
      await loadFiles()
      // The reload may have outlived the conversation: its failure text is not the new conversation's to show.
      if (failure !== null && currentSessionId() === session) error.value = failureText(failure, tr('deleteFailed'))
      return failure === null
    })
  }

  const setSort = (field: SortField) => {
    if (sortField.value === field) {
      sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
    } else {
      sortField.value = field
      sortDirection.value = field === 'name' ? 'asc' : 'desc'
    }
  }

  const clearError = (): void => { error.value = null }

  return {
    // State
    files,
    stats,
    loading,
    error,
    preview,
    previewLoading,
    uploadProgress,
    searchQuery,
    sortField,
    sortDirection,
    selectedFileIds,

    // Computed
    hasFiles,
    totalSizeFormatted,
    sortedFiles,
    selectedCount,
    allSelected,

    // Core methods
    loadFiles,
    uploadFiles,
    deleteFile,
    downloadFile,
    previewFile,
    closePreview,
    resetForSession,

    // Issue #70: New operations
    createFile,
    renameFile,
    getFileContent,
    updateFileContent,
    copyFile,

    // Bulk & sort
    toggleFileSelection,
    selectAllFiles,
    deleteSelectedFiles,
    setSort,

    // Utilities
    getFileIcon,
    formatFileSize,
    isPreviewable,
    isEditable,
    clearError
  }
}
