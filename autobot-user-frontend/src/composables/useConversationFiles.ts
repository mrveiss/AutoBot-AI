/**
 * Vue Composable for Conversation-Specific File Management
 *
 * Provides reactive state and methods for managing files attached to chat conversations.
 * Integrates with ConversationFileManager backend for per-session file operations.
 */

import { ref, computed } from 'vue'
import { useApi } from './useApi'
import { createLogger } from '@/utils/debugUtils'

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

/**
 * Composable for conversation file management operations
 *
 * @param sessionId - Chat session ID for file operations
 */
export function useConversationFiles(sessionId: string) {
  const api = useApi()

  // Reactive state
  const files = ref<ConversationFile[]>([])
  const stats = ref<FileStats>({
    total_files: 0,
    total_size_bytes: 0,
    uploads_count: 0,
    generated_count: 0
  })
  const loading = ref(false)
  const error = ref<string | null>(null)
  const uploadProgress = ref<number>(0)
  const searchQuery = ref('')
  const sortField = ref<SortField>('date')
  const sortDirection = ref<SortDirection>('desc')
  const selectedFileIds = ref<Set<string>>(new Set())

  // Computed
  const hasFiles = computed(() => files.value.length > 0)
  const totalSizeFormatted = computed(() => formatFileSize(stats.value.total_size_bytes))
  const selectedCount = computed(() => selectedFileIds.value.size)
  const allSelected = computed(() => files.value.length > 0 && selectedFileIds.value.size === files.value.length)

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

  const API = `/api/conversation-files/conversation/${sessionId}`

  /**
   * Load all files for the current conversation
   */
  const loadFiles = async (): Promise<void> => {
    if (!sessionId) {
      error.value = 'No session ID provided'
      return
    }

    loading.value = true
    error.value = null

    try {
      const response = await api.get(`/api/conversation-files/conversation/${sessionId}/list`)
      // Issue #156 Fix: Call .json() to get data from Response
      const data = await response.json()

      if (data) {
        files.value = data.files || []
        stats.value = data.stats || {
          total_files: 0,
          total_size_bytes: 0,
          uploads_count: 0,
          generated_count: 0
        }
      }
    } catch (err: any) {
      error.value = err.response?.data?.detail || err.message || 'Failed to load files'
      logger.error('Load error:', err)
    } finally {
      loading.value = false
    }
  }

  /**
   * Upload files to conversation
   *
   * @param fileList - Files to upload
   */
  const uploadFiles = async (fileList: FileList | File[]): Promise<boolean> => {
    if (!sessionId) {
      error.value = 'No session ID provided'
      return false
    }

    if (!fileList || fileList.length === 0) {
      error.value = 'No files selected'
      return false
    }

    loading.value = true
    error.value = null
    uploadProgress.value = 0

    try {
      const formData = new FormData()

      // Add all files to FormData
      Array.from(fileList).forEach((file) => {
        formData.append('files', file)
      })

      const response = await api.post(
        `/api/conversation-files/conversation/${sessionId}/upload`,
        formData,
        {
          headers: {
            'Content-Type': 'multipart/form-data'
          },
          onUploadProgress: (progressEvent: any) => {
            if (progressEvent.total) {
              uploadProgress.value = Math.round((progressEvent.loaded * 100) / progressEvent.total)
            }
          }
        }
      )

      // Issue #156 Fix: Call .json() to get data from Response
      const data = await response.json()

      if (data?.success) {
        // Reload files to get updated list
        await loadFiles()
        uploadProgress.value = 100
        return true
      }

      error.value = 'Upload failed'
      return false

    } catch (err: any) {
      error.value = err.response?.data?.detail || err.message || 'Upload failed'
      logger.error('Upload error:', err)
      return false
    } finally {
      loading.value = false
      // Reset progress after a short delay
      setTimeout(() => {
        uploadProgress.value = 0
      }, 2000)
    }
  }

  /**
   * Delete a file from conversation
   *
   * @param fileId - File ID to delete
   */
  const deleteFile = async (fileId: string): Promise<boolean> => {
    if (!sessionId || !fileId) {
      error.value = 'Missing session ID or file ID'
      return false
    }

    loading.value = true
    error.value = null

    try {
      await api.delete(`/api/conversation-files/conversation/${sessionId}/files/${fileId}`)

      // Remove file from local state
      files.value = files.value.filter(f => f.file_id !== fileId)

      // Update stats
      await loadFiles()

      return true

    } catch (err: any) {
      error.value = err.response?.data?.detail || err.message || 'Failed to delete file'
      logger.error('Delete error:', err)
      return false
    } finally {
      loading.value = false
    }
  }

  /**
   * Download a file from conversation
   *
   * @param fileId - File ID to download
   * @param filename - Optional filename for download
   */
  const downloadFile = async (fileId: string, filename?: string): Promise<void> => {
    if (!sessionId || !fileId) {
      error.value = 'Missing session ID or file ID'
      return
    }

    try {
      const response = await api.get(
        `/api/conversation-files/conversation/${sessionId}/download/${fileId}`,
        { responseType: 'blob' }
      )

      // Issue #156 Fix: Call .blob() to get blob data from Response
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

    } catch (err: any) {
      error.value = err.response?.data?.detail || err.message || 'Download failed'
      logger.error('Download error:', err)
    }
  }

  /**
   * Preview a file (opens in new tab or shows preview modal)
   *
   * @param fileId - File ID to preview
   */
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
        const previewUrl = `/api/conversation-files/conversation/${sessionId}/preview/${fileId}`
        window.open(previewUrl, '_blank')
      } else {
        // For non-previewable types, download instead
        await downloadFile(fileId, file.filename)
      }

    } catch (err: any) {
      error.value = err.response?.data?.detail || err.message || 'Preview failed'
      logger.error('Preview error:', err)
    }
  }

  /**
   * Check if a MIME type is previewable in browser
   */
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

  /**
   * Get Font Awesome icon class for file MIME type
   */
  const getFileIcon = (mimeType: string): string => {
    if (mimeType.startsWith('image/')) return 'fas fa-image'
    if (mimeType.startsWith('video/')) return 'fas fa-video'
    if (mimeType.startsWith('audio/')) return 'fas fa-music'
    if (mimeType.includes('pdf')) return 'fas fa-file-pdf'
    if (mimeType.includes('word') || mimeType.includes('document')) return 'fas fa-file-word'
    if (mimeType.includes('excel') || mimeType.includes('spreadsheet')) return 'fas fa-file-excel'
    if (mimeType.includes('powerpoint') || mimeType.includes('presentation')) return 'fas fa-file-powerpoint'
    if (mimeType.includes('zip') || mimeType.includes('archive')) return 'fas fa-file-archive'
    if (mimeType.startsWith('text/')) return 'fas fa-file-alt'
    if (mimeType.includes('json')) return 'fas fa-file-code'
    return 'fas fa-file'
  }

  /**
   * Format file size in human-readable format
   */
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
    loading.value = true
    error.value = null
    try {
      const response = await api.post(`${API}/files/create`, { filename, content, mime_type: mimeType })
      const data = await response.json()
      if (data?.success) { await loadFiles(); return true }
      error.value = 'Failed to create file'
      return false
    } catch (err: any) {
      error.value = err.response?.data?.detail || err.message || 'Failed to create file'
      logger.error('Create file error:', err)
      return false
    } finally { loading.value = false }
  }

  const renameFile = async (fileId: string, newFilename: string): Promise<boolean> => {
    if (!sessionId || !fileId) { error.value = 'Missing parameters'; return false }
    error.value = null
    try {
      const response = await api.put(`${API}/files/${fileId}/rename`, { new_filename: newFilename })
      const data = await response.json()
      if (data?.success) {
        const file = files.value.find(f => f.file_id === fileId)
        if (file) file.filename = newFilename
        return true
      }
      error.value = 'Rename failed'
      return false
    } catch (err: any) {
      error.value = err.response?.data?.detail || err.message || 'Rename failed'
      logger.error('Rename error:', err)
      return false
    }
  }

  const getFileContent = async (fileId: string): Promise<string | null> => {
    if (!sessionId || !fileId) { error.value = 'Missing parameters'; return null }
    try {
      const response = await api.get(`${API}/files/${fileId}/content`)
      const data = await response.json()
      return data?.content ?? null
    } catch (err: any) {
      error.value = err.response?.data?.detail || err.message || 'Failed to read file'
      logger.error('Get content error:', err)
      return null
    }
  }

  const updateFileContent = async (fileId: string, content: string): Promise<boolean> => {
    if (!sessionId || !fileId) { error.value = 'Missing parameters'; return false }
    error.value = null
    try {
      const response = await api.put(`${API}/files/${fileId}/content`, { content })
      const data = await response.json()
      if (data?.success) { await loadFiles(); return true }
      error.value = 'Save failed'
      return false
    } catch (err: any) {
      error.value = err.response?.data?.detail || err.message || 'Save failed'
      logger.error('Update content error:', err)
      return false
    }
  }

  const copyFile = async (fileId: string, newFilename?: string): Promise<boolean> => {
    if (!sessionId || !fileId) { error.value = 'Missing parameters'; return false }
    loading.value = true
    error.value = null
    try {
      const response = await api.post(`${API}/files/${fileId}/copy`, { new_filename: newFilename || null })
      const data = await response.json()
      if (data?.success) { await loadFiles(); return true }
      error.value = 'Copy failed'
      return false
    } catch (err: any) {
      error.value = err.response?.data?.detail || err.message || 'Copy failed'
      logger.error('Copy error:', err)
      return false
    } finally { loading.value = false }
  }

  const isEditable = (mimeType: string): boolean => {
    const editableTypes = ['text/', 'application/json', 'application/xml', 'application/javascript']
    return editableTypes.some(type => mimeType.startsWith(type))
  }

  // Bulk & sort operations

  const toggleFileSelection = (fileId: string) => {
    const next = new Set(selectedFileIds.value)
    if (next.has(fileId)) { next.delete(fileId) } else { next.add(fileId) }
    selectedFileIds.value = next
  }

  const selectAllFiles = () => {
    if (allSelected.value) {
      selectedFileIds.value = new Set()
    } else {
      selectedFileIds.value = new Set(files.value.map(f => f.file_id))
    }
  }

  const deleteSelectedFiles = async (): Promise<boolean> => {
    const ids = Array.from(selectedFileIds.value)
    if (ids.length === 0) return false
    loading.value = true
    error.value = null
    for (const fid of ids) {
      try { await api.delete(`${API}/files/${fid}`) } catch { /* continue */ }
    }
    selectedFileIds.value = new Set()
    await loadFiles()
    loading.value = false
    return true
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
