// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// ChatComposerUploads (#18243): upload rows with status, cancel and retry; attached files with remove and clear.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ChatComposerUploads from '../ChatComposerUploads.vue'
import type { UploadItem } from '@/composables/chat/useComposerUploads'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const upload = (over: Partial<UploadItem> = {}): UploadItem => ({
  id: 'u1', filename: 'a.csv', progress: 0, phase: 'preparing', current: 0, total: 100, ...over,
})
const render = (props: Record<string, unknown> = {}) =>
  mount(ChatComposerUploads, {
    props: { uploads: [], files: [], isCancellable: () => false, ...props },
    attachTo: document.body,
    global: { plugins: [i18n] },
  })

describe('ChatComposerUploads', () => {
  it('renders nothing for an empty composer', () => {
    const w = render()
    expect(w.findAll('li')).toHaveLength(0)
    w.unmount()
  })

  it('shows the phase of an upload, and the percentage once bytes move', () => {
    const w = render({ uploads: [upload({ phase: 'uploading', progress: 41.6 })] })
    expect(w.get('[data-testid="composer-upload"]').text()).toContain('Uploading… 42%')
    w.unmount()
  })

  it('shows the error in place of the status, with a Retry button that emits the id', async () => {
    const w = render({ uploads: [upload({ phase: 'failed', error: 'Network error during upload' })] })
    const row = w.get('[data-testid="composer-upload"]')
    expect(row.text()).toContain('Network error during upload')
    await row.get(`[aria-label="${en.chat.input.retryUpload}"]`).trigger('click')
    expect(w.emitted('retry')).toEqual([['u1']])
    w.unmount()
  })

  it('offers a named Cancel only while the upload is cancellable', async () => {
    const w = render({ uploads: [upload()], isCancellable: () => true })
    const cancel = w.get('[aria-label="Cancel upload of a.csv"]')
    await cancel.trigger('click')
    expect(w.emitted('cancel')).toEqual([['u1']])
    w.unmount()
    const none = render({ uploads: [upload()], isCancellable: () => false })
    expect(none.find('[aria-label="Cancel upload of a.csv"]').exists()).toBe(false)
    none.unmount()
  })

  it('lists attached files with their size, and removes one by index with a named button', async () => {
    const files = [new File(['abc'], 'a.txt', { type: 'text/plain' }), new File(['de'], 'b.txt', { type: 'text/plain' })]
    const w = render({ files })
    const rows = w.findAll('[data-testid="composer-attached-file"]')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('a.txt')
    await rows[1].get('[aria-label="Remove b.txt"]').trigger('click')
    expect(w.emitted('remove')).toEqual([[1]])
    w.unmount()
  })

  it('counts the attached files and clears them all', async () => {
    const w = render({ files: [new File(['a'], 'a.txt')] })
    expect(w.text()).toContain('1 files attached')
    await w.findAll('button').find((b) => b.text() === en.chat.input.clearAll)!.trigger('click')
    expect(w.emitted('clear-all')).toHaveLength(1)
    w.unmount()
  })
})
