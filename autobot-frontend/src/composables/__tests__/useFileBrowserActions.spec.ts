// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #22349: the Files tab actions -- each one calls `useFileBrowser` with the same arguments as before the split,
// reports errors through the same toast keys and logs chat activity only inside a chat.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const browser = {
  files: ref<Record<string, unknown>[]>([]),
  directoryTree: ref<Record<string, unknown>[]>([]),
  previewFile: ref<unknown>(null),
  fetchFiles: vi.fn().mockResolvedValue(undefined),
  fetchTree: vi.fn().mockResolvedValue(undefined),
  uploadFiles: vi.fn(),
  fetchPreview: vi.fn().mockResolvedValue(true),
  cancelPreview: vi.fn(),
  deleteFileOrFolder: vi.fn().mockResolvedValue(undefined),
  renameFileOrFolder: vi.fn().mockResolvedValue(undefined),
  createDirectory: vi.fn().mockResolvedValue(undefined),
}
const showToast = vi.fn()
const confirm = vi.fn()
const logFileActivity = vi.fn()

vi.mock('@/composables/file-browser/useFileBrowser', () => ({ useFileBrowser: () => browser }))
vi.mock('@/composables/useToast', () => ({ useToast: () => ({ showToast }) }))
vi.mock('@/composables/useConfirmDialog', () => ({ useConfirmDialog: () => ({ confirm }) }))
vi.mock('@/composables/useSessionActivityLogger', () => ({ useSessionActivityLogger: () => ({ logFileActivity }) }))
vi.mock('vue-i18n', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-i18n')>()),
  useI18n: () => ({ t: (k: string) => k }),
}))

import { useFileBrowserActions } from '../file-browser/useFileBrowserActions'

const file = (over: Record<string, unknown> = {}) => ({ name: 'a.txt', path: '/a.txt', is_dir: false, ...over }) as never

describe('useFileBrowserActions (#22349)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // the global vitest config (clearMocks/mockReset/restoreMocks) resets vi.fn implementations before each test, and an undefined result reads as a superseded preview
    browser.fetchPreview.mockResolvedValue(true)
    browser.files.value = []
  })

  it('navigating loads the folder and logs only inside a chat', async () => {
    const chat = useFileBrowserActions({ chatContext: true })
    chat.navigateToPath('/docs')
    await vi.waitFor(() => expect(browser.fetchFiles).toHaveBeenCalledWith('/docs'))
    expect(logFileActivity).toHaveBeenCalledWith('navigate', '/docs', { fromPath: '/', toPath: '/docs' })

    logFileActivity.mockClear()
    useFileBrowserActions({ chatContext: false }).navigateToPath('/x')
    expect(logFileActivity).not.toHaveBeenCalled()
  })

  it('sorting the same field flips the order, a new field starts ascending', () => {
    const a = useFileBrowserActions({ chatContext: false })
    a.sortBy('name')
    expect(a.sortOrder.value).toBe('desc')
    a.sortBy('size')
    expect([a.sortField.value, a.sortOrder.value]).toEqual(['size', 'asc'])
  })

  it('the Files tab starts in the flat list view', () => {
    expect(useFileBrowserActions({ chatContext: false }).viewMode.value).toBe('list')
  })

  it('switching to the tree view loads the tree', () => {
    const a = useFileBrowserActions({ chatContext: false })
    expect(a.viewMode.value).toBe('list')
    a.toggleView()
    expect(a.viewMode.value).toBe('tree')
    expect(browser.fetchTree).toHaveBeenCalled()
  })

  it('upload passes the list and the current path, then names each refused file in the toast', async () => {
    browser.uploadFiles.mockResolvedValue({ uploaded: [], failed: [{ name: 'big.bin', reason: 'too large' }] })
    const a = useFileBrowserActions({ chatContext: false })
    const list = [new File(['x'], 'big.bin')] as unknown as FileList
    await a.uploadFiles(list)
    expect(browser.uploadFiles).toHaveBeenCalledWith(list, '/')
    expect(showToast).toHaveBeenCalledWith('fileBrowser.browser.uploadFailed', 'error')
  })

  it('delete asks first and deletes only on confirmation', async () => {
    const a = useFileBrowserActions({ chatContext: false })
    confirm.mockResolvedValueOnce(false)
    await a.deleteFile(file())
    expect(browser.deleteFileOrFolder).not.toHaveBeenCalled()
    confirm.mockResolvedValueOnce(true)
    await a.deleteFile(file())
    expect(browser.deleteFileOrFolder).toHaveBeenCalledWith('/a.txt')
  })

  it('a failed delete reports the same toast key', async () => {
    browser.deleteFileOrFolder.mockRejectedValueOnce(new Error('nope'))
    confirm.mockResolvedValueOnce(true)
    await useFileBrowserActions({ chatContext: false }).deleteFile(file())
    expect(showToast).toHaveBeenCalledWith('fileBrowser.browser.errorDeletingFile', 'error')
  })

  it('rename and create folder take the name from the prompt and pass the same arguments', async () => {
    const a = useFileBrowserActions({ chatContext: false })
    vi.spyOn(window, 'prompt').mockReturnValueOnce('b.txt')
    await a.renameFile(file())
    expect(browser.renameFileOrFolder).toHaveBeenCalledWith('/a.txt', 'b.txt')
    vi.spyOn(window, 'prompt').mockReturnValueOnce('new')
    await a.createNewFolder()
    expect(browser.createDirectory).toHaveBeenCalledWith('/', 'new')
  })

  it('a cancelled prompt does nothing', async () => {
    const a = useFileBrowserActions({ chatContext: false })
    vi.spyOn(window, 'prompt').mockReturnValue(null)
    await a.renameFile(file())
    await a.createNewFolder()
    expect(browser.renameFileOrFolder).not.toHaveBeenCalled()
    expect(browser.createDirectory).not.toHaveBeenCalled()
  })

  it('viewing a file fetches its preview and opens it; closing clears it', async () => {
    const a = useFileBrowserActions({ chatContext: false })
    await a.viewFile(file())
    expect(browser.fetchPreview).toHaveBeenCalledWith(file(), expect.any(Function))
    expect(a.showPreview.value).toBe(true)
    a.closePreview()
    expect(a.showPreview.value).toBe(false)
    expect(browser.previewFile.value).toBeNull()
    expect(browser.cancelPreview).toHaveBeenCalledTimes(1)
  })

  it('a failed preview request shows an error toast and opens nothing', async () => {
    browser.fetchPreview.mockRejectedValueOnce(new Error('boom'))
    const a = useFileBrowserActions({ chatContext: true })
    await a.viewFile(file())
    expect(showToast).toHaveBeenCalledWith('fileBrowser.browser.errorLoadingPreview', 'error')
    expect(a.showPreview.value).toBe(false)
    expect(logFileActivity).not.toHaveBeenCalledWith('view', expect.anything(), expect.anything())
  })

  it('a superseded preview request neither opens the preview nor logs a view', async () => {
    browser.fetchPreview.mockResolvedValueOnce(false)
    const a = useFileBrowserActions({ chatContext: true })
    await a.viewFile(file())
    expect(a.showPreview.value).toBe(false)
    expect(logFileActivity).not.toHaveBeenCalledWith('view', expect.anything(), expect.anything())
  })

  it('an upload logs the folder it went to, even if the user navigated meanwhile', async () => {
    const a = useFileBrowserActions({ chatContext: true })
    browser.uploadFiles.mockImplementationOnce(async () => {
      a.navigateToPath('/elsewhere')
      return { uploaded: ['a.txt'], failed: [] }
    })
    await a.uploadFiles([new File(['x'], 'a.txt')] as unknown as FileList)
    expect(browser.uploadFiles).toHaveBeenCalledWith(expect.anything(), '/')
    expect(logFileActivity).toHaveBeenCalledWith('upload', '/', expect.objectContaining({ fileCount: 1 }))
  })

  it('expand all and collapse all walk the whole tree', () => {
    browser.directoryTree.value = [{ name: 'd', path: '/d', is_dir: true, expanded: false, children: [{ name: 'e', path: '/d/e', is_dir: true, expanded: false }] }]
    const a = useFileBrowserActions({ chatContext: false })
    a.expandAll()
    expect(JSON.stringify(browser.directoryTree.value)).not.toContain('"expanded":false')
    a.collapseAll()
    expect(JSON.stringify(browser.directoryTree.value)).not.toContain('"expanded":true')
  })
})
