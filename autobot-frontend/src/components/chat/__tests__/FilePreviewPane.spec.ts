// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #22349: the preview pane on the kit modal -- loading, content, truncation, close paths and focus return.
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick, ref } from 'vue'
import FilePreviewPane from '../FilePreviewPane.vue'

const preview = (over: Record<string, unknown> = {}) =>
  ({ filename: 'notes.txt', truncated: false, data: { preview_content: 'hello' }, ...over }) as never
const find = (sel: string) => document.body.querySelector(sel) as HTMLElement | null
const mountPane = (value: unknown) =>
  mount(FilePreviewPane, {
    props: { preview: value as never },
    attachTo: document.body,
    global: { mocks: { $t: (k: string) => k } },
  })

describe('FilePreviewPane (#22349)', () => {
  beforeEach(() => { document.body.innerHTML = '' })

  it('shows the loading status while the preview is null', () => {
    const wrapper = mountPane(null)
    expect(find('[data-testid="file-preview-loading"]')?.getAttribute('role')).toBe('status')
    expect(find('[data-testid="file-preview-content"]')).toBeNull()
    wrapper.unmount()
  })

  it('shows the content in a labelled, keyboard-scrollable area inside a modal dialog', () => {
    const wrapper = mountPane(preview())
    const content = find('[data-testid="file-preview-content"]')!
    expect(content.textContent).toBe('hello')
    expect(content.getAttribute('tabindex')).toBe('0')
    expect(find('[role="dialog"]')?.getAttribute('aria-modal')).toBe('true')
    wrapper.unmount()
  })

  it('shows the empty-file text for an empty preview', () => {
    const wrapper = mountPane(preview({ data: { preview_content: '' } }))
    expect(find('[data-testid="file-preview-content"]')?.textContent).toBe('chat.filePanel.previewEmpty')
    wrapper.unmount()
  })

  it('notes truncation only when truncated', () => {
    const truncated = mountPane(preview({ truncated: true }))
    expect(find('[data-testid="file-preview-truncated"]')).not.toBeNull()
    truncated.unmount()
    document.body.innerHTML = ''
    const complete = mountPane(preview())
    expect(find('[data-testid="file-preview-truncated"]')).toBeNull()
    complete.unmount()
  })

  it('emits close from the close button, from Escape and from the backdrop', () => {
    const wrapper = mountPane(preview())
    find('button[aria-label="chat.filePanel.closePreview"]')!.click()
    find('[role="dialog"]')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    find('.aui-dialog-overlay')!.click()
    expect(wrapper.emitted('close')).toHaveLength(3)
    wrapper.unmount()
  })

  it('returns focus to the element that had it when the pane unmounts', async () => {
    const trigger = document.createElement('button')
    document.body.appendChild(trigger)
    trigger.focus()
    const show = ref(true)
    const Host = defineComponent({ setup: () => () => (show.value ? h(FilePreviewPane, { preview: preview() }) : null) })
    const wrapper = mount(Host, { attachTo: document.body, global: { mocks: { $t: (k: string) => k } } })
    find('[role="dialog"]')!.focus()
    show.value = false
    await nextTick()
    expect(document.activeElement).toBe(trigger)
    wrapper.unmount()
  })
})
