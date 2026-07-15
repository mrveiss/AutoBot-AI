// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Vue Composable for Conversation-Specific File Management
 *
 * Provides reactive state and methods for managing files attached to chat conversations.
 * Integrates with ConversationFileManager backend for per-session file operations.
 */

import { getFileIconNameByMimeType } from '@/utils/iconMappings'
import type { IconName } from '@/components/ui/Icon.vue'
import { ref, computed } from 'vue'
import { useApiClient } from '@/plugins/api'
import { useBatchSelection } from './useBatchSelection'
import { createLogger } from '@/utils/debugUtils'
import { extractApiErrorMessage } from '@/utils/errorExtract'
import { getApiBase } from '@/config/ssot-config'
import { useLoadingState } from '@/composables/useLoadingState'

// Create scoped logger for useConversationFiles
const logger = createLogger('useConversationFiles')

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
  preview_url: string
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
      error.value = 'No session ID provided'
      return
    }

    error.value = null
    await wrap(async () => {
      try {
        const data = await api.get<{ files: ConversationFile[]; stats: FileStats }>(`${getApiBase()}/conversation-files/conversation/${sessionId}/list`)

        if (data) {
          files.value = data.files || []
          stats.value = data.stats || {
            total_files: 0,
            total_size_bytes: 0,
            uploads_count: 0,
            generated_count: 0
          }
        }
      } catch (err: unknown) {
        error.value = extractApiErrorMessage(err, 'Failed to load files')
        logger.error('Load error:', err)
      }
    })
  }

  const uploadFiles = async (fileList: FileList | File[]): Promise<boolean> => {
    if (!sessionId) {
      error.value = 'No session ID provided'
      return false
    }

    if (!fileList || fileList.length === 0) {
      error.value = 'No files selected'
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

        error.value = 'Upload failed'
        return false

      } catch (err: unknown) {
        error.value = extractApiErrorMessage(err, 'Upload failed')
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
      error.value = 'Missing session ID or file ID'
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
        error.value = extractApiErrorMessage(err, 'Failed to delete file')
        logger.error('Delete error:', err)
        return false
      }
    })
  }

  const downloadFile = async (fileId: string, filename?: string): Promise<void> => {
    if (!sessionId || !fileId) {
      error.value = 'Missing session ID or file ID'
      return
    }

    try {
      const response = await api.rawRequest(
        `${getApiBase()}/conversation-files/conversation/${sessionId}/download/${fileId}`,
        { method: 'GET' }
      )

      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url

      // Use provided filename or get from file list
      if (filename) {
        link.download = filename
      } else {
        const file = files.value.find(f => f.file_id === fileId)
        link.download = file?.filename || `file_${fileId}`
      }

      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)

    } catch (err: unknown) {
      error.value = extractApiErrorMessage(err, 'Download failed')
      logger.error('Download error:', err)
    }
  }

  const previewFile = async (fileId: string): Promise<void> => {
    if (!sessionId || !fileId) {
      error.value = 'Missing session ID or file ID'
      return
    }

    try {
      const file = files.value.find(f => f.file_id === fileId)

      if (!file) {
        error.value = 'File not found'
        return
      }

      // For previewable types, open preview URL
      if (isPreviewable(file.mime_type)) {
        const previewUrl = `${getApiBase()}/conversation-files/conversation/${sessionId}/preview/${fileId}`
        window.open(previewUrl, '_blank')
      } else {
        // For non-previewable types, download instead
        await downloadFile(fileId, file.filename)
      }

    } catch (err: unknown) {
      error.value = extractApiErrorMessage(err, 'Preview failed')
      logger.error('Preview error:', err)
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

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes'

    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))

    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`
  }

  // Issue #70: New file manager operations

  const createFile = async (filename: string, content: string = '', mimeType: string = 'text/plain'): Promise<boolean> => {
    if (!sessionId) { error.value = 'No session ID'; return false }
    error.value = null
    return wrap(async () => {
      try {
        const data = await api.post<{ success: boolean }>(`${API}/files/create`, { filename, content, mime_type: mimeType })
        if (data?.success) { await loadFiles(); return true }
        error.value = 'Failed to create file'
        return false
      } catch (err: unknown) {
        error.value = extractApiErrorMessage(err, 'Failed to create file')
        logger.error('Create file error:', err)
        return false
      }
    })
  }

  const renameFile = async (fileId: string, newFilename: string): Promise<boolean> => {
    if (!sessionId || !fileId) { error.value = 'Missing parameters'; return false }
    error.value = null
    try {
      const data = await api.put<{ success: boolean }>(`${API}/files/${fileId}/rename`, { new_filename: newFilename })
      if (data?.success) {
        const file = files.value.find(f => f.file_id === fileId)
        if (file) file.filename = newFilename
        return true
      }
      error.value = 'Rename failed'
      return false
    } catch (err: unknown) {
      error.value = extractApiErrorMessage(err, 'Rename failed')
      logger.error('Rename error:', err)
      return false
    }
  }

  const getFileContent = async (fileId: string): Promise<string | null> => {
    if (!sessionId || !fileId) { error.value = 'Missing parameters'; return null }
    try {
      const data = await api.get<{ content: string }>(`${API}/files/${fileId}/content`)
      return data?.content ?? null
    } catch (err: unknown) {
      error.value = extractApiErrorMessage(err, 'Failed to read file')
      logger.error('Get content error:', err)
      return null
    }
  }

  const updateFileContent = async (fileId: string, content: string): Promise<boolean> => {
    if (!sessionId || !fileId) { error.value = 'Missing parameters'; return false }
    error.value = null
    try {
      const data = await api.put<{ success: boolean }>(`${API}/files/${fileId}/content`, { content })
      if (data?.success) { await loadFiles(); return true }
      error.value = 'Save failed'
      return false
    } catch (err: unknown) {
      error.value = extractApiErrorMessage(err, 'Save failed')
      logger.error('Update content error:', err)
      return false
    }
  }

  const copyFile = async (fileId: string, newFilename?: string): Promise<boolean> => {
    if (!sessionId || !fileId) { error.value = 'Missing parameters'; return false }
    error.value = null
    return wrap(async () => {
      try {
        const data = await api.post<{ success: boolean }>(`${API}/files/${fileId}/copy`, { new_filename: newFilename || null })
        if (data?.success) { await loadFiles(); return true }
        error.value = 'Copy failed'
        return false
      } catch (err: unknown) {
        error.value = extractApiErrorMessage(err, 'Copy failed')
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
