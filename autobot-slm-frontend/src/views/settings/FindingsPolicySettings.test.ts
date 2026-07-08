// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import FindingsPolicySettings from './FindingsPolicySettings.vue'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    getApiUrl: () => '',
    getAuthHeaders: () => ({}),
  }),
}))

describe('FindingsPolicySettings', () => {
  beforeEach(() => {
    global.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        value: JSON.stringify({
          enabled: true,
          min_severity: 'high',
          require_approval_to_promote: true,
          run_on_index: false,
          verify_batch_size: 25,
        }),
      }),
    })) as unknown as typeof fetch
  })

  it('loads the current policy on mount', async () => {
    const wrapper = mount(FindingsPolicySettings)
    await flushPromises()
    const batchInput = wrapper.find('input[data-test="input-verify-batch-size"]').element as HTMLInputElement
    expect(batchInput.value).toBe('25')
    const severitySelect = wrapper.find('select[data-test="select-min-severity"]').element as HTMLSelectElement
    expect(severitySelect.value).toBe('high')
  })

  it('PUTs the policy as JSON on save', async () => {
    const wrapper = mount(FindingsPolicySettings)
    await flushPromises()
    await wrapper.find('button[data-test="save-policy"]').trigger('click')
    await flushPromises()
    const putCall = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.find((c) => c[1]?.method === 'PUT')
    expect(putCall).toBeTruthy()
    expect(putCall![0]).toContain('/api/settings/llc.findings_policy')
  })
})
