// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #22349: the Files tab's preview pane, split out of useFileBrowserActions.
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { saveUrl } from '@autobot/ui'
import { useAsyncHandler } from '@/composables/useErrorHandler'
import type { FilePreviewData, FileBrowserItem } from '@/composables/file-browser/useFileBrowser'
import { getFileType } from '@/utils/fileTypeLabel'
import { ERROR_OPTS, type FileBrowser, type FileLog } from '@/composables/file-browser/useFileBrowserNavigation'

// The FilePreview @download payload carries an optional `fileType`, so only the fields read here are required.
type PreviewDownloadFile = Pick<FilePreviewData, 'name' | 'url'>

export function useFileBrowserPreview(browser: FileBrowser, log: FileLog) {
  const { t } = useI18n()
  const showPreview = ref(false)
  const typeOf = (name: string) => getFileType(name, t)

  const { execute: viewFile } = useAsyncHandler(async (file: FileBrowserItem) => {
    await browser.fetchPreview(file, typeOf)
    showPreview.value = true
    log('view', file.path, { fileName: file.name, fileType: typeOf(file.name), size: file.size })
  }, ERROR_OPTS)

  const closePreview = () => {
    showPreview.value = false
    browser.previewFile.value = null
  }
  const downloadPreviewFile = (file: PreviewDownloadFile) => {
    if (file.url) saveUrl(file.url, file.name)
  }

  return { showPreview, viewFile, closePreview, downloadPreviewFile }
}
