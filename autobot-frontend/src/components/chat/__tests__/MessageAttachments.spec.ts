// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// MessageAttachments (#18243): the list the stream shows, its icon and size format, view and download.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import MessageAttachments from '../MessageAttachments.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en }, missingWarn: false, fallbackWarn: false })
const files = [
  { id: 'a', name: 'doc.pdf', type: 'application/pdf', size: 1536, url: 'https://x/doc.pdf' },
  { id: 'b', name: 'pic.png', type: 'image/png', size: 0, url: '' },
]
const render = () => mount(MessageAttachments, { props: { attachments: files }, global: { plugins: [i18n], stubs: { Icon: { props: ['name'], template: '<i :data-icon="name" />' } } } })

describe('MessageAttachments', () => {
  it('lists each file with the stream icon map and the two-decimal size format', () => {
    const w = render()
    const items = w.findAll('.attachment-item')
    expect(items).toHaveLength(2)
    expect(items[0].find('[data-icon]').attributes('data-icon')).toBe('file-pdf')
    expect(items[1].find('[data-icon]').attributes('data-icon')).toBe('image')
    expect(items[0].find('.attachment-size').text()).toBe('1.5 KB')
    expect(items[1].find('.attachment-size').text()).toBe('0 Bytes') // the kit formatter, as main's stream used
  })

  it('emits view on click and Enter, and download without also emitting view', async () => {
    const w = render()
    const first = w.findAll('.attachment-item')[0]
    await first.trigger('click')
    await first.trigger('keydown', { key: 'Enter' })
    expect(w.emitted('view')).toHaveLength(2)
    await first.get('.attachment-download').trigger('click')
    expect(w.emitted('download')?.[0]).toEqual([files[0]])
    expect(w.emitted('view')).toHaveLength(2)
  })
})
