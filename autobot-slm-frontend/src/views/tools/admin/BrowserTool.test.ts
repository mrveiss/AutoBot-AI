// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import BrowserTool from './BrowserTool.vue'
import { HttpError } from '@autobot/ui'
import { backendClient } from '@/testing/mockAutobotBackendClient'
import en from '@/locales/en.json'

/**
 * The status indicator reflects the browser VM's real state (#15228).
 *
 * It read `data.status` and compared it to `'connected'` / `'ready'`. The
 * route sends neither that field nor those values, so the dot was red however
 * healthy the VM was. Asserting the call succeeds passed the whole time —
 * these assert what the dot ends up showing.
 */

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 'test-token' }),
}))

vi.mock('@/utils/ApiClient', async (importOriginal) =>
  (await import('@/testing/mockAutobotBackendClient')).withMockedBackendClient(importOriginal),
)

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

async function mountWithStatus(body: unknown) {
  backendClient.get.mockResolvedValue(body)
  const wrapper = mount(BrowserTool, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

function indicatorClasses(wrapper: Awaited<ReturnType<typeof mountWithStatus>>): string {
  return wrapper.find('div.w-2.h-2.rounded-full').classes().join(' ')
}

describe('BrowserTool status indicator', () => {
  beforeEach(() => {
    backendClient.get.mockReset()
    backendClient.post.mockReset()
  })

  it('reads connected when the route reports a healthy browser VM', async () => {
    const wrapper = await mountWithStatus({
      success: true,
      browser_vm: { url: 'http://browser.invalid:1', status: 'healthy' },
      security: { fleet_membership_source: 'slm_node_registry' },
    })
    expect(indicatorClasses(wrapper)).toContain('bg-green-500')
    expect(wrapper.text()).toContain(en.tools.admin.browserTool.status.connected)
  })

  it('distinguishes degraded from unavailable', async () => {
    const degraded = await mountWithStatus({ browser_vm: { status: 'degraded' } })
    expect(indicatorClasses(degraded)).toContain('bg-amber-500')

    const down = await mountWithStatus({ browser_vm: { status: 'unavailable' } })
    expect(indicatorClasses(down)).toContain('bg-red-500')
  })

  it('does not read connected from the top-level field the route never sends', async () => {
    // Exactly the body the old client believed in. If the component reverts to
    // `data.status`, this goes green and this test fails.
    const wrapper = await mountWithStatus({ status: 'connected' })
    expect(indicatorClasses(wrapper)).not.toContain('bg-green-500')
    expect(wrapper.text()).toContain(en.tools.admin.browserTool.status.unknown)
  })

  it('shows "unknown", not "disconnected", when the field is absent', async () => {
    // The vacuity probe: a missing field must not read as a confident "down",
    // or a renamed field would be indistinguishable from a dead VM.
    const wrapper = await mountWithStatus({ success: true, browser_vm: {} })
    expect(wrapper.text()).toContain(en.tools.admin.browserTool.status.unknown)
    expect(indicatorClasses(wrapper)).toContain('bg-gray-400')
  })

  it('flags a degraded fleet source so a stale exception set is never silent', async () => {
    const wrapper = await mountWithStatus({
      browser_vm: { status: 'healthy' },
      security: { fleet_membership_source: 'ssot_fallback' },
    })
    expect(wrapper.text()).toContain(en.tools.admin.browserTool.fleetDegraded)
  })

  it('does not flag a healthy fleet source', async () => {
    const wrapper = await mountWithStatus({
      browser_vm: { status: 'healthy' },
      security: { fleet_membership_source: 'slm_node_registry' },
    })
    expect(wrapper.text()).not.toContain(en.tools.admin.browserTool.fleetDegraded)
  })

  it('surfaces the backend rejection reason verbatim', async () => {
    const wrapper = await mountWithStatus({ browser_vm: { status: 'unavailable' } })

    const detail = "Refused: '10.0.0.5' resolves to a non-public address and is neither a loopback host nor a node the fleet registry knows."
    backendClient.post.mockRejectedValue(new HttpError(400, 'Bad Request', { detail }))
    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain(detail)
    expect(wrapper.text()).not.toContain('whitelist')
  })
})
