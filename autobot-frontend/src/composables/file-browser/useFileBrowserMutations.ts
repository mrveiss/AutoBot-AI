// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #22349: the Files tab's upload, delete, rename and create-folder actions, split out of useFileBrowserActions.
import type { Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useToast } from '@/composables/useToast'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useAsyncHandler } from '@/composables/useErrorHandler'
import type { FileBrowserItem } from '@/composables/file-browser/useFileBrowser'
import { ERROR_OPTS, type FileBrowser, type FileLog } from '@/composables/file-browser/useFileBrowserNavigation'

type UploadOutcome = Awaited<ReturnType<FileBrowser['uploadFiles']>>
interface Where { currentPath: Ref<string>, refreshFiles: () => Promise<unknown> }

/** #22015: each refused file is named with the server's reason, never a bare status. */
export function uploadFailureText(outcome: UploadOutcome, fallback: string): string {
  return outcome ? outcome.failed.map(f => `${f.name}: ${f.reason}`).join('; ') : fallback
}

export function logUploaded(outcome: NonNullable<UploadOutcome>, fileList: FileList, path: string, log: FileLog): void {
  const stored = Array.from(fileList).filter(f => outcome.uploaded.includes(f.name))
  log('upload', path, {
    fileNames: outcome.uploaded.join(', '), fileCount: stored.length,
    totalSize: stored.reduce((sum, f) => sum + f.size, 0),
  })
}

function useUpload(browser: FileBrowser, log: FileLog, where: Where) {
  const { t } = useI18n()
  const { showToast } = useToast()
  const { execute } = useAsyncHandler(async (fileList: FileList) => {
    const outcome = await browser.uploadFiles(fileList, where.currentPath.value)
    await where.refreshFiles()
    const reasons = uploadFailureText(outcome, t('fileBrowser.browser.uploadFailedHint'))
    if (reasons) showToast(t('fileBrowser.browser.uploadFailed', { error: reasons }), 'error')
    if (outcome?.uploaded.length) logUploaded(outcome, fileList, where.currentPath.value, log)
  }, ERROR_OPTS)
  return execute
}

function useDelete(browser: FileBrowser, log: FileLog, where: Where) {
  const { t } = useI18n()
  const { showToast } = useToast()
  const { confirm } = useConfirmDialog()
  const { execute: performDelete } = useAsyncHandler(async (file: FileBrowserItem) => {
    const itemType = file.is_dir ? 'folder' : 'file'
    await browser.deleteFileOrFolder(file.path)
    await where.refreshFiles()
    log('delete', file.path, { fileName: file.name, isDir: file.is_dir, itemType })
    return itemType
  }, { ...ERROR_OPTS, onError: () => { showToast(t('fileBrowser.browser.errorDeletingFile'), 'error') } })

  return async (file: FileBrowserItem) => {
    const message = t('fileBrowser.browser.deleteConfirm', { name: file.name })
    if (await confirm({ title: t('common.confirm'), message })) await performDelete(file)
  }
}

function useRename(browser: FileBrowser, log: FileLog, where: Where) {
  const { t } = useI18n()
  const { showToast } = useToast()
  const { execute: performRename } = useAsyncHandler(async (file: FileBrowserItem, newName: string) => {
    await browser.renameFileOrFolder(file.path, newName)
    await where.refreshFiles()
    log('rename', file.path, { oldName: file.name, newName, isDir: file.is_dir })
  }, { ...ERROR_OPTS, onError: () => { showToast(t('fileBrowser.browser.errorRenamingFile'), 'error') } })

  return async (file: FileBrowserItem) => {
    const newName = prompt(t('fileBrowser.browser.renamePrompt'), file.name)
    if (newName && newName !== file.name) await performRename(file, newName)
  }
}

function useCreateFolder(browser: FileBrowser, log: FileLog, where: Where) {
  const { t } = useI18n()
  const { showToast } = useToast()
  const { execute: performCreateFolder } = useAsyncHandler(async (folderName: string) => {
    const parent = where.currentPath.value
    await browser.createDirectory(parent, folderName)
    await where.refreshFiles()
    log('create_folder', `${parent}/${folderName}`, { folderName, parentPath: parent })
  }, { ...ERROR_OPTS, onError: () => { showToast(t('fileBrowser.browser.errorCreatingFolder'), 'error') } })

  return async () => {
    const folderName = prompt(t('fileBrowser.browser.createFolderPrompt'))
    if (folderName) await performCreateFolder(folderName)
  }
}

export function useFileBrowserMutations(browser: FileBrowser, log: FileLog, where: Where) {
  return {
    uploadFiles: useUpload(browser, log, where),
    deleteFile: useDelete(browser, log, where),
    renameFile: useRename(browser, log, where),
    createNewFolder: useCreateFolder(browser, log, where),
  }
}
