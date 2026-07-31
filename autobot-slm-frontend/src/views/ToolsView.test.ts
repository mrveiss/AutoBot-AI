// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * ToolsView — remote-exec transport behaviour (#13140).
 *
 * ToolsView is the representative of the group that built its headers from
 * `authStore.getAuthHeaders()`, which returns `{}` for an unhydrated `token`
 * ref, so the request went out ANONYMOUS while a live session sat in storage.
 * It is also the group with a genuine timeout hazard: every tool here runs a
 * command over SSH against a fleet node, so it must NOT inherit the client's
 * 30s default — a long ansible run that completes fine today would abort.
 *
 * Asserted end to end at the component boundary:
 *
 *   * the bearer is attached from storage without the store ref being hydrated;
 *   * the request carries an abort signal (there was no timeout at all before);
 *   * the SSH-backed endpoints get the long remote-exec budget, not the default;
 *   * the endpoint path, method and JSON payload are unchanged;
 *   * the backend's `detail` error body is still what the operator is shown.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import ToolsView from './ToolsView.vue'
import { useFleetStore } from '@/stores/fleet'
import { REMOTE_EXEC_TIMEOUT_MS } from '@/constants/api-timeouts'
import en from '@/locales/en.json'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ params: {}, query: {} }),
}))

const TOKEN_KEY = 'slm_access_token'

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

const NODE = {
  node_id: 'node-a',
  ip_address: '10.0.0.9',
  ssh_user: 'autobot',
  ssh_port: 22,
  auth_method: 'key',
  status: 'online',
  roles: ['redis'],
}

/**
 * The view loads nodes on mount through the fleet store; seed the store's node
 * map directly so its own transport is not part of what this suite asserts.
 */
function seedFleet() {
  const fleet = useFleetStore()
  ;(fleet.nodes as unknown as Map<string, typeof NODE>).set(NODE.node_id, NODE)
}

async function mountTools() {
  const wrapper = mount(ToolsView, { global: { plugins: [i18n] } })
  // Let the on-mount `fleetStore.fetchNodes()` settle FIRST — it replaces the
  // node map wholesale, so seeding before it would be overwritten.
  await flushPromises()
  seedFleet()
  await flushPromises()
  return wrapper
}

/** Find the request this suite is about, ignoring any fleet-store traffic. */
function callTo(mock: ReturnType<typeof vi.fn>, path: string) {
  const call = mock.mock.calls.find((c) => String(c[0]).includes(path))
  expect(call, `no request to ${path}`).toBeDefined()
  return { url: String(call![0]), init: call![1] as RequestInit }
}

describe('ToolsView remote-exec transport', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  let originalLocation: Location

  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
    setActivePinia(createPinia())
    fetchMock = vi.fn().mockResolvedValue(jsonResponse({ nodes: [] }))
    vi.stubGlobal('fetch', fetchMock)

    originalLocation = window.location
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: { pathname: '/tools', href: '' } as unknown as Location,
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: originalLocation,
    })
  })

  it('attaches the stored bearer to an exec although the store ref is unhydrated', async () => {
    // `authStore.getAuthHeaders()` returned `{}` in exactly this state, so the
    // command was dispatched to the fleet with no credential at all.
    sessionStorage.setItem(TOKEN_KEY, 'tools-token')
    const wrapper = await mountTools()

    fetchMock.mockResolvedValue(jsonResponse({ output: 'PONG' }))
    const vm = wrapper.vm as unknown as {
      redisCommand: string
      runRedisCommand: () => Promise<void>
    }
    vm.redisCommand = 'PING'
    await vm.runRedisCommand()
    await flushPromises()

    const { init } = callTo(fetchMock, '/nodes/node-a/exec')
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tools-token')
  })

  it('sends the exec to the API base with the same method and payload', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'tools-token')
    const wrapper = await mountTools()

    fetchMock.mockResolvedValue(jsonResponse({ output: 'PONG' }))
    const vm = wrapper.vm as unknown as {
      redisCommand: string
      runRedisCommand: () => Promise<void>
    }
    vm.redisCommand = 'PING'
    await vm.runRedisCommand()
    await flushPromises()

    const { url, init } = callTo(fetchMock, '/nodes/node-a/exec')
    expect(url).toBe('/api/nodes/node-a/exec')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ command: 'redis-cli PING' })
  })

  it('gives an SSH-backed exec the long budget, not the client default', async () => {
    // A raw fetch had no timeout; the client's 30s default would abort a long
    // ansible run. The abort must therefore fire on the remote-exec budget.
    vi.useFakeTimers()
    try {
      sessionStorage.setItem(TOKEN_KEY, 'tools-token')
      const wrapper = mount(ToolsView, { global: { plugins: [i18n] } })
      await flushPromises()
      seedFleet()
      await flushPromises()

      let captured: AbortSignal | undefined
      fetchMock.mockImplementation((_u: string, init: RequestInit) => {
        captured = init.signal as AbortSignal
        return new Promise(() => {}) // never settles — the timeout must abort it
      })

      const vm = wrapper.vm as unknown as {
        ansibleCommand: string
        selectedNode: string
        runAnsibleCommand: () => Promise<void>
      }
      vm.selectedNode = 'node-a'
      vm.ansibleCommand = 'uptime'
      vm.runAnsibleCommand()
      await Promise.resolve()

      expect(captured).toBeInstanceOf(AbortSignal)
      // Still alive well past the 30s default the client would have applied.
      vi.advanceTimersByTime(30_000 + 1_000)
      expect(captured!.aborted).toBe(false)
      // Aborted once the remote-exec budget is spent.
      vi.advanceTimersByTime(REMOTE_EXEC_TIMEOUT_MS)
      expect(captured!.aborted).toBe(true)
    } finally {
      vi.useRealTimers()
    }
  })

  it("still shows the backend's detail message when an exec is rejected", async () => {
    // `rawRequest` rather than `post()` exists for this: `post()` would have
    // flattened the body into `HTTP 502: ...` and the operator would never see
    // what the backend actually said.
    sessionStorage.setItem(TOKEN_KEY, 'tools-token')
    const wrapper = await mountTools()

    fetchMock.mockResolvedValue(jsonResponse({ detail: 'node unreachable' }, 502))
    const vm = wrapper.vm as unknown as {
      redisCommand: string
      selectTool: (id: string) => void
      runRedisCommand: () => Promise<void>
    }
    // Open the Redis panel so the error region is actually rendered.
    vm.selectTool('redis-cli')
    vm.redisCommand = 'PING'
    await vm.runRedisCommand()
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('node unreachable')
  })

  it('clears the session and redirects when an exec is rejected as unauthorised', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'expired-token')
    const wrapper = await mountTools()

    fetchMock.mockResolvedValue(jsonResponse({ detail: 'Not authenticated' }, 401))
    const vm = wrapper.vm as unknown as {
      redisCommand: string
      runRedisCommand: () => Promise<void>
    }
    vm.redisCommand = 'PING'
    await vm.runRedisCommand()
    await flushPromises()

    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(window.location.href).toBe('/login')
  })
})
