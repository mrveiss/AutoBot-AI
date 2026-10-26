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
