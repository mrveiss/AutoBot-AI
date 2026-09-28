// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The backlog request carries the selected project (#17680).
 *
 * `GET /api/llc/backlog` has accepted and honoured a `project_id` filter since
 * it was written, plumbed through to `list_backlog`. This view was its only
 * caller and sent `company_id` alone, so "the project backlog" was always the
 * whole company's backlog, for every project.
 *
 * WHY THESE ASSERT THE REQUEST AND NOT THE RENDERED LIST. The same defect shape
 * was fixed hours earlier in #17651, where an index call omitted `source_id`
 * and every panel filtered on it. Both sides were internally consistent and no
 * test on either side could see the gap, because nobody checked what was
 * actually sent. Asserting a shorter list would pass against a client-side
 * filter over a page the server already truncated at `limit=50` -- which is the
 * wrong fix and indistinguishable from the right one by outcome alone.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const post = vi.fn()
const get = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get, post }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { companyId: 'c1' } }),
  useRouter: () => ({ push: vi.fn() }),
}))

import BacklogView from '../BacklogView.vue'

interface BacklogVm {
  projectFilterId: string
}

const PROJECTS = [
  { id: 'proj-1', name: 'First', lifecycle_state: 'active' },
  { id: 'proj-2', name: 'Second', lifecycle_state: 'active' },
]

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

function routeGet(url?: string) {
  if (url?.includes('/projects')) return Promise.resolve(PROJECTS)
  if (url?.includes('/backlog')) return Promise.resolve({ items: [] })
  return Promise.resolve({ items: [] })
}

async function mountView() {
  get.mockImplementation(routeGet)
  const wrapper = mount(BacklogView, {
    global: { plugins: [i18n], stubs: { LlcBreadcrumb: true, 'router-link': true } },
  })
  await flushPromises()
  return wrapper
}

function backlogUrls(): string[] {
  return get.mock.calls
    .map(call => call[0] as string)
    .filter(url => typeof url === 'string' && url.includes('/backlog'))
}

describe('BacklogView project filter (#17680)', () => {
  beforeEach(() => {
    post.mockReset()
    get.mockReset()
  })

  it('omits project_id when no project is selected, keeping the company view', async () => {
    await mountView()

    const urls = backlogUrls()
    expect(urls).toHaveLength(1)
    expect(urls[0]).toContain('company_id=c1')
    expect(urls[0]).not.toContain('project_id')
  })

  it('sends project_id once a project is selected', async () => {
    const wrapper = await mountView()

    ;(wrapper.vm as unknown as BacklogVm).projectFilterId = 'proj-2'
    await flushPromises()

    const urls = backlogUrls()
    expect(urls).toHaveLength(2)
    expect(urls[1]).toContain('project_id=proj-2')
    expect(urls[1]).toContain('company_id=c1')
  })

  it('drops project_id again when the selection is cleared', async () => {
    const wrapper = await mountView()
    const vm = wrapper.vm as unknown as BacklogVm

    vm.projectFilterId = 'proj-1'
    await flushPromises()
    vm.projectFilterId = ''
    await flushPromises()

    const urls = backlogUrls()
    expect(urls).toHaveLength(3)
    expect(urls[2]).not.toContain('project_id')
  })

  it('loads the project list on mount, not only when the assign modal opens', async () => {
    // The filter needs its options before any interaction; `loadProjects` used
    // to be reachable only through `openBulkAssign`.
    await mountView()

    const projectListCalls = get.mock.calls
      .map(call => call[0] as string)
      .filter(url => typeof url === 'string' && url.includes('/companies/c1/projects'))
    expect(projectListCalls).toHaveLength(1)
  })

  it('offers every non-archived project as a filter option', async () => {
    const wrapper = await mountView()

    const options = wrapper.findAll('.backlog-filters select')[0].findAll('option')
    expect(options[0].text()).toBe(en.llc.backlog.allProjects)
    expect(options.map(o => o.text())).toContain('First')
    expect(options.map(o => o.text())).toContain('Second')
  })
})
