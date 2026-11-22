// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #15907: an agent's page shows its heartbeat state and switches it on or off
// through the board control route; a refused write puts the switch back.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const put = vi.fn()

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ put }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import AgentHeartbeatControl from '../AgentHeartbeatControl.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
const URL = '/api/llc/companies/c1/controls/agents/ceo-c1/heartbeat'

function mountControl(enabled: boolean) {
  return mount(AgentHeartbeatControl, {
    props: { companyId: 'c1', agentId: 'ceo-c1', enabled },
    global: { plugins: [i18n] },
  })
}

beforeEach(() => {
  put.mockReset()
})

describe('AgentHeartbeatControl (#15907)', () => {
  it('shows the current state from the server row', () => {
    expect(mountControl(false).get('[data-testid="agent-heartbeat-state"]').text()).toBe(en.llc.orgChart.heartbeat.off)
    expect(mountControl(true).get('[data-testid="agent-heartbeat-state"]').text()).toBe(en.llc.orgChart.heartbeat.on)
  })

  it('switching on writes heartbeat_enabled=true for this agent and reports it', async () => {
    put.mockResolvedValue({ heartbeat_enabled: true })
    const wrapper = mountControl(false)

    await wrapper.get('[role="switch"]').trigger('click')
    await flushPromises()

    expect(put).toHaveBeenCalledWith(URL, { heartbeat_enabled: true })
    expect(wrapper.emitted('changed')).toEqual([[true]])
    expect(wrapper.get('[role="switch"]').attributes('aria-checked')).toBe('true')
  })

  it('a refused write puts the switch back and says why', async () => {
    put.mockRejectedValue(new Error('Agent ceo-c1 is inactive; its heartbeat cannot be enabled'))
    const wrapper = mountControl(false)

    await wrapper.get('[role="switch"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[role="switch"]').attributes('aria-checked')).toBe('false')
    expect(wrapper.get('[role="alert"]').text()).toContain('is inactive')
    expect(wrapper.emitted('changed')).toBeUndefined()
  })
})
