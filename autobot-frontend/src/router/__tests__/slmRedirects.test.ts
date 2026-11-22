// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #20605: the main app's old /slm/* URLs send a bookmark to the SLM console, where the
// theme manager and the remote-desktop tool live now. They are slmRedirectRoutes entries (#20631):
// the guard leaves for the SLM and cancels the in-app navigation.

import { describe, it, expect, vi, afterEach } from 'vitest'
import type { RouteRecordRaw } from 'vue-router'
import { routes } from '@/router'

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get: vi.fn().mockResolvedValue([]) }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ error: vi.fn(), info: vi.fn(), warn: vi.fn(), debug: vi.fn() }),
}))
vi.mock('@/config/ssot-config', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/config/ssot-config')>()),
  getSLMAdminUrl: () => 'https://slm.example',
}))

const originalLocation = window.location

afterEach(() => {
  Object.defineProperty(window, 'location', { value: originalLocation, configurable: true })
})

/** Runs the record's guard and reports where it sent the browser and what it answered the router. */
function followRedirect(path: string): { href: string; fallback: unknown } {
  const record = routes.find((r: RouteRecordRaw) => r.path === path)
  expect(record, `route ${path}`).toBeDefined()
  const guard = record?.beforeEnter as () => unknown
  const fake = { href: '' }
  Object.defineProperty(window, 'location', { value: fake, configurable: true })
  const fallback = guard()
  return { href: fake.href, fallback }
}

describe('/slm/* routes of the main app (#20605)', () => {
  it('/slm/themes opens the SLM Themes screen and cancels the in-app navigation', () => {
    expect(followRedirect('/slm/themes')).toEqual({ href: 'https://slm.example/settings/admin/themes', fallback: false })
  })

  it('/slm/tools/novnc opens the SLM remote desktop tool and cancels the in-app navigation', () => {
    expect(followRedirect('/slm/tools/novnc')).toEqual({ href: 'https://slm.example/tools/novnc', fallback: false })
  })

  it('neither is a view of this app any more', () => {
    for (const path of ['/slm/themes', '/slm/tools/novnc']) {
      const record = routes.find((r: RouteRecordRaw) => r.path === path)
      const view = record?.component as { render: () => unknown } | undefined
      expect(view?.render(), path).toBeNull()
    }
  })
})
