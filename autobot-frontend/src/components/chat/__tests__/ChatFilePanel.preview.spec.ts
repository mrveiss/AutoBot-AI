// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #20906: opening a preview from a listed attachment calls the preview route and renders its response.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get, rawRequest: vi.fn() }) }))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api' }))
vi.mock('@/composables/useConfirmDialog', () => ({ useConfirmDialog: () => ({ confirm: vi.fn() }) }))
vi.mock('vue-i18n', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-i18n')>()),
  useI18n: () => ({ t: (k: string) => k, locale: { value: 'en' } }),
}))

import ChatFilePanel from '../ChatFilePanel.vue'

const textFile = { file_id: 'f1', filename: 'notes.txt', original_filename: 'notes.txt', size: 5, mime_type: 'text/plain', uploaded_at: '2026-11-01T10:00:00Z', uploaded_by: 'alice' }
const listing = {
  files: [{ file_id: 'f1', filename: 'notes.txt', original_filename: 'notes.txt', size: 5, mime_type: 'text/plain', uploaded_at: '2026-11-01T10:00:00Z', uploaded_by: 'alice' }],
  total_files: 1,
  total_size: 5,
}
let previewBody: Record<string, unknown> = { file_info: { file_id: 'f1' }, preview_available: true, preview_content: 'hello preview', preview_type: 'text' }

const base = { file_info: { file_id: 'f1' }, preview_available: true, preview_content: 'hello preview', preview_type: 'text' }
const pane = () => document.body.querySelector('[data-testid="file-preview-pane"]')

describe('ChatFilePanel preview (#20906)', () => {
  let list: typeof listing
  const open = async (props = { sessionId: 's1' }) => {
    const wrapper = mount(ChatFilePanel, {
      props,
      attachTo: document.body,
      global: {
        mocks: { $t: (k: string) => k },
        stubs: { Icon: true, EmptyState: true, StatusBadge: true, BaseAlert: true },
      },
    })
    await flushPromises()
    return wrapper
  }
  const clickPreview = async (wrapper: Awaited<ReturnType<typeof open>>) => {
    await wrapper.find('button[title="chat.filePanel.preview"]').trigger('click')
    await flushPromises()
  }

  beforeEach(() => {
    get.mockReset()
    previewBody = base
    list = listing
    get.mockImplementation(async (url: string) => (url.includes('/preview/') ? previewBody : list))
    document.body.innerHTML = ''
  })

  it('calls the preview route and renders the response in the pane', async () => {
    const wrapper = await open()
    await clickPreview(wrapper)
    expect(get).toHaveBeenCalledWith('/api/conversation-files/conversation/s1/preview/f1')
    expect(document.body.querySelector('[data-testid="file-preview-content"]')?.textContent).toBe('hello preview')
    wrapper.unmount()
  })

  it('is a modal dialog with a focusable, labelled content area, and focus moves into it', async () => {
    const wrapper = await open()
    await clickPreview(wrapper)
    const dialog = document.body.querySelector('[role="dialog"]')
    expect(dialog?.getAttribute('aria-modal')).toBe('true')
    const content = document.body.querySelector('[data-testid="file-preview-content"]')
    expect(content?.getAttribute('tabindex')).toBe('0')
    expect(content?.getAttribute('aria-label')).toBe('chat.filePanel.previewContentLabel')
    expect(dialog?.contains(document.activeElement)).toBe(true)
    wrapper.unmount()
  })

  it('the close button closes the pane and Escape closes it too', async () => {
    const wrapper = await open()
    await clickPreview(wrapper)
    ;(document.body.querySelector('[data-testid="file-preview-close"]') as HTMLElement).click()
    await flushPromises()
    expect(pane()).toBeNull()
    await clickPreview(wrapper)
    expect(pane()).not.toBeNull()
    document.body.querySelector('[role="dialog"]')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(pane()).toBeNull()
    wrapper.unmount()
  })

  it('returns focus to the trigger when the pane closes', async () => {
    const wrapper = await open()
    const trigger = wrapper.find('button[title="chat.filePanel.preview"]').element as HTMLElement
    trigger.focus()
    await clickPreview(wrapper)
    ;(document.body.querySelector('[data-testid="file-preview-close"]') as HTMLElement).click()
    await flushPromises()
    expect(document.activeElement).toBe(trigger)
    wrapper.unmount()
  })

  it('shows the empty-file text for an empty preview', async () => {
    previewBody = { ...base, preview_content: '' }
    const wrapper = await open()
    await clickPreview(wrapper)
    expect(document.body.querySelector('[data-testid="file-preview-content"]')?.textContent).toBe('chat.filePanel.previewEmpty')
    wrapper.unmount()
  })

  it('notes truncation when the file is larger than the content shown', async () => {
    list = { ...listing, files: [{ ...textFile, size: 50_000 }] }
    const wrapper = await open()
    await clickPreview(wrapper)
    expect(document.body.querySelector('[data-testid="file-preview-truncated"]')).not.toBeNull()
    wrapper.unmount()
  })

  it('shows no truncation note for a complete file', async () => {
    const wrapper = await open()
    await clickPreview(wrapper)
    expect(document.body.querySelector('[data-testid="file-preview-truncated"]')).toBeNull()
    wrapper.unmount()
  })

  it('shows a loading state while the preview is fetched', async () => {
    let release: (v: unknown) => void = () => {}
    get.mockImplementation((url: string) =>
      url.includes('/preview/') ? new Promise((r) => { release = r }) : Promise.resolve(list))
    const wrapper = await open()
    await clickPreview(wrapper)
    expect(document.body.querySelector('[data-testid="file-preview-loading"]')).not.toBeNull()
    release(base)
    await flushPromises()
    expect(document.body.querySelector('[data-testid="file-preview-loading"]')).toBeNull()
    expect(document.body.querySelector('[data-testid="file-preview-content"]')).not.toBeNull()
    wrapper.unmount()
  })

  it('closes a stale preview when the session changes', async () => {
    const wrapper = await open()
    await clickPreview(wrapper)
    expect(pane()).not.toBeNull()
    await wrapper.setProps({ sessionId: 's2' })
    await flushPromises()
    expect(pane()).toBeNull()
    wrapper.unmount()
  })
})
