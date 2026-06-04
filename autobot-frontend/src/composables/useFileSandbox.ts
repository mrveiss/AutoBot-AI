// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import { extractApiErrorMessage } from '@/utils/errorExtract'
import { getApiBase } from '@/config/ssot-config'
import { useLoadingState } from '@/composables/useLoadingState'

const logger = createLogger('useFileSandbox')

export interface SandboxFileInfo {
  name: string
  path: string
  size: number
  modified: string
  is_dir: boolean
}

export interface SandboxTreeNode {
  name: string
  path: string
  is_dir: boolean
  children?: SandboxTreeNode[]
}

export interface SandboxStats {
  sandbox_root: string
  total_files: number
  total_directories: number
  total_size: number
  total_size_mb: number
  max_file_size_mb: number
  allowed_extensions: string[]
}

export interface SandboxPreview {
  type: string
  url: string
  content?: string
  mime_type?: string
  size: number
  name: string
}

export function useFileSandbox() {
  const api = useApiClient()

  const tree = ref<SandboxTreeNode[]>([])
  const stats = ref<SandboxStats | null>(null)
  const { isLoading: loading, wrap } = useLoadingState()
  const error = ref<string | null>(null)

  const API = `${getApiBase()}/sandbox/files`

  const viewFile = async (path: string): Promise<SandboxFileInfo | null> => {
    error.value = null
    try {
      return await api.get<SandboxFileInfo>(`${API}/view/${encodeURIComponent(path)}`)
    } catch (err: unknown) {
      error.value = extractApiErrorMessage(err, 'Failed to view file')
      logger.error('View file error:', err)
      return null
    }
  }

  const previewFile = async (path: string): Promise<SandboxPreview | null> => {
    error.value = null
    try {
      return await api.get<SandboxPreview>(`${API}/preview?path=${encodeURIComponent(path)}`)
    } catch (err: unknown) {
      error.value = extractApiErrorMessage(err, 'Failed to preview file')
      logger.error('Preview file error:', err)
      return null
    }
  }

  const getTree = async (path?: string): Promise<void> => {
    error.value = null
    await wrap(async () => {
      try {
        const url = path ? `${API}/tree?path=${encodeURIComponent(path)}` : `${API}/tree`
        const data = await api.get<SandboxTreeNode[]>(url)
        tree.value = data ?? []
      } catch (err: unknown) {
        error.value = extractApiErrorMessage(err, 'Failed to load tree')
        logger.error('Get tree error:', err)
      }
    })
  }

  const getStats = async (): Promise<void> => {
    error.value = null
    await wrap(async () => {
      try {
        const data = await api.get<SandboxStats>(`${API}/stats`)
        stats.value = data ?? null
      } catch (err: unknown) {
        error.value = extractApiErrorMessage(err, 'Failed to load stats')
        logger.error('Get stats error:', err)
      }
    })
  }

  const renameItem = async (path: string, newName: string): Promise<boolean> => {
    error.value = null
    return wrap(async () => {
      try {
        const formData = new FormData()
        formData.append('path', path)
        formData.append('new_name', newName)
        await api.post<void>(`${API}/rename`, formData)
        await getTree()
        return true
      } catch (err: unknown) {
        error.value = extractApiErrorMessage(err, 'Rename failed')
        logger.error('Rename error:', err)
        return false
      }
    })
  }

  const deleteItem = async (path: string): Promise<boolean> => {
    error.value = null
    return wrap(async () => {
      try {
        await api.delete<void>(`${API}/delete?path=${encodeURIComponent(path)}`)
        await getTree()
        return true
      } catch (err: unknown) {
        error.value = extractApiErrorMessage(err, 'Delete failed')
        logger.error('Delete error:', err)
        return false
      }
    })
  }

  const createDirectory = async (path: string, name: string): Promise<boolean> => {
    error.value = null
    return wrap(async () => {
      try {
        const formData = new FormData()
        formData.append('path', path)
        formData.append('name', name)
        await api.post<void>(`${API}/create_directory`, formData)
        await getTree()
        return true
      } catch (err: unknown) {
        error.value = extractApiErrorMessage(err, 'Failed to create directory')
        logger.error('Create directory error:', err)
        return false
      }
    })
  }

  const clearError = (): void => { error.value = null }

  return {
    // State
    tree,
    stats,
    loading,
    error,

    // Read methods
    viewFile,
    previewFile,
    getTree,
    getStats,

    // Write methods
    renameItem,
    deleteItem,
    createDirectory,

    // Utilities
    clearError,
  }
}
