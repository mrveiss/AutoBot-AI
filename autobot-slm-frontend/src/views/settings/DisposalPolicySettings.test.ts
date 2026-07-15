// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import DisposalPolicySettings from './DisposalPolicySettings.vue'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    getApiUrl: () => '',
    getAuthHeaders: () => ({}),
  }),
}))

describe('DisposalPolicySettings', () => {
  beforeEach(() => {
    global.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ value: JSON.stringify({ retention_days: 14, require_approval: true }) }),
    })) as unknown as typeof fetch
  })

  it('loads the current policy on mount', async () => {
    const wrapper = mount(DisposalPolicySettings)
    await flushPromises()
    const number = wrapper.find('input[type="number"]').element as HTMLInputElement
    expect(number.value).toBe('14')
  })

  it('PUTs the policy as JSON on save', async () => {
    const wrapper = mount(DisposalPolicySettings)
    await flushPromises()
    await wrapper.find('button[data-test="save-policy"]').trigger('click')
    await flushPromises()
    const putCall = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.find((c) => c[1]?.method === 'PUT')
    expect(putCall).toBeTruthy()
    expect(putCall![0]).toContain('/api/settings/llc.project_disposal_policy')
  })
})
