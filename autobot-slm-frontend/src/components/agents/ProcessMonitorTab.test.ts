// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #13079 — ProcessMonitorTab reaches the autobot backend through
 * `useAutobotApi` instead of a private `fetch` that sent only
 * `Bearer ${authStore.token}` (no `autobot_access_token` fallback, no 401
 * cleanup, no timeout).
 *
 * The live-log WebSocket is deliberately NOT migrated — `useAutobotApi` is an
 * HTTP client and has no socket equivalent — so these tests also pin that the
 * plain-text log body still arrives verbatim rather than JSON-parsed.
 *
 * #16374 — the nginx `/autobot-api/` proxy now runs an `auth_request` session
 * check before it forwards anything, and a browser WebSocket handshake cannot
 * carry a custom `Authorization` header. `FakeWebSocket` below pins that the
 * SLM session token instead rides the `Sec-WebSocket-Protocol` subprotocol
 * list (`new WebSocket(url, ['bearer', token])`), which nginx's dedicated
 * stream location reads via `$http_sec_websocket_protocol`, and that the URL
 * itself carries no token.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import ProcessMonitorTab from './ProcessMonitorTab.vue'
import { HttpError } from '@autobot/ui'
import { backendClient } from '@/testing/mockAutobotBackendClient'
import en from '@/locales/en.json'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 'test-token' }),
}))

class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  url: string
  protocols: string | string[] | undefined
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  constructor(url: string, protocols?: string | string[]) {
    this.url = url
    this.protocols = protocols
    FakeWebSocket.instances.push(this)
  }
  close(): void {}
}
vi.stubGlobal('WebSocket', FakeWebSocket)

vi.mock('@/utils/ApiClient', async (importOriginal) =>
  (await import('@/testing/mockAutobotBackendClient')).withMockedBackendClient(importOriginal),
)

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

const PROCESS = {
  id: 'p1',
  agent_id: 'orchestrator',
  task_id: null,
  command: '/usr/bin/python3',
  args: ['script.py'],
  status: 'completed',
  exit_code: 0,
  signal: null,
  log_excerpt: 'done',
  log_path: null,
  timeout_seconds: 300,
  started_at: '2026-01-01T00:00:00Z',
  completed_at: '2026-01-01T00:00:10Z',
  created_at: '2026-01-01T00:00:00Z',
}

type Vm = {
  agentId: string
  statusFilter: string
  fullLog: string | null
  error: string | null
  fetchProcesses: () => Promise<void>
  fetchFullLog: (id: string) => Promise<void>
  signalProcess: (id: string, sig: string) => Promise<void>
  spawnProcess: () => Promise<void>
  streamLogs: (id: string) => void
  spawnForm: { agent_id: string; command: string; args: string; timeout_seconds: number }
}

function mountTab(): { vm: Vm } {
  const wrapper = mount(ProcessMonitorTab, { global: { plugins: [i18n] } })
  return { vm: wrapper.vm as unknown as Vm }
}

describe('ProcessMonitorTab transport (#13079)', () => {
  beforeEach(() => {
    backendClient.get.mockReset()
    backendClient.post.mockReset()
    backendClient.get.mockResolvedValue({ processes: [PROCESS] })
    backendClient.post.mockResolvedValue({ success: true })
  })

  it('GETs /agents/{id}/processes with the limit and the selected status filter', async () => {
    const { vm } = mountTab()
    vm.agentId = 'orchestrator'
    vm.statusFilter = 'running'

    await vm.fetchProcesses()
    await flushPromises()

    expect(backendClient.get.mock.calls[0][0]).toBe(
      '/agents/orchestrator/processes?limit=50&status=running',
    )
  })

  it('omits the status filter when "All" is selected', async () => {
    const { vm } = mountTab()
    vm.agentId = 'orchestrator'
    vm.statusFilter = ''

    await vm.fetchProcesses()

    expect(backendClient.get.mock.calls[0][0]).toBe('/agents/orchestrator/processes?limit=50')
  })

  it('requests the log as text and stores it verbatim', async () => {
    backendClient.get.mockResolvedValue('stdout line\nstderr line')
    const { vm } = mountTab()

    await vm.fetchFullLog('p1')

    const [url, config] = backendClient.get.mock.calls[0] as [string, { responseType: string }]
    expect(url).toBe('/processes/p1/logs')
    expect(config.responseType).toBe('text')
    expect(vm.fullLog).toBe('stdout line\nstderr line')
  })

  it('keeps the "Failed to load log" placeholder when the log request rejects', async () => {
    backendClient.get.mockRejectedValue(new Error('gone'))
    const { vm } = mountTab()

    await vm.fetchFullLog('p1')

    expect(vm.fullLog).toBe('Failed to load log')
  })

  it('POSTs the signal name and surfaces the backend detail on failure', async () => {
    const { vm } = mountTab()
    vm.agentId = 'orchestrator'

    await vm.signalProcess('p1', 'SIGKILL')

    expect(backendClient.post.mock.calls[0].slice(0, 2)).toEqual([
      '/processes/p1/signal',
      { signal: 'SIGKILL' },
    ])

    backendClient.post.mockRejectedValue(new HttpError(409, 'Error', { detail: 'process already exited' }))
    await vm.signalProcess('p1', 'SIGTERM')

    expect(vm.error).toBe('process already exited')
  })

  it('POSTs the spawn payload with args split into a list', async () => {
    const { vm } = mountTab()
    vm.agentId = 'orchestrator'
    vm.spawnForm.command = '/usr/bin/python3'
    vm.spawnForm.args = 'script.py --flag'
    vm.spawnForm.timeout_seconds = 120

    await vm.spawnProcess()

    expect(backendClient.post.mock.calls[0].slice(0, 2)).toEqual([
      '/processes/spawn',
      {
        agent_id: 'orchestrator',
        command: '/usr/bin/python3',
        args: ['script.py', '--flag'],
        timeout_seconds: 120,
      },
    ])
  })

  it('carries the SLM session token as a WebSocket subprotocol, never the URL (#16374)', () => {
    FakeWebSocket.instances.length = 0
    const { vm } = mountTab()

    vm.streamLogs('p1')

    expect(FakeWebSocket.instances).toHaveLength(1)
    const socket = FakeWebSocket.instances[0]
    expect(socket.url).toContain('/processes/p1/stream')
    expect(socket.url).not.toContain('test-token')
    expect(socket.url).not.toContain('?')
    expect(socket.protocols).toEqual(['bearer', 'test-token'])
  })
})
