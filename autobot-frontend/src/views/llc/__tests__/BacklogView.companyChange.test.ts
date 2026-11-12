// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * What the backlog says about a failed load or refresh (#21032).
 *
 * - a fetch failure is its own state with a Retry, not the empty-list "No items match";
 * - the "created, but the list did not refresh" warning belongs to one company: switching company drops
 *   it, and a refresh still in flight for the previous company cannot bring it back.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
const post = vi.fn()
const route = await vi.hoisted(async () => {
  const { reactive } = await import('vue')
  return reactive({ params: { companyId: 'c1' } })
})

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get, post }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))
vi.mock('vue-router', () => ({ useRoute: () => route, useRouter: () => ({ push: vi.fn() }) }))

import BacklogView from '../BacklogView.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function serve(backlog: () => Promise<unknown>) {
  get.mockImplementation((url?: string) => {
    if (url?.includes('/api/llc/backlog')) return backlog()
    if (url?.includes('/projects')) return Promise.resolve([])
    return Promise.resolve({})
  })
}

async function mountView() {
  const wrapper = mount(BacklogView, {
    global: { plugins: [i18n], stubs: { LlcBreadcrumb: true, 'router-link': true, BacklogHierarchyPanel: true } },
  })
  await flushPromises()
  return wrapper
}

const created = (wrapper: Awaited<ReturnType<typeof mountView>>) =>
  wrapper.findComponent({ name: 'BacklogCreateModal' }).vm.$emit('created', { id: 'wi-new' })

describe('BacklogView load failure and company change (#21032)', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
    route.params.companyId = 'c1'
  })

  it('shows a fetch failure with a Retry instead of "No items match"', async () => {
    serve(() => Promise.reject(new Error('down')))
    const wrapper = await mountView()

    expect(wrapper.text()).toContain(en.llc.backlog.fetchFailed)
    expect(wrapper.text()).not.toContain(en.llc.backlog.noMatch)

    serve(() => Promise.resolve({ items: [] }))
    await wrapper.get('[data-testid="retry-load"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).not.toContain(en.llc.backlog.fetchFailed)
    expect(wrapper.text()).toContain(en.llc.backlog.noMatch)
  })

  it('drops the create-refresh warning when the company changes', async () => {
    serve(() => Promise.resolve({ items: [] }))
    const wrapper = await mountView()
    serve(() => Promise.reject(new Error('down')))
    created(wrapper)
    await flushPromises()
    expect(wrapper.text()).toContain(en.llc.backlog.createdRefreshFailed)

    serve(() => Promise.resolve({ items: [] }))
    route.params.companyId = 'c2'
    await nextTick()
    await flushPromises()
    expect(wrapper.text()).not.toContain(en.llc.backlog.createdRefreshFailed)
  })

  it('does not let a refresh from before the company change restore the warning', async () => {
    serve(() => Promise.resolve({ items: [] }))
    const wrapper = await mountView()
    const earlier = deferred<unknown>()
    serve(() => earlier.promise)
    created(wrapper) // the create-refresh for c1 is in flight

    serve(() => Promise.resolve({ items: [] }))
    route.params.companyId = 'c2'
    await nextTick()
    await flushPromises()

    earlier.reject(new Error('down')) // ...and fails after the user has moved on
    await flushPromises()
    expect(wrapper.text()).not.toContain(en.llc.backlog.createdRefreshFailed)
    expect(wrapper.text()).not.toContain(en.llc.backlog.fetchFailed)
  })
})
