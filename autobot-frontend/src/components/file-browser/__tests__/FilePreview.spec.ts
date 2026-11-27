// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #22349: the Files tab preview on the kit modal -- content per type, close paths and focus return.
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import FilePreview from '../FilePreview.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const find = (sel: string) => document.body.querySelector(sel) as HTMLElement | null
const mountPreview = (previewFile: Record<string, unknown> | null, showPreview = true) =>
  mount(FilePreview, {
    props: { showPreview, previewFile: previewFile as never },
    attachTo: document.body,
    global: { plugins: [i18n], stubs: { Icon: true } },
  })

describe('FilePreview (#22349)', () => {
  beforeEach(() => { document.body.innerHTML = '' })

  it('renders nothing without a file', () => {
    const wrapper = mountPreview(null)
    expect(find('[role="dialog"]')).toBeNull()
    wrapper.unmount()
  })

  it('shows text content inside a modal dialog titled with the file name', () => {
    const wrapper = mountPreview({ name: 'n.txt', type: 'text', content: 'hello' })
    expect(find('[role="dialog"]')?.getAttribute('aria-modal')).toBe('true')
    expect(find('.text-preview')?.textContent).toContain('hello')
    expect(document.body.textContent).toContain('n.txt')
    wrapper.unmount()
  })

  it('pretty-prints JSON', () => {
    const wrapper = mountPreview({ name: 'a.json', type: 'json', content: '{"a":1}' })
    expect(find('.json-preview')?.textContent).toContain('"a": 1')
    wrapper.unmount()
  })

  it('an unknown type shows the info block and its Download button emits download', async () => {
    const file = { name: 'x.bin', type: 'other', fileType: 'bin', size: 1536 }
    const wrapper = mountPreview(file)
    expect(find('.file-info')?.textContent).toContain('1.5 KB')
    find('[data-testid="preview-download"]')!.click()
    expect(wrapper.emitted('download')?.[0]).toEqual([file])
    wrapper.unmount()
  })

  it('the close button emits close', async () => {
    const wrapper = mountPreview({ name: 'n.txt', type: 'text', content: 'x' })
    find(`[aria-label="${en.fileBrowser.preview.closeAriaLabel}"]`)!.click()
    expect(wrapper.emitted('close')).toHaveLength(1)
    wrapper.unmount()
  })

  it('Escape emits close', async () => {
    const wrapper = mountPreview({ name: 'n.txt', type: 'text', content: 'x' })
    find('[role="dialog"]')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(wrapper.emitted('close')).toHaveLength(1)
    wrapper.unmount()
  })

  it('returns focus to the element that opened it once it closes', async () => {
    const trigger = document.createElement('button')
    document.body.appendChild(trigger)
    trigger.focus()
    const wrapper = mountPreview({ name: 'n.txt', type: 'text', content: 'x' }, false)
    await wrapper.setProps({ showPreview: true })
    find('[role="dialog"]')?.focus()
    await wrapper.setProps({ showPreview: false })
    expect(document.activeElement).toBe(trigger)
    wrapper.unmount()
  })
})
