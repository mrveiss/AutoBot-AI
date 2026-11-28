// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #19887 — OrchestrationView's loaders caught their own failure and resolved with
 * []/null/void, so Promise.allSettled counted them as fulfilled, refresh() returned
 * true and the shared poller never reached POLL_CONSECUTIVE_ERROR_LIMIT: a down
 * backend polled forever with no PollingPausedAlert. Mounts the real view with every
 * read failing and asserts the poller pauses; an empty-but-successful read must not.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en.json'
import { POLL_CONSECUTIVE_ERROR_LIMIT } from '@/constants/api-timeouts'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: {}, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

import OrchestrationView from './OrchestrationView.vue'

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })
const POLL_MS = 15000

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function okBody(url: string): unknown {
  if (url.includes('/fleet/services')) return { services: [], total_services: 0 }
  if (url.includes('/nodes')) return { nodes: [] }
  if (url.includes('/roles/owners')) return { owners: {} }
  if (url.includes('/roles/fleet-health')) return {}
  if (url.includes('/roles')) return []
  if (url.includes('/orchestration/services')) return []
  return {}
}

async function runPolls(count: number) {
  for (let i = 0; i < count; i++) {
    await vi.advanceTimersByTimeAsync(POLL_MS)
    await flushPromises()
  }
}

async function mountWith(respond: (url: string) => Response) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => respond(String(url))))
  const wrapper = mount(OrchestrationView, { global: { plugins: [i18n] } })
  await flushPromises()
  await runPolls(POLL_CONSECUTIVE_ERROR_LIMIT + 2)
  return wrapper
}

describe('OrchestrationView poll failure (#19887)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    setActivePinia(createPinia())
    sessionStorage.clear()
    localStorage.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('pauses the poller and shows the paused alert when every read fails', async () => {
    const wrapper = await mountWith(() => jsonResponse({ detail: 'down' }, 500))
    expect(wrapper.findAll('[data-polling-paused]')).toHaveLength(1)
    wrapper.unmount()
  })

  it('does not pause when the reads succeed with empty results', async () => {
    const wrapper = await mountWith(url => jsonResponse(okBody(url)))
    expect(wrapper.findAll('[data-polling-paused]')).toHaveLength(0)
    wrapper.unmount()
  })
})
