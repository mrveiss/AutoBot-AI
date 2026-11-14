// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #18353: every string the System status panel shows comes from i18n. Rows
 * carry keys and render in the active locale -- relabelled on a language
 * switch without a new poll -- and backend text outside the known vocabulary
 * passes through untouched rather than as a missing key.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const fetchWithFallback = vi.fn()

vi.mock('@/utils/ApiEndpointMapper.js', () => ({
  default: { fetchWithFallback: (...a: unknown[]) => fetchWithFallback(...a) },
}))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api' }))
vi.mock('@/composables/usePollingJob', () => ({
  usePollingJob: () => ({ start: vi.fn(), stop: vi.fn() }),
}))

import { useSystemStatus } from '../useSystemStatus'
import i18n from '@/i18n'

const files = import.meta.glob('@/i18n/locales/*.json', { eager: true, import: 'default' }) as Record<
  string,
  Record<string, unknown>
>
const locales = Object.fromEntries(
  Object.entries(files).map(([p, m]) => [p.split('/').pop()!.replace('.json', ''), m]),
) as Record<string, { systemStatus: Record<string, Record<string, string>>; status: Record<string, string> }>
for (const [code, messages] of Object.entries(locales)) i18n.global.setLocaleMessage(code, messages as never)

const jsonOk = (body: unknown) => ({ ok: true, status: 200, fallback: false, json: async () => body })

/** One poll: a known message, an HTTP code, a raw exception text, a shared status word. */
function poll() {
  fetchWithFallback.mockImplementation(async (url: string) =>
    url.endsWith('/vms/status')
      ? jsonOk({
          vms: [
            { name: 'Redis', status: 'online', message: 'Running' },
            { name: 'NPU Worker', status: 'offline', message: 'HTTP 503' },
            { name: 'Browser Service', status: 'offline', message: 'ECONNRESET at socket 7' },
          ],
        })
      : jsonOk({ services: { ollama: { status: 'healthy', health: 'healthy' } } }),
  )
}

const flat = (o: unknown, p = ''): string[] =>
  typeof o === 'object' && o ? Object.entries(o).flatMap(([k, v]) => flat(v, p ? `${p}.${k}` : k)) : [p]

describe('System status text (#18353)', () => {
  beforeEach(() => {
    fetchWithFallback.mockReset()
    poll()
  })
  afterEach(() => {
    i18n.global.locale.value = 'en'
  })

  it.each(['en', 'de'])('%s: names and states render from the locale, raw backend text passes through', async (code) => {
    i18n.global.locale.value = code as never
    const s = locales[code].systemStatus
    const { systemServices, refreshSystemStatus } = useSystemStatus()
    await refreshSystemStatus()
    const byId = Object.fromEntries(systemServices.value.map((r) => [r.id, r]))

    expect(byId.redis.name).toBe(s.service.redis)
    expect(byId.redis.statusText).toBe(s.state.running)
    expect(byId.npu_worker.statusText).toBe(s.state.http.replace('{code}', '503'))
    expect(byId.browser.statusText).toBe('ECONNRESET at socket 7')
    expect(byId.ollama.statusText).toBe(locales[code].status.healthy)
    expect(byId.websocket.statusText).toBe(s.state.connected)
  })

  it.each(['en', 'de'])('%s: the summary and the pluralised description', async (code) => {
    i18n.global.locale.value = code as never
    const s = locales[code].systemStatus
    const status = useSystemStatus()
    await status.refreshSystemStatus()

    expect(status.getSystemStatusText()).toBe(s.summary.issues)
    expect(status.getSystemStatusTooltip()).toBe(s.tooltip.issues)
    const down = s.description.servicesDown.split(' | ')[1].replace('{n}', '2')
    const warnings = s.description.warnings.split(' | ')[1].replace('{n}', '0')
    expect(status.getSystemStatusDescription()).toBe(
      s.description.downAndWarnings.replace('{down}', down).replace('{warnings}', warnings),
    )
  })

  it('relabels on a language switch without a new poll', async () => {
    const { systemServices, refreshSystemStatus } = useSystemStatus()
    await refreshSystemStatus()
    const calls = fetchWithFallback.mock.calls.length
    const redis = () => systemServices.value.find((r) => r.id === 'redis')!.name

    expect(redis()).toBe(locales.en.systemStatus.service.redis)
    i18n.global.locale.value = 'lv' as never
    expect(systemServices.value.find((r) => r.id === 'npu_worker')!.name).toBe(locales.lv.systemStatus.service.npu_worker)
    expect(fetchWithFallback.mock.calls.length).toBe(calls)
  })

  it('every locale carries the full systemStatus key set', () => {
    const en = flat(locales.en.systemStatus).sort()
    expect(en.length).toBeGreaterThan(40)
    for (const [code, messages] of Object.entries(locales)) {
      expect(flat(messages.systemStatus).sort(), code).toEqual(en)
    }
  })
})
