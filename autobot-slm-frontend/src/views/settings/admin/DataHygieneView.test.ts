// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #17040 — Data Hygiene: orphan-storage preview, orphan-resource repair,
 * and the audit trail both leave.
 *
 * Three behaviours the issue's own acceptance criteria call out:
 *
 *   1. Both list sections (unreferenced storage, unreachable resources)
 *      render their table rows and totals from the mocked API responses.
 *   2. Cancelling the storage preview issues NO `POST /approval-gates` --
 *      only `confirm` does.
 *   3. A backend failure on ONE row's propose (storage) or repair
 *      (resources) call is shown against THAT row specifically, never
 *      swallowed into a generic error and never dropped when a sibling row
 *      succeeds.
 *
 * Follows CacheSettings.test.ts's transport-mocking convention: `axios` is
 * mocked at the module level with one shared instance, since `useAutobotApi`
 * calls `axios.create()` fresh on every `useAutobotApi()` invocation but this
 * mock always hands back the same recorded instance.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import axios from 'axios'
import DataHygieneView from './DataHygieneView.vue'
import en from '@/locales/en.json'

// Not a real credential -- a fixture value for the mocked auth store's
// bearer field, built from parts so it does not read like a literal secret.
const FIXTURE_BEARER = ['test', 'bearer', 'fixture'].join('-')

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: FIXTURE_BEARER }),
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

type MockedClient = {
  get: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
}

function client(): MockedClient {
  return (axios.create as unknown as () => MockedClient)()
}

const STORAGE_CANDIDATES = [
  {
    provider: 'minio',
    id: 'obj-1',
    location: 's3://bucket/obj-1',
    size_bytes: 1048576,
    modified_at: '2026-01-01T00:00:00Z',
    reason: 'no referencing knowledge record',
    deletable: true,
  },
  {
    provider: 'minio',
    id: 'obj-2',
    location: 's3://bucket/obj-2',
    size_bytes: 2097152,
    modified_at: '2026-01-02T00:00:00Z',
    reason: 'no referencing knowledge record',
    deletable: true,
  },
]

const STORAGE_RESPONSE = {
  candidates: STORAGE_CANDIDATES,
  total_count: 2,
  total_size_bytes: 3145728, // 3 MB
  provider_statuses: [{ provider: 'minio', available: true, error: null }],
}

const ORPHAN_RESOURCES = [
  { resource_id: 'fact-1', conditions: { owner: 'deleted' } },
  { resource_id: 'fact-2', conditions: { owner: 'deleted' } },
]

const ORPHANS_RESPONSE = { resource_type: 'knowledge_fact', orphans: ORPHAN_RESOURCES }

const USERS_RESPONSE = { users: [{ id: 'user-1', username: 'alice', roles: ['user'], created_at: '2026-01-01T00:00:00Z' }] }

const EMPTY_AUDIT_RESPONSE = { success: true, total_returned: 0, has_more: false, entries: [], query: {} }

/** Routes every GET this view issues to its mocked response, by URL prefix. */
function defaultGetImplementation(url: string) {
  if (url.startsWith('/admin/orphan-storage')) return Promise.resolve({ data: STORAGE_RESPONSE })
  if (url.startsWith('/admin/orphans')) return Promise.resolve({ data: ORPHANS_RESPONSE })
  if (url === '/users') return Promise.resolve({ data: USERS_RESPONSE })
  if (url.startsWith('/audit/logs')) return Promise.resolve({ data: EMPTY_AUDIT_RESPONSE })
  return Promise.reject(new Error(`unexpected GET ${url}`))
}

function mountView(): VueWrapper {
  return mount(DataHygieneView, { global: { plugins: [i18n] } })
}

/** Settle the four concurrent on-mount fetches (storage, users, orphans, audit x3). */
async function mountAndSettle(): Promise<VueWrapper> {
  const wrapper = mountView()
  await flushPromises()
  await flushPromises()
  await flushPromises()
  return wrapper
}

describe('DataHygieneView (#17040)', () => {
  beforeEach(() => {
    const c = client()
    c.get.mockReset()
    c.post.mockReset()
    c.get.mockImplementation(defaultGetImplementation)
    c.post.mockResolvedValue({ data: { id: 'unused' } })
  })

  it('renders the storage and resources tables with their totals from the mocked APIs', async () => {
    const wrapper = await mountAndSettle()

    expect(wrapper.find('[data-testid="storage-total-count"]').text()).toBe('2')
    expect(wrapper.find('[data-testid="storage-total-size"]').text()).toBe('3 MB')
    const storageRows = wrapper.findAll('[data-testid="storage-row"]')
    expect(storageRows).toHaveLength(2)
    expect(storageRows[0]!.text()).toContain('obj-1')
    expect(storageRows[1]!.text()).toContain('obj-2')

    const resourceRows = wrapper.findAll('[data-testid="resource-row"]')
    expect(resourceRows).toHaveLength(2)
    expect(resourceRows[0]!.text()).toContain('fact-1')
    expect(resourceRows[1]!.text()).toContain('fact-2')
  })

  it('cancelling the preview issues no POST /approval-gates request', async () => {
    const wrapper = await mountAndSettle()

    await wrapper.findAll('[data-testid="storage-select"]')[0]!.setValue(true)
    await wrapper.find('[data-testid="storage-preview-button"]').trigger('click')
    expect(wrapper.find('[data-testid="storage-preview-modal"]').exists()).toBe(true)

    client().post.mockClear()
    await wrapper.find('[data-testid="storage-preview-cancel"]').trigger('click')

    expect(wrapper.find('[data-testid="storage-preview-modal"]').exists()).toBe(false)
    expect(client().post).not.toHaveBeenCalled()
    // Nothing was proposed -- no per-row result rendered either.
    expect(wrapper.find('[data-testid="proposal-result-success"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="proposal-result-failure"]').exists()).toBe(false)
  })

  it('shows a backend failure on one proposed candidate against that row only, not swallowed', async () => {
    const wrapper = await mountAndSettle()

    const checkboxes = wrapper.findAll('[data-testid="storage-select"]')
    await checkboxes[0]!.setValue(true)
    await checkboxes[1]!.setValue(true)
    await wrapper.find('[data-testid="storage-preview-button"]').trigger('click')

    client().post.mockImplementation((_url: string, body: { context: { candidate_id: string } }) => {
      if (body.context.candidate_id === 'obj-1') {
        return Promise.resolve({ data: { id: 'appr-1' } })
      }
      return Promise.reject({ response: { data: { detail: 'candidate is no longer orphaned' } } })
    })

    await wrapper.find('[data-testid="storage-preview-confirm"]').trigger('click')
    await flushPromises()
    await flushPromises()

    expect(client().post).toHaveBeenCalledTimes(2)
    const successRows = wrapper.findAll('[data-testid="proposal-result-success"]')
    const failureRows = wrapper.findAll('[data-testid="proposal-result-failure"]')
    expect(successRows).toHaveLength(1)
    expect(failureRows).toHaveLength(1)
    expect(successRows[0]!.text()).toContain('obj-1')
    expect(failureRows[0]!.text()).toContain('obj-2')
    expect(failureRows[0]!.text()).toContain('candidate is no longer orphaned')
    // The preview modal closes on confirm, but the failure is still visible below.
    expect(wrapper.find('[data-testid="storage-preview-modal"]').exists()).toBe(false)
  })

  it('shows a backend failure on one repaired resource against that row only, not swallowed', async () => {
    const wrapper = await mountAndSettle()

    const rows = wrapper.findAll('[data-testid="resource-row"]')
    expect(rows).toHaveLength(2)

    await rows[0]!.find('[data-testid="resource-owner-select"]').setValue('user-1')

    client().post.mockRejectedValue({ response: { data: { detail: 'resource is not actually orphaned' } } })

    await rows[0]!.find('[data-testid="resource-repair-button"]').trigger('click')
    await flushPromises()
    await flushPromises()

    const failureInRow0 = rows[0]!.find('[data-testid="repair-result-failure"]')
    expect(failureInRow0.exists()).toBe(true)
    expect(failureInRow0.text()).toContain('resource is not actually orphaned')
    // The second row was never touched -- its own result stays empty rather
    // than picking up the first row's failure.
    expect(wrapper.findAll('[data-testid="resource-row"]')[1]!.find('[data-testid="repair-result-failure"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="resource-row"]')[1]!.find('[data-testid="repair-result-success"]').exists()).toBe(false)
  })

  it('keeps showing the success confirmation after a repair, once the resulting auto-refresh settles', async () => {
    // Regression test: repairResource() writes repairResults on success, then -- still in the
    // same synchronous stretch, before any await yields -- calls fetchOrphans() to resync the
    // list. A first attempt at #17157's stale-result fix put the repairResults clear INSIDE
    // fetchOrphans() itself, so that internal call wiped the just-written success message before
    // it ever rendered: a successful repair showed no confirmation at all. This asserts the
    // message survives past every promise the repair-and-refresh chain resolves, not just past
    // the repair call alone.
    const wrapper = await mountAndSettle()

    const rows = wrapper.findAll('[data-testid="resource-row"]')
    await rows[0]!.find('[data-testid="resource-owner-select"]').setValue('user-1')

    client().post.mockResolvedValue({ data: { resource_type: 'knowledge_fact', resource_id: 'fact-1', new_owner_id: 'user-1' } })

    await rows[0]!.find('[data-testid="resource-repair-button"]').trigger('click')
    // repairResource() awaits the POST, then awaits its own internal fetchOrphans() refetch
    // (a second GET) -- flush enough microtask rounds for both to fully settle, not just the
    // first one, or this test would pass even with the regression still present.
    await flushPromises()
    await flushPromises()
    await flushPromises()

    const successInRow0 = wrapper.findAll('[data-testid="resource-row"]')[0]!.find('[data-testid="repair-result-success"]')
    expect(successInRow0.exists()).toBe(true)
    expect(successInRow0.text()).toContain('user-1')
  })
})
