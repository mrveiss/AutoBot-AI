// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// GH#10531: HandoffModal must call the real /handoff/to-* endpoints (NOT /release).

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const get = vi.fn()
const post = vi.fn()

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get, post }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))
vi.mock('@/stores/useUserStore', () => ({
  useUserStore: () => ({ currentUser: { id: 'user-1', displayName: 'Operator' } }),
}))

import HandoffModal from '../HandoffModal.vue'

// vue-i18n 11 requires app.use(); HandoffModal uses useI18n() in <script setup>,
// so a bare $t mock is not enough. Install a real i18n instance with empty
// messages + warnings off so t('key') / $t('key') return the key verbatim (the
// original assertion contract that mocks: { $t } provided).
const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages: { en: {} },
  missingWarn: false,
  fallbackWarn: false,
})

// BaseModal (@autobot/ui) wraps its body/actions in <Teleport to="body">;
// stub Teleport so the slotted <select> + .handoff-confirm render inline where
// wrapper.find() can reach them.
const mountOpts = { global: { plugins: [i18n], stubs: { teleport: true } } }

describe('HandoffModal (GH#10531)', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
    post.mockResolvedValue({})
    get.mockImplementation((url: string) => {
      if (url.includes('/org-chart')) {
        return Promise.resolve({ nodes: [{ node_id: 'agent-pk-1', name: 'Builder', is_human: false }] })
      }
      if (url.includes('/members')) {
        return Promise.resolve([{ user_id: 'human-1', display_name: 'Reviewer Rita', role: 'member' }])
      }
      return Promise.resolve([])
    })
  })

  it('to_agent posts to /handoff/to-agent with the agent PK (not /release)', async () => {
    const wrapper = mount(HandoffModal, {
      props: { workItemId: 'wi-1', companyId: 'c1', direction: 'to_agent' },
      ...mountOpts,
    })
    await flushPromises()
    await wrapper.find('select').setValue('agent-pk-1')
    await wrapper.find('.handoff-confirm').trigger('click')
    await flushPromises()

    expect(post).toHaveBeenCalledTimes(1)
    const [url, body] = post.mock.calls[0]
    expect(url).toBe('/api/llc/work-items/wi-1/handoff/to-agent')
    expect(url).not.toContain('/release')
    expect(body.target_agent_id).toBe('agent-pk-1')
    expect(body.user_id).toBe('user-1')
  })

  it('to_human posts to /handoff/to-human with reviewer_user_id + the agent assignee', async () => {
    const wrapper = mount(HandoffModal, {
      props: { workItemId: 'wi-2', companyId: 'c1', direction: 'to_human', agentAssigneeId: 'agent-pk-9' },
      ...mountOpts,
    })
    await flushPromises()
    await wrapper.find('select').setValue('human-1')
    await wrapper.find('.handoff-confirm').trigger('click')
    await flushPromises()

    const [url, body] = post.mock.calls[0]
    expect(url).toBe('/api/llc/work-items/wi-2/handoff/to-human')
    expect(body.reviewer_user_id).toBe('human-1')
    expect(body.agent_id).toBe('agent-pk-9')
  })
})
