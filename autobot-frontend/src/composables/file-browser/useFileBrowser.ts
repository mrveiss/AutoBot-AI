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
import { HttpError } from '@autobot/ui'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { useAsyncHandler } from '@/composables/useErrorHandler'
import { extractResponseErrorDetail } from '@/utils/errorExtract'
import i18n from '@/i18n'

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

/** Form fields of POST /files/upload; the contract test pins these against the route signature (#22015). */
export const UPLOAD_FORM_FIELDS = { file: 'file', path: 'path', overwrite: 'overwrite' } as const

export interface UploadOutcome {
  uploaded: string[]
  failed: Array<{ name: string; reason: string }>
}

/** Upload one file; null on success, else the reason it failed (the server's client-safe `detail`, or a hint). */
async function uploadOne(file: File, path: string, overwrite: boolean): Promise<string | null> {
  const formData = new FormData()
  formData.append(UPLOAD_FORM_FIELDS.file, file)
  formData.append(UPLOAD_FORM_FIELDS.path, path)
  formData.append(UPLOAD_FORM_FIELDS.overwrite, String(overwrite))
  try {
    const response = await fetchWithAuth(`${getApiBase()}/files/upload`, { // fetchWithAuth retained: FormData body — exempt from Wave 5 (#6224)
      method: 'POST',
      body: formData,
    })
    if (response.ok) return null
    // 409: the API's text says to send overwrite=true, which this UI cannot do.
    if (response.status === 409) return i18n.global.t('fileBrowser.browser.uploadAlreadyExists')
    return (await extractResponseErrorDetail(response)) || i18n.global.t('fileBrowser.browser.uploadFailedHint')
  } catch {
    return i18n.global.t('fileBrowser.browser.uploadFailedHint')
  }
}

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
  // The route takes ONE file per request (form field `file`, plus `path` and `overwrite`), so a
  // selection of N files is N requests. Each file is judged by the route's own validation; a refused
  // file is reported with the server's reason and never stops the others (#22015).
  const { execute: uploadFiles, loading: isUploadingFiles } = useAsyncHandler(
    async (fileList: FileList, path: string, overwrite = false): Promise<UploadOutcome> => {
      const outcome: UploadOutcome = { uploaded: [], failed: [] }
      for (const file of Array.from(fileList)) {
        const reason = await uploadOne(file, path, overwrite)
        if (reason === null) outcome.uploaded.push(file.name)
        else outcome.failed.push({ name: file.name, reason })
      }
      return outcome
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
      if (!response.ok) throw new HttpError(response.status, response.statusText)
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
      if (!response.ok) throw new HttpError(response.status, response.statusText)
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
