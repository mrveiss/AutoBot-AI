// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #20234: a person can see, approve and reject a pending removal proposal, and reset a stuck file.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { HttpError } from '@autobot/ui'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
const post = vi.fn()

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get, post }) }))
vi.mock('@/composables/useNotificationBus', () => ({ useNotificationBus: () => ({ showToast: vi.fn() }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import Panel from '../StuckFileCleanupPanel.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
const STATUS = {
  stuck_cleanup_files: 1,
  stuck_cleanup_bytes: 5,
  stuck_cleanup: [{ file_id: 'f1', file_size: 5, failed_attempts: 3, last_reason: 'outside' }],
}
const PROPOSALS = [
  { id: 'a1', title: 'Remove deleted conversation file: a.txt', description: 'd', approval_type: 'destructive_action' },
  { id: 'a2', title: 'Something else', description: 'd', approval_type: 'tool_use' },
]

async function mountPanel() {
  const wrapper = mount(Panel, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  get.mockReset()
  post.mockReset()
  post.mockResolvedValue({})
  get.mockImplementation((url: string) =>
    Promise.resolve(url.includes('/approval-gates/pending') ? PROPOSALS : STATUS)
  )
})

describe('StuckFileCleanupPanel (#20234)', () => {
  it('lists only destructive-action proposals and approves one through the existing route', async () => {
    const wrapper = await mountPanel()
    const rows = wrapper.findAll('[data-testid="removal-proposals"] li')
    expect(rows).toHaveLength(1)
    await rows[0].findAll('button')[0].trigger('click')
    expect(post).toHaveBeenCalledWith('/api/approval-gates/a1/approve', {})
  })

  it('rejects through the existing route', async () => {
    const wrapper = await mountPanel()
    await wrapper.findAll('[data-testid="removal-proposals"] li')[0].findAll('button')[1].trigger('click')
    expect(post).toHaveBeenCalledWith('/api/approval-gates/a1/reject', {})
  })

  it('resets a stuck file', async () => {
    const wrapper = await mountPanel()
    await wrapper.find('[data-testid="stuck-files"] button').trigger('click')
    expect(post).toHaveBeenCalledWith('/api/conversation-files/cleanup/f1/reset', {})
  })

  it.each([401, 403])('hides the panel and never asks for proposals on HTTP %i', async (status) => {
    get.mockRejectedValue(new HttpError(status, 'refused'))
    const wrapper = await mountPanel()
    expect(wrapper.html()).not.toContain('removal-proposals')
    expect(wrapper.find('[data-testid="load-error"]').exists()).toBe(false)
    expect(get).toHaveBeenCalledTimes(1)
  })

  it('shows an error alert, not an empty panel, when the status call fails with a server error', async () => {
    get.mockRejectedValueOnce(new HttpError(500, 'boom'))
    const wrapper = await mountPanel()
    const alert = wrapper.find('[data-testid="load-error"]')
    expect(alert.exists()).toBe(true)
    expect(alert.text()).toContain(en.llc.approvals.stuckCleanup.loadError)
    expect(wrapper.find('[data-testid="stuck-files"]').exists()).toBe(false)
  })

  it('retries a failed load and shows the data once it succeeds', async () => {
    get.mockRejectedValueOnce(new HttpError(500, 'boom'))
    const wrapper = await mountPanel()
    await wrapper.find('[data-testid="load-error"] button').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="load-error"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="stuck-files"]').exists()).toBe(true)
  })
})
