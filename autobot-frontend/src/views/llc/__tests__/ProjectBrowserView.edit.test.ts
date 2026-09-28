// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * A project can be edited, through the route that already existed (#17681).
 *
 * `PATCH /api/llc/projects/{id}` (`llc/api/sprints.py:685`) has worked since it
 * was written and no frontend called it, so projects were write-once at
 * creation. The owner reported it as "I can create a project but can't edit
 * it", which was exactly right.
 *
 * WHY THESE ASSERT THE REQUEST BODY AND NOT THE RENDERED CARD. `update_project`
 * applies `model_dump(exclude_none=True)`, so an unchanged value is a silent
 * no-op write and a `null` does nothing at all (#17694). A test that only
 * checked the card updated would pass against a handler that sent every field
 * every time -- which works, and quietly rewrites values the user did not
 * touch. The body is the thing under test.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
const post = vi.fn()
const patch = vi.fn()
const del = vi.fn()

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
const mountOpts = { global: { plugins: [i18n], stubs: { LlcBreadcrumb: true } } }

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get, post, patch, delete: del }),
}))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { companyId: 'c1', programId: 'pr1' } }),
  RouterLink: { template: '<a><slot /></a>' },
}))
vi.mock('@autobot/ui', () => ({
  BaseModal: {
    name: 'BaseModal',
    props: ['modelValue', 'title', 'size'],
    template: '<div v-if="modelValue" class="modal-stub"><slot /><slot name="actions" /></div>',
  },
}))

import ProjectBrowserView from '../ProjectBrowserView.vue'

// `status` is a real member of the `projectstatus` DB enum. The neighbouring
// lifecycle fixtures use 'active', which is not one -- harmless there, wrong
// for a test that drives the status control.
const PROJECT = {
  id: 'p-1',
  company_id: 'c1',
  program_id: 'pr1',
  goal_id: null,
  name: 'Original name',
  description: 'Original description',
  status: 'planned',
  lifecycle_state: 'active',
  lead_agent_id: null,
  lead_user_id: null,
  target_date: null,
  auto_rollover: false,
  created_at: '2026-01-01',
  updated_at: '2026-01-01',
  open_work_item_count: 2,
  active_sprint_name: null,
  code_source_id: null,
  code_source: null,
}

const P = en.llcBrowser.projects

function stubGet() {
  get.mockImplementation((url?: string) => {
    if (url?.endsWith('/projects')) return Promise.resolve([{ ...PROJECT }])
    if (url?.includes('/velocity')) return Promise.resolve({ sprints: [] })
    return Promise.resolve([])
  })
}

function byText(wrapper: ReturnType<typeof mount>, text: string) {
  return wrapper.findAll('button').find(b => b.text().includes(text))
}

async function openEditor() {
  stubGet()
  const wrapper = mount(ProjectBrowserView, mountOpts)
  await flushPromises()
  await byText(wrapper, P.edit)!.trigger('click')
  await flushPromises()
  return wrapper
}

describe('ProjectBrowserView edit (#17681)', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
    patch.mockReset()
    del.mockReset()
  })

  it('offers an Edit action on a project', async () => {
    stubGet()
    const wrapper = mount(ProjectBrowserView, mountOpts)
    await flushPromises()

    expect(byText(wrapper, P.edit)).toBeDefined()
  })

  it('prefills the form from the project rather than from blanks', async () => {
    const wrapper = await openEditor()

    const inputs = wrapper.findAll('input')
    expect(inputs.some(i => (i.element as HTMLInputElement).value === 'Original name')).toBe(true)
    expect((wrapper.find('textarea').element as HTMLTextAreaElement).value).toBe(
      'Original description',
    )
    expect((wrapper.find('select').element as HTMLSelectElement).value).toBe('planned')
  })

  it('offers exactly the five values of the projectstatus enum', async () => {
    // Read off `llc/models/sprint.py:118-131`. A sixth option, or a missing
    // one, means the form and the column have drifted -- and the API takes an
    // unvalidated string, so the database is the only thing that would object
    // (#17694).
    const wrapper = await openEditor()

    const options = wrapper.find('select').findAll('option').map(o => o.attributes('value'))
    expect(options).toEqual(['backlog', 'planned', 'in_progress', 'completed', 'cancelled'])
  })

  it('PATCHes only the fields that changed', async () => {
    patch.mockResolvedValue({ ...PROJECT, name: 'New name' })
    const wrapper = await openEditor()

    const nameInput = wrapper.findAll('input').find(
      i => (i.element as HTMLInputElement).value === 'Original name',
    )!
    await nameInput.setValue('New name')
    await byText(wrapper, P.saveAction)!.trigger('click')
    await flushPromises()

    expect(patch).toHaveBeenCalledTimes(1)
    const [url, body] = patch.mock.calls[0]
    expect(url).toBe('/api/llc/projects/p-1')
    // The whole point: description, status, target_date and auto_rollover are
    // untouched and must not be in the request.
    expect(body).toEqual({ name: 'New name' })
  })

  it('sends nothing at all when nothing was changed', async () => {
    // The contrast case. Without it, "only changed fields" is satisfied by a
    // handler that always sends every field, since every field would then
    // legitimately differ from nothing.
    const wrapper = await openEditor()

    await byText(wrapper, P.saveAction)!.trigger('click')
    await flushPromises()

    expect(patch).not.toHaveBeenCalled()
  })

  it('reloads the list from the server rather than trusting the PATCH response', async () => {
    // The response is deliberately neither typed nor read: naming a response
    // type at the call site is a shape claim TypeScript cannot check, and
    // `frontend_api_contract_ratchet` counts those on a shrink-only pin. So the
    // list is refetched, matching what create and delete already do here.
    //
    // Asserting the REFETCH and not just the rendered name, because a handler
    // that read the response would also end up showing 'Renamed' -- the two are
    // indistinguishable by output alone, which is the whole reason this test
    // names the mechanism.
    patch.mockResolvedValue({ ...PROJECT, name: 'ignored-if-read' })
    let served = { ...PROJECT }
    get.mockImplementation((url?: string) => {
      if (url?.endsWith('/projects')) return Promise.resolve([served])
      if (url?.includes('/velocity')) return Promise.resolve({ sprints: [] })
      return Promise.resolve([])
    })
    const wrapper = mount(ProjectBrowserView, mountOpts)
    await flushPromises()
    await byText(wrapper, P.edit)!.trigger('click')
    await flushPromises()

    const nameInput = wrapper.findAll('input').find(
      i => (i.element as HTMLInputElement).value === 'Original name',
    )!
    await nameInput.setValue('Renamed')
    // What the server will now serve — only a refetch can pick this up.
    served = { ...PROJECT, name: 'Renamed' }
    await byText(wrapper, P.saveAction)!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Renamed')
    expect(wrapper.text()).not.toContain('Original name')
    // And the response's own value must NOT appear, which is what proves it
    // was not read.
    expect(wrapper.text()).not.toContain('ignored-if-read')
  })

  it('reports a 404 as gone rather than as a generic failure', async () => {
    // The route's IDOR guard answers 404 for a project outside the caller's
    // org as well as for one that does not exist, so the message cannot claim
    // a permission verdict it is unable to distinguish.
    patch.mockRejectedValue({ status: 404, message: 'Project not found' })
    const wrapper = await openEditor()

    const nameInput = wrapper.findAll('input').find(
      i => (i.element as HTMLInputElement).value === 'Original name',
    )!
    await nameInput.setValue('Something else')
    await byText(wrapper, P.saveAction)!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain(P.editNotFound)
    expect(wrapper.text()).not.toContain(P.editError)
  })

  it('reports any other failure with the generic message', async () => {
    // The other half of the pair: a 404-specific message assigned to every
    // failure would satisfy the assertion above on its own.
    patch.mockRejectedValue({ status: 500, message: 'boom' })
    const wrapper = await openEditor()

    const nameInput = wrapper.findAll('input').find(
      i => (i.element as HTMLInputElement).value === 'Original name',
    )!
    await nameInput.setValue('Something else')
    await byText(wrapper, P.saveAction)!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain(P.editError)
    expect(wrapper.text()).not.toContain(P.editNotFound)
  })
})
