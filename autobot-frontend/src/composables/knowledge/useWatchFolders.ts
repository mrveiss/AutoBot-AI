/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2026 mrveiss
 * Author: mrveiss
 *
 * Composable for managing KB watch folders
 *
 * Issue #9000: Auto-watch folder for KB ingestion
 */

import { ref, computed } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useWatchFolders')

export interface WatchFolderConfig {
  folder_id?: string
  path: string
  collection: string
  enabled: boolean
  file_types: string[]
  recursive: boolean
  category: string
  tags: string[]
  created_at?: string
  is_watching?: boolean
  stats?: {
    files_ingested: number
    last_change: string | null
    errors: number
  }
}

export interface WatchFolderStats {
  is_running: boolean
  total_folders: number
  active_folders: number
  total_files_ingested: number
  total_errors: number
  folders: WatchFolderConfig[]
}

export function useWatchFolders() {
  const api = useApiClient()

  const watchFolders = ref<WatchFolderConfig[]>([])
  const stats = ref<WatchFolderStats | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const activeCount = computed(() => {
    return watchFolders.value.filter(f => f.is_watching).length
  })

  const totalIngested = computed(() => {
    return watchFolders.value.reduce((sum, f) => {
      return sum + (f.stats?.files_ingested || 0)
    }, 0)
  })

  /**
   * Load all watch folders
   */
  async function loadWatchFolders() {
    loading.value = true
    error.value = null

    try {
      const response = await api.get<{
        success: boolean
        folders: WatchFolderConfig[]
        total: number
      }>('/api/knowledge_base/watch-folders')

      if (response.success) {
        watchFolders.value = response.folders
      } else {
        error.value = 'Failed to load watch folders'
      }
    } catch (err) {
      logger.error('Error loading watch folders:', err)
      error.value = err instanceof Error ? err.message : 'Unknown error'
      watchFolders.value = []
    } finally {
      loading.value = false
    }
  }

  /**
   * Create a new watch folder
   */
  async function createWatchFolder(config: Omit<WatchFolderConfig, 'folder_id' | 'created_at' | 'is_watching' | 'stats'>) {
    loading.value = true
    error.value = null

    try {
      const response = await api.post<{
        success: boolean
        message?: string
        folder_id?: string
        folder?: WatchFolderConfig
      }>('/api/knowledge_base/watch-folders', config)

      if (response.success && response.folder) {
        watchFolders.value.push(response.folder)
        logger.info('Watch folder created:', response.folder_id)
        return response.folder_id
      } else {
        error.value = response.message || 'Failed to create watch folder'
        return null
      }
    } catch (err) {
      logger.error('Error creating watch folder:', err)
      error.value = err instanceof Error ? err.message : 'Unknown error'
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * Delete a watch folder
   */
  async function deleteWatchFolder(folderId: string) {
    loading.value = true
    error.value = null

    try {
      const response = await api.delete<{
        success: boolean
        message?: string
      }>(`/api/knowledge_base/watch-folders/${folderId}`)

      if (response.success) {
        watchFolders.value = watchFolders.value.filter(f => f.folder_id !== folderId)
        logger.info('Watch folder deleted:', folderId)
        return true
      } else {
        error.value = response.message || 'Failed to delete watch folder'
        return false
      }
    } catch (err) {
      logger.error('Error deleting watch folder:', err)
      error.value = err instanceof Error ? err.message : 'Unknown error'
      return false
    } finally {
      loading.value = false
    }
  }

  /**
   * Enable or disable a watch folder
   */
  async function controlWatchFolder(folderId: string, action: 'enable' | 'disable') {
    loading.value = true
    error.value = null

    try {
      const response = await api.patch<{
        success: boolean
        message?: string
      }>(`/api/knowledge_base/watch-folders/${folderId}/control`, { action })

      if (response.success) {
        // Update local state
        const folder = watchFolders.value.find(f => f.folder_id === folderId)
        if (folder) {
          folder.enabled = action === 'enable'
          folder.is_watching = action === 'enable'
        }
        logger.info('Watch folder control:', folderId, action)
        return true
      } else {
        error.value = response.message || `Failed to ${action} watch folder`
        return false
      }
    } catch (err) {
      logger.error(`Error ${action} watch folder:`, err)
      error.value = err instanceof Error ? err.message : 'Unknown error'
      return false
    } finally {
      loading.value = false
    }
  }

  /**
   * Enable a watch folder
   */
  async function enableWatchFolder(folderId: string) {
    return controlWatchFolder(folderId, 'enable')
  }

  /**
   * Disable a watch folder
   */
  async function disableWatchFolder(folderId: string) {
    return controlWatchFolder(folderId, 'disable')
  }

  /**
   * Load watch folder statistics
   */
  async function loadStats() {
    loading.value = true
    error.value = null

    try {
      const response = await api.get<{
        success: boolean
        stats: WatchFolderStats
      }>('/api/knowledge_base/watch-folders/stats')

      if (response.success) {
        stats.value = response.stats
      } else {
        error.value = 'Failed to load watch folder stats'
      }
    } catch (err) {
      logger.error('Error loading watch folder stats:', err)
      error.value = err instanceof Error ? err.message : 'Unknown error'
      stats.value = null
    } finally {
      loading.value = false
    }
  }

  return {
    watchFolders,
    stats,
    loading,
    error,
    activeCount,
    totalIngested,
    loadWatchFolders,
    createWatchFolder,
    deleteWatchFolder,
    enableWatchFolder,
    disableWatchFolder,
    loadStats,
  }
}
