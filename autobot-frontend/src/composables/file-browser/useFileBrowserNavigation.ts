// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #22349: the Files tab's location, view mode and tree handling, split out of useFileBrowserActions.
import { ref, type Ref } from 'vue'
import { useAsyncHandler } from '@/composables/useErrorHandler'
import type { FileActivitySubtype } from '@/composables/useSessionActivityLogger'
import type { FileBrowserTreeNode, useFileBrowser } from '@/composables/file-browser/useFileBrowser'

export type FileBrowser = ReturnType<typeof useFileBrowser>
/** Issue #608: logs a file activity, only inside a chat. */
export type FileLog = (action: FileActivitySubtype, path: string, details: Record<string, unknown>) => void
export const ERROR_OPTS = { logErrors: true, errorPrefix: '[FileBrowser]' }

function setExpanded(nodes: FileBrowserTreeNode[], expanded: boolean): void {
  nodes.forEach((node) => {
    if (!node.is_dir) return
    node.expanded = expanded
    if (node.children) setExpanded(node.children, expanded)
  })
}

function useRefresh(browser: FileBrowser, currentPath: Ref<string>, viewMode: Ref<'tree' | 'list'>) {
  const { execute: loadDirectoryTree } = useAsyncHandler(async () => { await browser.fetchTree() }, ERROR_OPTS)
  const { execute: refreshFiles } = useAsyncHandler(async () => {
    await browser.fetchFiles(currentPath.value)
    if (viewMode.value === 'tree') await loadDirectoryTree()
  }, ERROR_OPTS)
  return { loadDirectoryTree, refreshFiles }
}

export function useFileBrowserNavigation(browser: FileBrowser, log: FileLog) {
  const currentPath = ref('/')
  const selectedPath = ref('')
  const viewMode = ref<'tree' | 'list'>('list')
  const { loadDirectoryTree, refreshFiles } = useRefresh(browser, currentPath, viewMode)

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
  const toggleNode = (item: FileBrowserTreeNode) => {
    if (!item.is_dir) return
    item.expanded = !item.expanded
    selectedPath.value = item.path
    navigateToPath(item.path)
  }
  const expandAll = () => setExpanded(browser.directoryTree.value, true)
  const collapseAll = () => setExpanded(browser.directoryTree.value, false)

  return {
    currentPath, selectedPath, viewMode, refreshFiles, navigateToPath, toggleView, toggleNode, expandAll, collapseAll,
  }
}
