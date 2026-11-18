// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #15907: the hire form has a 'Run on heartbeat' switch, OFF by default (the
// 2026-09-28 ruling), and the hire request carries it as heartbeat_enabled.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const post = vi.fn()
const get = vi.fn()

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ post, get }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import HireAgentModal from '../HireAgentModal.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

function mountModal() {
  return mount(HireAgentModal, {
    props: { companyId: 'c1' },
    global: { plugins: [i18n], stubs: { teleport: true, AdapterTypeSelect: true } },
  })
}

async function hire(wrapper: ReturnType<typeof mountModal>) {
  await wrapper.get('input[type="text"]').setValue('Builder-1')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  return post.mock.calls[0][1]
}

beforeEach(() => {
  post.mockReset()
  post.mockResolvedValue({})
  get.mockReset()
  get.mockResolvedValue([])
})

describe('HireAgentModal heartbeat switch (#15907)', () => {
  it('is off by default and the hire says so', async () => {
    const wrapper = mountModal()
    const sw = wrapper.get('[data-testid="hire-heartbeat"]')
    expect(sw.attributes('aria-checked')).toBe('false')
    expect(sw.attributes('aria-label')).toBe(en.hireAgent.runOnHeartbeat)

    expect((await hire(wrapper)).heartbeat_enabled).toBe(false)
  })

  it('switched on, the hire is sent with heartbeat_enabled=true', async () => {
    const wrapper = mountModal()
    await wrapper.get('[data-testid="hire-heartbeat"]').trigger('click')

    const body = await hire(wrapper)
    expect(post.mock.calls[0][0]).toBe('/api/llc/companies/c1/agent-hires')
    expect(body.heartbeat_enabled).toBe(true)
  })
})

describe('HireAgentModal pending approval (#8214)', () => {
  it('a pending_approval answer shows the notice and does not claim a hire', async () => {
    post.mockResolvedValue({ status: 'pending_approval', approval_id: 'a1' })
    const wrapper = mountModal()
    await hire(wrapper)

    expect(wrapper.get('[data-testid="hire-pending"]').text()).toBe(en.hireAgent.pendingApproval)
    expect(wrapper.emitted('hired')).toBeUndefined()
    expect(wrapper.emitted('close')).toBeUndefined()
  })

  it('a hired agent still closes the modal and announces the hire', async () => {
    post.mockResolvedValue({ agent_id: 'x' })
    const wrapper = mountModal()
    await hire(wrapper)

    expect(wrapper.emitted('hired')).toHaveLength(1)
    expect(wrapper.emitted('close')).toHaveLength(1)
    expect(wrapper.find('[data-testid="hire-pending"]').exists()).toBe(false)
  })
})

describe('HireAgentModal submit guard and notice wording (#8214)', () => {
  it('a second submit while the first is in flight, or after a pending answer, sends nothing', async () => {
    post.mockResolvedValue({ status: 'pending_approval' })
    const wrapper = mountModal()
    await wrapper.get('input[type="text"]').setValue('Builder-1')
    await wrapper.get('form').trigger('submit')
    await wrapper.get('form').trigger('submit') // Enter while the first request is in flight
    await flushPromises()
    await wrapper.get('form').trigger('submit') // Enter after the pending answer
    await flushPromises()
    expect(post).toHaveBeenCalledTimes(1)
  })

  it('the notice describes the submission only, not a state the board can change', () => {
    expect(en.hireAgent.pendingApproval).not.toMatch(/waiting|no agent has been created/i)
  })
})
