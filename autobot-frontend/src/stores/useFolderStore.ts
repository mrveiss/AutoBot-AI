// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// GH#8987: Pinia store for conversation folder management.

import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useFolderStore')

const FOLDERS_ENDPOINT = '/api/chat/folders'

export interface ChatFolder {
  id: string
  name: string
  parent_id: string | null
  owner: string
  pinned: boolean
  created_at: string
  session_ids: string[]
  session_count: number
}

export interface FolderCreate {
  name: string
  parent_id?: string | null
}

export interface FolderUpdate {
  name?: string
  parent_id?: string | null
  pinned?: boolean
}

export const useFolderStore = defineStore('chatFolders', () => {
  const folders = ref<ChatFolder[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  // Folders that have no parent (root level)
  const rootFolders = computed(() =>
    folders.value.filter((f) => !f.parent_id).sort((a, b) => {
      if (a.pinned !== b.pinned) return a.pinned ? -1 : 1
      return a.name.localeCompare(b.name)
    })
  )

  function childrenOf(parentId: string): ChatFolder[] {
    return folders.value
      .filter((f) => f.parent_id === parentId)
      .sort((a, b) => a.name.localeCompare(b.name))
  }

  function folderForSession(sessionId: string): ChatFolder | undefined {
    return folders.value.find((f) => f.session_ids.includes(sessionId))
  }

  async function fetchFolders(): Promise<void> {
    const api = useApiClient()
    isLoading.value = true
    error.value = null
    try {
      // Backend returns plain JSON: { folders: ChatFolder[], count: number }
      const resp = await api.get<{ folders: ChatFolder[]; count: number }>(FOLDERS_ENDPOINT)
      folders.value = resp?.folders ?? []
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to load folders'
      logger.error('[useFolderStore] fetchFolders failed:', err)
    } finally {
      isLoading.value = false
    }
  }

  async function createFolder(payload: FolderCreate): Promise<ChatFolder | null> {
    const api = useApiClient()
    try {
      const created = await api.post<ChatFolder>(FOLDERS_ENDPOINT, payload)
      folders.value.push(created)
      return created
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to create folder'
      logger.error('[useFolderStore] createFolder failed:', err)
      return null
    }
  }

  async function updateFolder(id: string, payload: FolderUpdate): Promise<ChatFolder | null> {
    const api = useApiClient()
    try {
      const updated = await api.put<ChatFolder>(`${FOLDERS_ENDPOINT}/${id}`, payload)
      const idx = folders.value.findIndex((f) => f.id === id)
      if (idx !== -1) folders.value[idx] = updated
      return updated
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to update folder'
      logger.error('[useFolderStore] updateFolder failed:', err)
      return null
    }
  }

  async function deleteFolder(id: string): Promise<boolean> {
    const api = useApiClient()
    try {
      await api.delete(`${FOLDERS_ENDPOINT}/${id}`)
      // Re-parent children locally to mirror server behaviour
      const toDelete = folders.value.find((f) => f.id === id)
      folders.value.forEach((f) => {
        if (f.parent_id === id) f.parent_id = toDelete?.parent_id ?? null
      })
      folders.value = folders.value.filter((f) => f.id !== id)
      return true
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to delete folder'
      logger.error('[useFolderStore] deleteFolder failed:', err)
      return false
    }
  }

  async function assignSessionToFolder(sessionId: string, folderId: string | null): Promise<boolean> {
    const api = useApiClient()
    try {
      await api.put(`/api/chat/sessions/${sessionId}/folder`, { folder_id: folderId })
      // Update local state
      folders.value.forEach((f) => {
        const idx = f.session_ids.indexOf(sessionId)
        if (idx !== -1) {
          f.session_ids.splice(idx, 1)
          f.session_count = f.session_ids.length
        }
      })
      if (folderId) {
        const target = folders.value.find((f) => f.id === folderId)
        if (target && !target.session_ids.includes(sessionId)) {
          target.session_ids.push(sessionId)
          target.session_count = target.session_ids.length
        }
      }
      return true
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to assign session to folder'
      logger.error('[useFolderStore] assignSessionToFolder failed:', err)
      return false
    }
  }

  async function togglePin(id: string): Promise<void> {
    const folder = folders.value.find((f) => f.id === id)
    if (!folder) return
    await updateFolder(id, { pinned: !folder.pinned })
  }

  return {
    folders,
    rootFolders,
    isLoading,
    error,
    childrenOf,
    folderForSession,
    fetchFolders,
    createFolder,
    updateFolder,
    deleteFolder,
    assignSessionToFolder,
    togglePin,
  }
})
