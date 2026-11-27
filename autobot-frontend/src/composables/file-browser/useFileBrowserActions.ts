// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #22349: the Files tab's UI state and action handlers, moved out of FileBrowser.vue so the component is a template.
// It calls `useFileBrowser` exactly as the component did (same arguments, same toast keys, same activity log
// entries when `chatContext` is set); nothing in the data path changed.
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { saveUrl } from '@autobot/ui'
import { useToast } from '@/composables/useToast'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useAsyncHandler } from '@/composables/useErrorHandler'
import { useSessionActivityLogger, type FileActivitySubtype } from '@/composables/useSessionActivityLogger'
import { useFileBrowser } from '@/composables/file-browser/useFileBrowser'
import type { FileBrowserItem, FileBrowserTreeNode, FilePreviewData } from '@/composables/file-browser/useFileBrowser'
import { getFileType } from '@/utils/fileTypeLabel'

// The FilePreview @download payload carries an optional `fileType`, so only the fields read here are required.
type PreviewDownloadFile = Pick<FilePreviewData, 'name' | 'url'>
type SortOrder = 'asc' | 'desc'
const ERROR_OPTS = { logErrors: true, errorPrefix: '[FileBrowser]' }

function sortValue(file: FileBrowserItem, field: string): string | number {
  if (field === 'size') return file.size || 0
  if (field === 'modified') return new Date(file.last_modified || 0).getTime()
  if (field === 'type') return file.is_dir ? 'Directory' : getFileType(file.name)
  return file.name
}

/** Directories first, then the chosen field in the chosen order. */
export function sortFileItems(files: FileBrowserItem[], field: string, order: SortOrder): FileBrowserItem[] {
  const sign = order === 'asc' ? 1 : -1
  return [...files].sort((a, b) => {
    if (a.is_dir && !b.is_dir) return -1
    if (!a.is_dir && b.is_dir) return 1
    const av = sortValue(a, field)
    const bv = sortValue(b, field)
    return av < bv ? -sign : av > bv ? sign : 0
  })
}

function setExpanded(nodes: FileBrowserTreeNode[], expanded: boolean): void {
  nodes.forEach((node) => {
    if (!node.is_dir) return
    node.expanded = expanded
    if (node.children) setExpanded(node.children, expanded)
  })
}

export function useFileBrowserActions(options: { chatContext: boolean }) {
  const { t } = useI18n()
  const { showToast } = useToast()
  const { confirm } = useConfirmDialog()
  // Issue #608: Activity logger for session tracking
  const { logFileActivity } = useSessionActivityLogger()
  const browser = useFileBrowser()
  const { files, directoryTree, previewFile } = browser

  const currentPath = ref('/')
  const selectedPath = ref('')
  const viewMode = ref<'tree' | 'list'>('list')
  const sortField = ref('name')
  const sortOrder = ref<SortOrder>('asc')
  const showPreview = ref(false)
  const sortedFiles = computed(() => sortFileItems(files.value, sortField.value, sortOrder.value))

  /** Issue #608: log only inside a chat. */
  const log = (action: FileActivitySubtype, path: string, details: Record<string, unknown>) => {
    if (options.chatContext) logFileActivity(action, path, details)
  }

  const { execute: loadDirectoryTree } = useAsyncHandler(async () => { await browser.fetchTree() }, ERROR_OPTS)
  const { execute: refreshFiles } = useAsyncHandler(async () => {
    await browser.fetchFiles(currentPath.value)
    if (viewMode.value === 'tree') await loadDirectoryTree()
  }, ERROR_OPTS)

  const navigateToPath = (path: string) => {
    const previousPath = currentPath.value
    currentPath.value = path
    selectedPath.value = path
    refreshFiles()
    log('navigate', path, { fromPath: previousPath, toPath: path })
  }

  const toggleView = () => {
    viewMode.value = viewMode.value === 'tree' ? 'list' : 'tree'
    if (viewMode.value === 'tree') loadDirectoryTree()
  }

  const sortBy = (field: string) => {
    if (sortField.value === field) {
      sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
    } else {
      sortField.value = field
      sortOrder.value = 'asc'
    }
  }

  const { execute: uploadFiles } = useAsyncHandler(async (fileList: FileList) => {
    const outcome = await browser.uploadFiles(fileList, currentPath.value)
    await refreshFiles()
    // #22015: each refused file is named with the server's reason, never a bare status.
    const reasons = outcome
      ? outcome.failed.map(f => `${f.name}: ${f.reason}`).join('; ')
      : t('fileBrowser.browser.uploadFailedHint')
    if (reasons) showToast(t('fileBrowser.browser.uploadFailed', { error: reasons }), 'error')
    if (outcome?.uploaded.length) {
      const stored = Array.from(fileList).filter(f => outcome.uploaded.includes(f.name))
      log('upload', currentPath.value, {
        fileNames: outcome.uploaded.join(', '), fileCount: stored.length,
        totalSize: stored.reduce((sum, f) => sum + f.size, 0),
      })
    }
  }, ERROR_OPTS)

  const { execute: viewFile } = useAsyncHandler(async (file: FileBrowserItem) => {
    await browser.fetchPreview(file, getFileType)
    showPreview.value = true
    log('view', file.path, { fileName: file.name, fileType: getFileType(file.name), size: file.size })
  }, ERROR_OPTS)

  const { execute: performDelete } = useAsyncHandler(async (file: FileBrowserItem) => {
    const itemType = file.is_dir ? 'folder' : 'file'
    await browser.deleteFileOrFolder(file.path)
    await refreshFiles()
    log('delete', file.path, { fileName: file.name, isDir: file.is_dir, itemType })
    return itemType
  }, { ...ERROR_OPTS, onError: () => { showToast(t('fileBrowser.browser.errorDeletingFile'), 'error') } })

  const deleteFile = async (file: FileBrowserItem) => {
    const message = t('fileBrowser.browser.deleteConfirm', { name: file.name })
    if (await confirm({ title: t('common.confirm'), message })) await performDelete(file)
  }

  const { execute: performRename } = useAsyncHandler(async (file: FileBrowserItem, newName: string) => {
    await browser.renameFileOrFolder(file.path, newName)
    await refreshFiles()
    log('rename', file.path, { oldName: file.name, newName, isDir: file.is_dir })
  }, { ...ERROR_OPTS, onError: () => { showToast(t('fileBrowser.browser.errorRenamingFile'), 'error') } })

  const renameFile = async (file: FileBrowserItem) => {
    const newName = prompt(t('fileBrowser.browser.renamePrompt'), file.name)
    if (newName && newName !== file.name) await performRename(file, newName)
  }

  const { execute: performCreateFolder } = useAsyncHandler(async (folderName: string) => {
    await browser.createDirectory(currentPath.value, folderName)
    await refreshFiles()
    log('create_folder', `${currentPath.value}/${folderName}`, { folderName, parentPath: currentPath.value })
  }, { ...ERROR_OPTS, onError: () => { showToast(t('fileBrowser.browser.errorCreatingFolder'), 'error') } })

  const createNewFolder = async () => {
    const folderName = prompt(t('fileBrowser.browser.createFolderPrompt'))
    if (folderName) await performCreateFolder(folderName)
  }

  const closePreview = () => {
    showPreview.value = false
    previewFile.value = null
  }

  const downloadPreviewFile = (file: PreviewDownloadFile) => {
    if (file.url) saveUrl(file.url, file.name)
  }

  const toggleNode = (item: FileBrowserTreeNode) => {
    if (!item.is_dir) return
    item.expanded = !item.expanded
    selectedPath.value = item.path
    navigateToPath(item.path)
  }

  return {
    files, directoryTree, previewFile, currentPath, selectedPath, viewMode, sortField, sortOrder, showPreview,
    sortedFiles, refreshFiles, navigateToPath, toggleView, sortBy, uploadFiles, viewFile, deleteFile, renameFile,
    createNewFolder, closePreview, downloadPreviewFile, toggleNode,
    expandAll: () => setExpanded(directoryTree.value, true),
    collapseAll: () => setExpanded(directoryTree.value, false),
  }
}
