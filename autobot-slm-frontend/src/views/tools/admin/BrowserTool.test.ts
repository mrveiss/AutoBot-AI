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
    expect(indicatorClasses(wrapper)).toContain('bg-autobot-dot-ok')
    expect(wrapper.text()).toContain(en.tools.admin.browserTool.status.connected)
  })

  it('distinguishes degraded from unavailable', async () => {
    const degraded = await mountWithStatus({ browser_vm: { status: 'degraded' } })
    expect(indicatorClasses(degraded)).toContain('bg-autobot-dot-warn')

    const down = await mountWithStatus({ browser_vm: { status: 'unavailable' } })
    expect(indicatorClasses(down)).toContain('bg-autobot-dot-bad')
  })

  it('does not read connected from the top-level field the route never sends', async () => {
    // Exactly the body the old client believed in. If the component reverts to
    // `data.status`, this goes green and this test fails.
    const wrapper = await mountWithStatus({ status: 'connected' })
    expect(indicatorClasses(wrapper)).not.toContain('bg-autobot-dot-ok')
    expect(wrapper.text()).toContain(en.tools.admin.browserTool.status.unknown)
  })

  it('shows "unknown", not "disconnected", when the field is absent', async () => {
    // The vacuity probe: a missing field must not read as a confident "down",
    // or a renamed field would be indistinguishable from a dead VM.
    const wrapper = await mountWithStatus({ success: true, browser_vm: {} })
    expect(wrapper.text()).toContain(en.tools.admin.browserTool.status.unknown)
    expect(indicatorClasses(wrapper)).toContain('bg-autobot-dot-idle')
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
    await wrapper.get('input[type="text"]').setValue('https://example.test/')
    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain(detail)
    expect(wrapper.text()).not.toContain('whitelist')
  })
})

/** The address bar and the first button (Start, until connected) of a mounted tool. */
async function startWith(address: string) {
  const wrapper = await mountWithStatus({ browser_vm: { status: 'unavailable' } })
  backendClient.post.mockReset()
  backendClient.post.mockResolvedValue({})
  await wrapper.get('input[type="text"]').setValue(address)
  await wrapper.findAll('button').find((b) => b.text() === en.tools.admin.browserTool.startBrowser)!.trigger('click')
  await flushPromises()
  return wrapper
}

function postedPaths(): string[] {
  return backendClient.post.mock.calls.map((call) => call[0] as string)
}

describe('BrowserTool Start needs a real http(s) URL (#22142)', () => {
  beforeEach(() => {
    backendClient.get.mockReset()
    backendClient.post.mockReset()
  })

  it('cannot submit the empty default: Start is disabled and nothing is posted', async () => {
    const wrapper = await mountWithStatus({ browser_vm: { status: 'unavailable' } })
    const start = wrapper.findAll('button').find((b) => b.text() === en.tools.admin.browserTool.startBrowser)!
    expect(start.attributes('disabled')).toBeDefined()
    await start.trigger('click')
    expect(backendClient.post).not.toHaveBeenCalled()
  })

  it.each(['/', 'javascript:history.back()', 'ftp://host.test/x', 'not a url'])(
    'refuses %j with the localised message and no request',
    async (address) => {
      const wrapper = await startWith(address)
      expect(backendClient.post).not.toHaveBeenCalled()
      expect(wrapper.text()).toContain(en.tools.admin.browserTool.invalidUrl)
    },
  )

  it('posts a valid https URL to navigate', async () => {
    await startWith('https://example.test/page')
    expect(backendClient.post).toHaveBeenCalledWith('/browser/mcp/navigate', { url: 'https://example.test/page' })
  })
})

describe('BrowserTool history buttons use real history routes (#22142)', () => {
  beforeEach(() => {
    backendClient.get.mockReset()
    backendClient.post.mockReset()
  })

  it.each([
    ['back', '/playwright/back'],
    ['forward', '/playwright/forward'],
    ['refresh', '/playwright/reload'],
  ])('%s posts %s and never a javascript: URL', async (label, route) => {
    const wrapper = await startWith('https://example.test/')
    backendClient.post.mockClear()
    const title = en.tools.admin.browserTool[label as 'back' | 'forward' | 'refresh']
    await wrapper.get(`button[title="${title}"]`).trigger('click')
    await flushPromises()
    expect(postedPaths()[0]).toBe(route)
    expect(JSON.stringify(backendClient.post.mock.calls)).not.toContain('javascript:')
    expect(postedPaths()).not.toContain('/browser/mcp/navigate')
  })
})
