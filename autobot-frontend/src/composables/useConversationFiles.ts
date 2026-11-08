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
import { ref, computed } from 'vue'
import { useApiClient } from '@/plugins/api'
import { useBatchSelection } from './useBatchSelection'
import { createLogger } from '@/utils/debugUtils'
import { extractApiErrorMessage } from '@/utils/errorExtract'
import { describeApiRefusal } from '@/utils/conversationFileUpload'
import i18n from '@/i18n'
import { getApiBase } from '@/config/ssot-config'
import type { ConversationFilePreview } from '@/utils/conversationFilePreview'
import { mapFileList, type BackendFileList } from '@/utils/conversationFileList'
import { useLoadingState } from '@/composables/useLoadingState'

// Create scoped logger for useConversationFiles
const logger = createLogger('useConversationFiles')

/** The translated text for a `chat.conversationFiles.*` key (#21159). */
function tr(key: string): string {
  return i18n.global.t(`chat.conversationFiles.${key}`)
}

/** A failure's user-facing text: the server's own detail when it sent one, else the translated fallback (#21159). */
function failureText(err: unknown, key: string): string {
  return extractApiErrorMessage(err, tr(key))
}

/** The user-facing text for a failed write: a recognised 413 refusal translated, else the server's message (#20723). */
function describeFailure(err: unknown, fallbackKey: string): string {
  const t = (key: string, params?: Record<string, unknown>) => i18n.global.t(key, params ?? {})
  return describeApiRefusal(err, t) ?? extractApiErrorMessage(err, t(fallbackKey))
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
 * @param sessionId - Chat session ID for file operations
 */
export function useConversationFiles(sessionId: string) {
  const api = useApiClient()

  // Reactive state
  const files = ref<ConversationFile[]>([])
  const stats = ref<FileStats>({
    total_files: 0,
    total_size_bytes: 0,
    uploads_count: 0,
    generated_count: 0
  })
  const { isLoading: loading, wrap } = useLoadingState()
  const error = ref<string | null>(null)
  /** The preview pane's content, from `GET .../preview/{file_id}` (#20906); null while no pane is open. */
  const preview = ref<{ filename: string; data: ConversationFilePreview } | null>(null)
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

  const API = `${getApiBase()}/conversation-files/conversation/${sessionId}`

  const loadFiles = async (): Promise<void> => {
    if (!sessionId) {
      error.value = tr('noSession')
      return
    }

    error.value = null
    await wrap(async () => {
      try {
        const data = await api.get<BackendFileList>(`${API}/list`)

        if (data) {
          const mapped = mapFileList(data, API)
          files.value = mapped.files
          stats.value = mapped.stats
        }
      } catch (err: unknown) {
        error.value = failureText(err, 'loadFailed')
        logger.error('Load error:', err)
      }
    })
  }

  const uploadFiles = async (fileList: FileList | File[]): Promise<boolean> => {
    if (!sessionId) {
      error.value = tr('noSession')
      return false
    }

    if (!fileList || fileList.length === 0) {
      error.value = tr('noFilesSelected')
      return false
    }

    error.value = null
    uploadProgress.value = 0

    return wrap(async () => {
      try {
        const formData = new FormData()

        // Add all files to FormData
        Array.from(fileList).forEach((file) => {
          formData.append('files', file)
        })

        const data = await api.post<{ success: boolean }>(
          `${getApiBase()}/conversation-files/conversation/${sessionId}/upload`,
          formData,
          {
            headers: {
              'Content-Type': 'multipart/form-data'
            },
            onUploadProgress: (progressEvent: UploadProgressEvent) => {
              if (progressEvent.total) {
                uploadProgress.value = Math.round((progressEvent.loaded * 100) / progressEvent.total)
              }
            }
          }
        )

        if (data?.success) {
          // Reload files to get updated list
          await loadFiles()
          uploadProgress.value = 100
          return true
        }

        error.value = i18n.global.t('chat.input.uploadError.unknown')
        return false

      } catch (err: unknown) {
        error.value = describeFailure(err, 'chat.input.uploadError.unknown')
        logger.error('Upload error:', err)
        return false
      } finally {
        // Reset progress after a short delay
        setTimeout(() => {
          uploadProgress.value = 0
        }, 2000)
      }
    })
  }

  const deleteFile = async (fileId: string): Promise<boolean> => {
    if (!sessionId || !fileId) {
      error.value = tr('missingParameters')
      return false
    }

    error.value = null

    return wrap(async () => {
      try {
        await api.delete<unknown>(`${getApiBase()}/conversation-files/conversation/${sessionId}/files/${fileId}`)

        // Remove file from local state
        files.value = files.value.filter(f => f.file_id !== fileId)

        // Update stats
        await loadFiles()

        return true

      } catch (err: unknown) {
        error.value = failureText(err, 'deleteFailed')
        logger.error('Delete error:', err)
        return false
      }
    })
  }

  const downloadFile = async (fileId: string, filename?: string): Promise<void> => {
    if (!sessionId || !fileId) {
      error.value = tr('missingParameters')
      return
    }

    try {
      const response = await api.rawRequest(
        `${getApiBase()}/conversation-files/conversation/${sessionId}/download/${fileId}`,
        { method: 'GET' }
      )

      const blob = await response.blob()
      // Use provided filename or get from file list
      const name = filename || files.value.find(f => f.file_id === fileId)?.filename || `file_${fileId}`
      saveBlob(blob, name)

    } catch (err: unknown) {
      error.value = failureText(err, 'downloadFailed')
      logger.error('Download error:', err)
    }
  }

  const previewFile = async (fileId: string): Promise<void> => {
    if (!sessionId || !fileId) {
      error.value = tr('missingParameters')
      return
    }

    try {
      const file = files.value.find(f => f.file_id === fileId)

      if (!file) {
        error.value = tr('fileNotFound')
        return
      }

      // For previewable types, open the bytes as a blob URL: the routes are bearer-authenticated
      // (Authorization header only), which a plain window.open() never sends (#20195).
      if (await openPreviewPane(file)) return
      const shownType = previewBlobType(file.mime_type)
      if (shownType && isPreviewable(file.mime_type)) {
        await openAuthenticatedPreview(fileId, shownType)
      } else {
        // For non-previewable types, download instead
        await downloadFile(fileId, file.filename)
      }

    } catch (err: unknown) {
      error.value = failureText(err, 'previewFailed')
      logger.error('Preview error:', err)
    }
  }

  /**
   * Fetch the server-built preview of a text file through the typed contract and show it in the pane (#20906).
   * Returns false when the route has no inline text for this file, so the caller falls back to the bytes.
   */
  const openPreviewPane = async (file: ConversationFile): Promise<boolean> => {
    if (!file.mime_type.startsWith('text/')) return false
    const data = await api.get<ConversationFilePreview>(`${API}/preview/${file.file_id}`)
    if (!data?.preview_available || typeof data.preview_content !== 'string') return false
    preview.value = { filename: file.filename, data }
    return true
  }

  const closePreview = (): void => { preview.value = null }

  /**
   * Open a file in a new tab through the authenticated client, then revoke the blob URL (#20195).
   * The tab is opened synchronously (a popup after an await is blocked), then pointed at the blob.
   */
  const openAuthenticatedPreview = async (fileId: string, shownType: string): Promise<void> => {
    const tab = window.open('', '_blank')
    try {
      const response = await api.rawRequest(`${API}/download/${fileId}`, { method: 'GET' })
      const blob = new Blob([await response.blob()], { type: shownType })
      const url = window.URL.createObjectURL(blob)
      if (tab) tab.location.href = url
      setTimeout(() => window.URL.revokeObjectURL(url), PREVIEW_BLOB_REVOKE_MS)
    } catch (err) {
      tab?.close()
      throw err
    }
  }

  const isPreviewable = (mimeType: string): boolean => {
    const previewableTypes = [
      'image/',
      'text/',
      'application/pdf',
      'application/json',
      'video/',
      'audio/'
    ]

    return previewableTypes.some(type => mimeType.startsWith(type))
  }

  // #9724: consumed by <Icon :name="..."> (ChatFilePanel) — must return an
  // SVG IconName; the previous FA class strings rendered empty SVGs.
  const getFileIcon = (mimeType: string): IconName => {
    return getFileIconNameByMimeType(mimeType)
  }

  // Issue #70: New file manager operations

  const createFile = async (filename: string, content: string = '', mimeType: string = 'text/plain'): Promise<boolean> => {
    if (!sessionId) { error.value = tr('noSession'); return false }
    error.value = null
    return wrap(async () => {
      try {
        const data = await api.post<{ success: boolean }>(`${API}/files/create`, { filename, content, mime_type: mimeType })
        if (data?.success) { await loadFiles(); return true }
        error.value = tr('createFailed')
        return false
      } catch (err: unknown) {
        error.value = describeFailure(err, 'chat.conversationFiles.createFailed')
        logger.error('Create file error:', err)
        return false
      }
    })
  }

  const renameFile = async (fileId: string, newFilename: string): Promise<boolean> => {
    if (!sessionId || !fileId) { error.value = tr('missingParameters'); return false }
    error.value = null
    try {
      const data = await api.put<{ success: boolean }>(`${API}/files/${fileId}/rename`, { new_filename: newFilename })
      if (data?.success) {
        const file = files.value.find(f => f.file_id === fileId)
        if (file) file.filename = newFilename
        return true
      }
      error.value = tr('renameFailed')
      return false
    } catch (err: unknown) {
      error.value = failureText(err, 'renameFailed')
      logger.error('Rename error:', err)
      return false
    }
  }

  const getFileContent = async (fileId: string): Promise<string | null> => {
    if (!sessionId || !fileId) { error.value = tr('missingParameters'); return null }
    try {
      const data = await api.get<{ content: string }>(`${API}/files/${fileId}/content`)
      return data?.content ?? null
    } catch (err: unknown) {
      error.value = failureText(err, 'readFailed')
      logger.error('Get content error:', err)
      return null
    }
  }

  const updateFileContent = async (fileId: string, content: string): Promise<boolean> => {
    if (!sessionId || !fileId) { error.value = tr('missingParameters'); return false }
    error.value = null
    try {
      const data = await api.put<{ success: boolean }>(`${API}/files/${fileId}/content`, { content })
      if (data?.success) { await loadFiles(); return true }
      error.value = tr('saveFailed')
      return false
    } catch (err: unknown) {
      error.value = describeFailure(err, 'chat.conversationFiles.saveFailed')
      logger.error('Update content error:', err)
      return false
    }
  }

  const copyFile = async (fileId: string, newFilename?: string): Promise<boolean> => {
    if (!sessionId || !fileId) { error.value = tr('missingParameters'); return false }
    error.value = null
    return wrap(async () => {
      try {
        const data = await api.post<{ success: boolean }>(`${API}/files/${fileId}/copy`, { new_filename: newFilename || null })
        if (data?.success) { await loadFiles(); return true }
        error.value = tr('copyFailed')
        return false
      } catch (err: unknown) {
        error.value = describeFailure(err, 'chat.conversationFiles.copyFailed')
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

  const deleteSelectedFiles = async (): Promise<boolean> => {
    const ids = Array.from(fileSelection.selected.value)
    if (ids.length === 0) return false
    error.value = null
    return wrap(async () => {
      for (const fid of ids) {
        try { await api.delete<unknown>(`${API}/files/${fid}`) } catch { /* continue */ }
      }
      fileSelection.clear()
      await loadFiles()
      return true
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
