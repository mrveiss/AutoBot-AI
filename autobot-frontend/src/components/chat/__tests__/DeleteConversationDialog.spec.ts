// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// DeleteConversationDialog (#18243): a failed preview is shown as an error in the dialog, not as an empty one.
import { describe, it, expect } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import DeleteConversationDialog from '../DeleteConversationDialog.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const render = (props: Record<string, unknown> = {}) =>
  mount(DeleteConversationDialog, {
    props: { visible: true, sessionId: 's1', fileStats: null, kbFacts: null, ...props },
    attachTo: document.body,
    global: { plugins: [i18n] },
  })

describe('DeleteConversationDialog preview failure', () => {
  it('shows the error alert, and still offers deleting, when the preview failed', async () => {
    const w = render({ previewFailed: true })
    await flushPromises()
    expect(document.body.textContent).toContain(en.chat.sidebar.previewFailed)
    expect(document.querySelector('[role="alert"]')).not.toBeNull()
    w.unmount()
  })

  it('shows no error when the preview simply had nothing', async () => {
    const w = render({ previewFailed: false })
    await flushPromises()
    expect(document.body.textContent).not.toContain(en.chat.sidebar.previewFailed)
    w.unmount()
  })
})
