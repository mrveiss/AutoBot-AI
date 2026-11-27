// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #22349: the Files tab's UI state and action handlers, moved out of FileBrowser.vue so the component is a template.
// It calls `useFileBrowser` exactly as the component did (same arguments, same toast keys, same activity log
// entries when `chatContext` is set); nothing in the data path changed. The pieces live in the sibling
// useFileBrowserSort / Navigation / Mutations / Preview composables; this one only composes them.
import { useSessionActivityLogger } from '@/composables/useSessionActivityLogger'
import { useFileBrowser } from '@/composables/file-browser/useFileBrowser'
import { useFileBrowserSort } from '@/composables/file-browser/useFileBrowserSort'
import { useFileBrowserNavigation, type FileLog } from '@/composables/file-browser/useFileBrowserNavigation'
import { useFileBrowserMutations } from '@/composables/file-browser/useFileBrowserMutations'
import { useFileBrowserPreview } from '@/composables/file-browser/useFileBrowserPreview'

export { sortFileItems } from '@/composables/file-browser/useFileBrowserSort'

export function useFileBrowserActions(options: { chatContext: boolean }) {
  // Issue #608: Activity logger for session tracking
  const { logFileActivity } = useSessionActivityLogger()
  const browser = useFileBrowser()
  const log: FileLog = (action, path, details) => {
    if (options.chatContext) logFileActivity(action, path, details)
  }
  const sort = useFileBrowserSort(browser.files)
  const nav = useFileBrowserNavigation(browser, log)
  const mutations = useFileBrowserMutations(browser, log, nav)
  const preview = useFileBrowserPreview(browser, log)
  const { files, directoryTree, previewFile } = browser

  return { files, directoryTree, previewFile, ...sort, ...nav, ...mutations, ...preview }
}
