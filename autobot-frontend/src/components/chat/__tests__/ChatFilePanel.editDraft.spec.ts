// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #21337: switching conversation closes an open edit dialog, so a save never sends the old draft to the new session.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const { get, put } = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }))

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get, put, rawRequest: vi.fn() }) }))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api' }))
vi.mock('@/composables/useConfirmDialog', () => ({ useConfirmDialog: () => ({ confirm: vi.fn() }) }))
vi.mock('vue-i18n', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-i18n')>()),
  useI18n: () => ({ t: (k: string) => k, locale: { value: 'en' } }),
}))

import ChatFilePanel from '../ChatFilePanel.vue'

const listing = {
  files: [{ file_id: 'f1', filename: 'notes.txt', original_filename: 'notes.txt', size: 5, mime_type: 'text/plain', uploaded_at: '2026-11-01T10:00:00Z', uploaded_by: 'alice' }],
  total_files: 1,
  total_size: 5,
}

describe('ChatFilePanel edit draft (#21337)', () => {
  beforeEach(() => {
    get.mockReset(); put.mockReset()
    get.mockImplementation(async (url: string) => (url.includes('/content') ? { content: 'draft' } : listing))
    document.body.innerHTML = ''
  })

  it('closes the edit dialog on a session change, so a save cannot reach the new session', async () => {
    const wrapper = mount(ChatFilePanel, {
      props: { sessionId: 's1' },
      attachTo: document.body,
      global: { mocks: { $t: (k: string) => k }, stubs: { Icon: true, EmptyState: true, StatusBadge: true, BaseAlert: true } },
    })
    await flushPromises()
    await wrapper.find('button[title="common.edit"]').trigger('click')
    await flushPromises()
    expect(document.body.querySelector('textarea')).not.toBeNull()

    await wrapper.setProps({ sessionId: 's2' })
    await flushPromises()

    expect(document.body.querySelector('textarea')).toBeNull()
    expect(put).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('discards an edit response that lands after the session switched, so the editor stays closed', async () => {
    let release: (v: unknown) => void = () => {}
    get.mockImplementation((url: string) => (url.includes('/content')
      ? new Promise((r) => { release = r })
      : Promise.resolve(listing)))
    const wrapper = mount(ChatFilePanel, {
      props: { sessionId: 's1' },
      attachTo: document.body,
      global: { mocks: { $t: (k: string) => k }, stubs: { Icon: true, EmptyState: true, StatusBadge: true, BaseAlert: true } },
    })
    await flushPromises()
    await wrapper.find('button[title="common.edit"]').trigger('click')
    await wrapper.setProps({ sessionId: 's2' })
    await flushPromises()

    release({ content: 'old session draft' })
    await flushPromises()

    expect(document.body.querySelector('textarea')).toBeNull()
    expect(put).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
