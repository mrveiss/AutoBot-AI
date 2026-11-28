// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #22349: the Files tab -- the flat table with Upload is the default, the tree and the view toggle are advanced
// surfaces, every control is kept, and `chatContext` reaches the actions.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const actions = {
  directoryTree: ref([]), previewFile: ref(null), currentPath: ref('/'), selectedPath: ref(''),
  viewMode: ref<'tree' | 'list'>('list'), sortField: ref('name'), sortOrder: ref('asc'), showPreview: ref(false),
  sortedFiles: ref([{ name: 'a.txt', path: '/a.txt', is_dir: false }]),
  refreshFiles: vi.fn(), navigateToPath: vi.fn(), toggleView: vi.fn(), sortBy: vi.fn(), uploadFiles: vi.fn(),
  viewFile: vi.fn(), deleteFile: vi.fn(), renameFile: vi.fn(), createNewFolder: vi.fn(), closePreview: vi.fn(),
  downloadPreviewFile: vi.fn(), toggleNode: vi.fn(), expandAll: vi.fn(), collapseAll: vi.fn(),
}
const useActions = vi.fn(() => actions)
vi.mock('@/composables/file-browser/useFileBrowserActions', () => ({ useFileBrowserActions: (o: unknown) => useActions(o) }))

import FileBrowser from '../FileBrowser.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const mountBrowser = (props: Record<string, unknown> = {}) =>
  mount(FileBrowser, { props, global: { plugins: [i18n], stubs: { Icon: true } } })

describe('FileBrowser (#22349)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    actions.viewMode.value = 'list'
  })

  it('passes chatContext to the actions and loads the folder on mount', () => {
    mountBrowser({ chatContext: true })
    expect(useActions).toHaveBeenCalledWith({ chatContext: true })
    expect(actions.refreshFiles).toHaveBeenCalled()
  })

  it('shows the flat table and no tree by default; the view toggle is an advanced control', () => {
    const wrapper = mountBrowser()
    expect(wrapper.find('.tree-side').exists()).toBe(false)
    expect(wrapper.find('[data-testid="file-row-a.txt"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="toggle-view"]').classes()).toContain('adv')
  })

  it('the tree view is an advanced surface', () => {
    actions.viewMode.value = 'tree'
    const wrapper = mountBrowser()
    expect(wrapper.get('.tree-side').classes()).toContain('adv')
  })

  it('refresh, toggle view, new folder and the file actions reach the composable', async () => {
    const wrapper = mountBrowser()
    await wrapper.get('[data-testid="refresh-files"]').trigger('click')
    await wrapper.get('[data-testid="toggle-view"]').trigger('click')
    expect(actions.refreshFiles).toHaveBeenCalledTimes(2)
    expect(actions.toggleView).toHaveBeenCalledTimes(1)
    await wrapper.get(`button[aria-label="${en.fileBrowser.header.newFolder}"]`).trigger('click')
    expect(actions.createNewFolder).toHaveBeenCalledTimes(1)
    await wrapper.get('[data-testid="row-delete"]').trigger('click')
    expect(actions.deleteFile).toHaveBeenCalledTimes(1)
  })

  it('Upload file in the header opens the file picker of the upload input', async () => {
    const wrapper = mountBrowser()
    const input = wrapper.get('[data-testid="file-upload-input"]').element as HTMLInputElement
    const click = vi.spyOn(input, 'click')
    await wrapper.get(`button[aria-label="${en.fileBrowser.header.uploadFile}"]`).trigger('click')
    expect(click).toHaveBeenCalledTimes(1)
  })
})
