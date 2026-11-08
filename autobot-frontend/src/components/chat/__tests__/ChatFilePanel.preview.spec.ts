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

const listing = {
  files: [{ file_id: 'f1', filename: 'notes.txt', original_filename: 'notes.txt', size: 5, mime_type: 'text/plain', uploaded_at: '2026-11-01T10:00:00Z', uploaded_by: 'alice' }],
  total_files: 1,
  total_size: 5,
}
const previewBody = { file_info: { file_id: 'f1' }, preview_available: true, preview_content: 'hello preview', preview_type: 'text' }

describe('ChatFilePanel preview (#20906)', () => {
  beforeEach(() => {
    get.mockReset()
    get.mockImplementation(async (url: string) => (url.includes('/preview/') ? previewBody : listing))
    document.body.innerHTML = ''
  })

  it('calls the preview route and renders the response in the pane', async () => {
    const wrapper = mount(ChatFilePanel, {
      props: { sessionId: 's1' },
      attachTo: document.body,
      global: {
        mocks: { $t: (k: string) => k },
        stubs: { Icon: true, EmptyState: true, StatusBadge: true, BaseAlert: true },
      },
    })
    await flushPromises()
    await wrapper.find('button[title="chat.filePanel.preview"]').trigger('click')
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/api/conversation-files/conversation/s1/preview/f1')
    expect(document.body.querySelector('[data-testid="file-preview-content"]')?.textContent).toBe('hello preview')
    wrapper.unmount()
  })
})
