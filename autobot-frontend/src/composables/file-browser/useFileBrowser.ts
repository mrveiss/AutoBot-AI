// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * useFileBrowser Composable
 *
 * Encapsulates all API interactions for the FileBrowser component.
 * Extracted from FileBrowser.vue (#6075) to separate data-fetching from presentation.
 */

import { ref } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { useAsyncHandler } from '@/composables/useErrorHandler'

// ==================== Types ====================

export interface FileBrowserItem {
  name: string
  path: string
  size?: number
  last_modified?: string
  is_dir?: boolean
}

export interface FilePreviewData {
  name: string
  type: string
  url?: string
  content?: string
  fileType: string
  size?: number
}

export interface FileBrowserTreeNode {
  name: string
  path: string
  is_dir?: boolean
  expanded?: boolean
  children?: FileBrowserTreeNode[]
}

// ==================== Composable ====================

export function useFileBrowser() {
  const files = ref<FileBrowserItem[]>([])
  const directoryTree = ref<FileBrowserTreeNode[]>([])
  const previewFile = ref<FilePreviewData | null>(null)

  // ---- GET /files/list ----
  const { execute: fetchFiles, loading: isLoadingFiles } = useAsyncHandler(
    async (path: string) => {
      const data = await apiClient.get<{ files?: FileBrowserItem[] }>(
        `${getApiBase()}/files/list?path=${encodeURIComponent(path)}`
      )
      files.value = data.files ?? []
    },
    {
      onError: () => { files.value = [] },
      logErrors: true,
      errorPrefix: '[useFileBrowser]'
    }
  )

  // ---- GET /files/tree ----
  const { execute: fetchTree, loading: isLoadingTree } = useAsyncHandler(
    async () => {
      const data = await apiClient.get<{ tree?: FileBrowserTreeNode[] }>(`${getApiBase()}/files/tree`)
      directoryTree.value = data.tree ?? []
    },
    {
      onError: () => { directoryTree.value = [] },
      logErrors: true,
      errorPrefix: '[useFileBrowser]'
    }
  )

  // ---- POST /files/upload ----
  const { execute: uploadFiles, loading: isUploadingFiles } = useAsyncHandler(
    async (fileList: FileList, path: string) => {
      const formData = new FormData()
      Array.from(fileList).forEach((file) => { formData.append('files', file) })
      formData.append('path', path)
      const response = await fetchWithAuth(`${getApiBase()}/files/upload`, { // fetchWithAuth retained: FormData body — exempt from Wave 5 (#6224)
        method: 'POST',
        body: formData,
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    },
    {
      logErrors: true,
      errorPrefix: '[useFileBrowser]'
    }
  )

  // ---- GET /files/preview ----
  const { execute: fetchPreview, loading: isLoadingPreview } = useAsyncHandler(
    async (file: FileBrowserItem, getFileType: (name: string) => string) => {
      const data = await apiClient.get<{ type?: string; url?: string; content?: string }>(
        `${getApiBase()}/files/preview?path=${encodeURIComponent(file.path)}`
      )
      previewFile.value = {
        name: file.name,
        type: data.type ?? '',
        url: data.url,
        content: data.content,
        fileType: getFileType(file.name),
        size: file.size
      }
    },
    {
      logErrors: true,
      errorPrefix: '[useFileBrowser]'
    }
  )

  // ---- DELETE /files/delete ----
  const { execute: deleteFileOrFolder, loading: isDeletingFile } = useAsyncHandler(
    async (path: string) => {
      await apiClient.delete<unknown>(`${getApiBase()}/files/delete?path=${encodeURIComponent(path)}`)
    },
    {
      logErrors: true,
      errorPrefix: '[useFileBrowser]'
    }
  )

  // ---- POST /files/rename ----
  const { execute: renameFileOrFolder, loading: isRenamingFile } = useAsyncHandler(
    async (path: string, newName: string) => {
      const formData = new FormData()
      formData.append('path', path)
      formData.append('new_name', newName)
      const response = await fetchWithAuth(`${getApiBase()}/files/rename`, { // fetchWithAuth retained: FormData body — exempt from Wave 5 (#6224)
        method: 'POST',
        body: formData,
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    },
    {
      logErrors: true,
      errorPrefix: '[useFileBrowser]'
    }
  )

  // ---- POST /files/create_directory ----
  const { execute: createDirectory, loading: isCreatingDirectory } = useAsyncHandler(
    async (parentPath: string, name: string) => {
      const formData = new FormData()
      formData.append('path', parentPath)
      formData.append('name', name)
      const response = await fetchWithAuth(`${getApiBase()}/files/create_directory`, { // fetchWithAuth retained: FormData body — exempt from Wave 5 (#6224)
        method: 'POST',
        body: formData,
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    },
    {
      logErrors: true,
      errorPrefix: '[useFileBrowser]'
    }
  )

  return {
    // State
    files,
    directoryTree,
    previewFile,

    // Loading flags
    isLoadingFiles,
    isLoadingTree,
    isUploadingFiles,
    isLoadingPreview,
    isDeletingFile,
    isRenamingFile,
    isCreatingDirectory,

    // Actions
    fetchFiles,
    fetchTree,
    uploadFiles,
    fetchPreview,
    deleteFileOrFolder,
    renameFileOrFolder,
    createDirectory
  }
}
