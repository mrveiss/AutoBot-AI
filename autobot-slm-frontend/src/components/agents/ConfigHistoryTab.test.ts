// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #13079 — ConfigHistoryTab reaches the autobot backend through
 * `useAutobotApi` instead of a private `fetch` that sent only
 * `Bearer ${authStore.token}`. The client is mocked with the shared
 * `mockAutobotBackendClient` double: methods resolve the parsed body and failures
 * are the kit `HttpError`.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import ConfigHistoryTab from './ConfigHistoryTab.vue'
import { HttpError } from '@autobot/ui'
import { backendClient } from '@/testing/mockAutobotBackendClient'
import en from '@/locales/en.json'

vi.mock('@/utils/ApiClient', async (importOriginal) =>
  (await import('@/testing/mockAutobotBackendClient')).withMockedBackendClient(importOriginal),
)

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

const REVISION = {
  id: 'rev-9',
  entity_type: 'agent',
  entity_id: 'orchestrator',
  before_config: { retries: 1 },
  after_config: { retries: 3 },
  changed_keys: ['retries'],
  source: 'api',
  created_by: 'ops',
  created_at: '2026-01-01T00:00:00Z',
}

type Vm = {
  entityType: string
  entityId: string
  revisions: unknown[]
  error: string | null
  fetchRevisions: () => Promise<void>
  rollback: (id: string) => Promise<void>
}

function mountTab(): Vm {
  return mount(ConfigHistoryTab, { global: { plugins: [i18n] } }).vm as unknown as Vm
}

describe('ConfigHistoryTab transport (#13079)', () => {
  beforeEach(() => {
    backendClient.get.mockReset()
    backendClient.post.mockReset()
    backendClient.get.mockResolvedValue([REVISION])
    backendClient.post.mockResolvedValue({ success: true })
  })

  it('GETs /config-revisions/{type}/{id} with the limit', async () => {
    const vm = mountTab()
    vm.entityType = 'agent'
    vm.entityId = 'orchestrator'

    await vm.fetchRevisions()
    await flushPromises()

    expect(backendClient.get.mock.calls[0][0]).toBe('/config-revisions/agent/orchestrator?limit=50')
    expect(vm.revisions).toHaveLength(1)
  })

  it('makes no request until an entity id is supplied', async () => {
    const vm = mountTab()
    vm.entityId = ''

    await vm.fetchRevisions()

    expect(backendClient.get).not.toHaveBeenCalled()
  })

  it('POSTs the rollback path and reloads the timeline', async () => {
    const vm = mountTab()
    vm.entityType = 'agent'
    vm.entityId = 'orchestrator'
    await vm.fetchRevisions()
    backendClient.get.mockClear()

    await vm.rollback('rev-9')
    await flushPromises()

    expect(backendClient.post.mock.calls[0][0]).toBe(
      '/config-revisions/agent/orchestrator/rev-9/rollback',
    )
    expect(backendClient.get.mock.calls[0][0]).toBe('/config-revisions/agent/orchestrator?limit=50')
  })

  it('surfaces the backend detail when a rollback is refused', async () => {
    const vm = mountTab()
    vm.entityType = 'agent'
    vm.entityId = 'orchestrator'
    backendClient.post.mockRejectedValue(new HttpError(409, 'Error', { detail: 'revision is not rollbackable' }))

    await vm.rollback('rev-9')

    expect(vm.error).toBe('revision is not rollbackable')
  })

  it('surfaces the backend detail when the timeline load fails', async () => {
    const vm = mountTab()
    vm.entityType = 'agent'
    vm.entityId = 'orchestrator'
    backendClient.get.mockRejectedValue(new HttpError(404, 'Error', { detail: 'no such entity' }))

    await vm.fetchRevisions()

    expect(vm.error).toBe('no such entity')
    expect(vm.revisions).toEqual([])
  })
})
