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
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import axios from 'axios'
import ProcessMonitorTab from './ProcessMonitorTab.vue'
import en from '@/locales/en.json'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 'test-token' }),
}))

vi.mock('axios', () => {
  const instance = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: { use: () => undefined },
      response: { use: () => undefined },
    },
  }
  return { default: { create: () => instance } }
})

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

type MockedClient = { get: ReturnType<typeof vi.fn>; post: ReturnType<typeof vi.fn> }

function client(): MockedClient {
  return (axios.create as unknown as () => MockedClient)()
}

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
  spawnForm: { agent_id: string; command: string; args: string; timeout_seconds: number }
}

function mountTab(): { vm: Vm } {
  const wrapper = mount(ProcessMonitorTab, { global: { plugins: [i18n] } })
  return { vm: wrapper.vm as unknown as Vm }
}

describe('ProcessMonitorTab transport (#13079)', () => {
  beforeEach(() => {
    const c = client()
    c.get.mockReset()
    c.post.mockReset()
    c.get.mockResolvedValue({ data: { processes: [PROCESS] }, status: 200 })
    c.post.mockResolvedValue({ data: { success: true }, status: 200 })
  })

  it('GETs /agents/{id}/processes with the limit and the selected status filter', async () => {
    const { vm } = mountTab()
    vm.agentId = 'orchestrator'
    vm.statusFilter = 'running'

    await vm.fetchProcesses()
    await flushPromises()

    expect(client().get.mock.calls[0][0]).toBe(
      '/agents/orchestrator/processes?limit=50&status=running',
    )
  })

  it('omits the status filter when "All" is selected', async () => {
    const { vm } = mountTab()
    vm.agentId = 'orchestrator'
    vm.statusFilter = ''

    await vm.fetchProcesses()

    expect(client().get.mock.calls[0][0]).toBe('/agents/orchestrator/processes?limit=50')
  })

  it('requests the log as text and stores it verbatim', async () => {
    client().get.mockResolvedValue({ data: 'stdout line\nstderr line', status: 200 })
    const { vm } = mountTab()

    await vm.fetchFullLog('p1')

    const [url, config] = client().get.mock.calls[0] as [string, { responseType: string }]
    expect(url).toBe('/processes/p1/logs')
    expect(config.responseType).toBe('text')
    expect(vm.fullLog).toBe('stdout line\nstderr line')
  })

  it('keeps the "Failed to load log" placeholder when the log request rejects', async () => {
    client().get.mockRejectedValue(new Error('gone'))
    const { vm } = mountTab()

    await vm.fetchFullLog('p1')

    expect(vm.fullLog).toBe('Failed to load log')
  })

  it('POSTs the signal name and surfaces the backend detail on failure', async () => {
    const { vm } = mountTab()
    vm.agentId = 'orchestrator'

    await vm.signalProcess('p1', 'SIGKILL')

    expect(client().post.mock.calls[0].slice(0, 2)).toEqual([
      '/processes/p1/signal',
      { signal: 'SIGKILL' },
    ])

    client().post.mockRejectedValue({ response: { data: { detail: 'process already exited' } } })
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

    expect(client().post.mock.calls[0].slice(0, 2)).toEqual([
      '/processes/spawn',
      {
        agent_id: 'orchestrator',
        command: '/usr/bin/python3',
        args: ['script.py', '--flag'],
        timeout_seconds: 120,
      },
    ])
  })
})
