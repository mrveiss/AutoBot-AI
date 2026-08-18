// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #14221 step 6b: the Roles tab can now CHANGE what a role carries.
//
// It shipped read-only. Six GETs were wired and eleven mutating endpoints had no
// control at all, so an admin could see a role's permissions, tools, workflows
// and credentials but never alter them — the feature existed and nobody could
// use it.
//
// These tests assert each control reaches its endpoint. A button that renders
// and calls nothing looks identical to a working one in every screenshot, which
// is how the gap survived a green suite the first time.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ar from '@/i18n/locales/ar.json'

const get = vi.fn()
const post = vi.fn()
const del = vi.fn()

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get, post, delete: del }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { companyId: 'c1' } }),
  useRouter: () => ({ push: vi.fn() }),
}))

import RolesView from '../RolesView.vue'
import RoleAttachmentPanel from '@/components/llc/RoleAttachmentPanel.vue'

const ROLE = { id: 'r1', company_id: 'c1', name: 'Head of Sales', is_system: false }
const OTHER_ROLE = { id: 'r2', company_id: 'c1', name: 'SRE', is_system: false }
const HOLDER = { id: 'a1', role_id: 'r1', holder_type: 'user', holder_id: 'u-9', ended_at: null }

function respond(): void {
  get.mockImplementation((url: string) => {
    if (url.includes('/holders')) return Promise.resolve([HOLDER])
    if (url.includes('/permissions')) return Promise.resolve(['knowledge.read'])
    if (url.includes('/workflows')) return Promise.resolve(['wf-1'])
    if (url.includes('/tools')) return Promise.resolve(['llc.create_work_item'])
    if (url.includes('/credentials')) return Promise.resolve(['sec-1'])
    return Promise.resolve([ROLE])
  })
}

async function mountView(locale: 'en' | 'ar' = 'en') {
  const i18n = createI18n({ legacy: false, locale, messages: { en, ar } })
  const wrapper = mount(RolesView, { global: { plugins: [i18n], stubs: { BaseModal: true } } })
  await flushPromises()
  return wrapper
}

/** The panel rendering a given section title. */
function panelFor(wrapper: Awaited<ReturnType<typeof mountView>>, title: string) {
  const panel = wrapper
    .findAllComponents(RoleAttachmentPanel)
    .find((p) => p.props('title') === title)
  if (!panel) throw new Error(`no panel titled ${title}`)
  return panel
}

describe('RolesView operations (#14221 step 6b)', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
    del.mockReset()
    post.mockResolvedValue(undefined)
    del.mockResolvedValue(undefined)
  })

  it('renders a panel for every kind of thing a role carries', async () => {
    respond()
    const wrapper = await mountView()

    const titles = wrapper.findAllComponents(RoleAttachmentPanel).map((p) => p.props('title'))
    expect(titles).toEqual([
      en.llcRoles.permissions,
      en.llcRoles.workflows,
      en.llcRoles.tools,
      en.llcRoles.credentials,
    ])
  })

  it.each([
    [en.llcRoles.permissions, 'knowledge.write', '/permissions', { permission: 'knowledge.write' }],
    [en.llcRoles.workflows, 'wf-2', '/workflows', { workflow_id: 'wf-2' }],
    [en.llcRoles.tools, 'llc.record_decision', '/tools', { tool_name: 'llc.record_decision' }],
    [en.llcRoles.credentials, 'sec-2', '/credentials', { secret_id: 'sec-2' }],
  ])('adds to %s via its endpoint', async (title, value, suffix, body) => {
    respond()
    const wrapper = await mountView()

    panelFor(wrapper, title).vm.$emit('add', value)
    await flushPromises()

    expect(post).toHaveBeenCalledWith(`/api/llc/roles/c1/r1${suffix}`, body)
  })

  it.each([
    [en.llcRoles.permissions, 'knowledge.read', '/permissions/knowledge.read'],
    [en.llcRoles.workflows, 'wf-1', '/workflows/wf-1'],
    [en.llcRoles.tools, 'llc.create_work_item', '/tools/llc.create_work_item'],
    [en.llcRoles.credentials, 'sec-1', '/credentials/sec-1'],
  ])('removes from %s via its endpoint', async (title, value, suffix) => {
    respond()
    const wrapper = await mountView()

    panelFor(wrapper, title).vm.$emit('remove', value)
    await flushPromises()

    expect(del).toHaveBeenCalledWith(`/api/llc/roles/c1/r1${suffix}`)
  })

  it('encodes a value that would otherwise break the path', async () => {
    // A namespaced tool or a permission with a slash must not silently address
    // a different endpoint.
    respond()
    const wrapper = await mountView()

    panelFor(wrapper, en.llcRoles.tools).vm.$emit('remove', 'team/oncall')
    await flushPromises()

    expect(del).toHaveBeenCalledWith('/api/llc/roles/c1/r1/tools/team%2Foncall')
  })

  it('assigns a holder with the selected kind', async () => {
    respond()
    const wrapper = await mountView()
    const vm = wrapper.vm as unknown as {
      newHolderType: string
      newHolderId: string
      assignHolder: () => Promise<void>
    }

    vm.newHolderType = 'contact'
    vm.newHolderId = '  u-77  '
    await vm.assignHolder()
    await flushPromises()

    // Trimmed: a stray space would create a holder id nothing else matches.
    expect(post).toHaveBeenCalledWith('/api/llc/roles/c1/r1/holders', {
      holder_type: 'contact',
      holder_id: 'u-77',
    })
  })

  it('ends a tenure by assignment id, not by holder id', async () => {
    // The tenure is the thing that ends; addressing it by holder would end the
    // wrong one when someone has held the role twice.
    respond()
    const wrapper = await mountView()
    const vm = wrapper.vm as unknown as { endTenure: (id: string) => Promise<void> }

    await vm.endTenure('a1')
    await flushPromises()

    expect(del).toHaveBeenCalledWith('/api/llc/roles/c1/r1/holders/a1')
  })

  it('reloads from the server after a change rather than patching locally', async () => {
    // An optimistic list would show access that may not exist. The reload is
    // what makes the panel agree with the server.
    respond()
    const wrapper = await mountView()
    const before = get.mock.calls.length

    panelFor(wrapper, en.llcRoles.permissions).vm.$emit('add', 'knowledge.write')
    await flushPromises()

    expect(get.mock.calls.length).toBeGreaterThan(before)
  })

  it('surfaces the refusal and leaves the list untouched', async () => {
    respond()
    post.mockRejectedValue(
      new Error("HTTP 403: membership role 'member' may not perform this change"),
    )
    const wrapper = await mountView()

    panelFor(wrapper, en.llcRoles.permissions).vm.$emit('add', 'knowledge.write')
    await flushPromises()

    expect(wrapper.text()).toContain('may not perform this change')
    expect(wrapper.text()).toContain('knowledge.read')
  })

  it('blocks a second mutation while one is in flight', async () => {
    respond()
    let release: (() => void) | undefined
    post.mockImplementation(() => new Promise<void>((resolve) => (release = resolve)))
    const wrapper = await mountView()
    const panel = panelFor(wrapper, en.llcRoles.permissions)

    panel.vm.$emit('add', 'a.one')
    await flushPromises()
    panel.vm.$emit('add', 'a.two')
    await flushPromises()

    expect(post).toHaveBeenCalledTimes(1)
    release?.()
  })

  it.each(['en', 'ar'] as const)(
    'gives every panel a distinct DOM id in %s',
    async (locale) => {
      // Asserted in a non-Latin locale on purpose. The id used to be derived
      // from the translated title, and the slug regex keeps only [a-z0-9] — so
      // Arabic, Hebrew, Farsi and Urdu collapsed all four panels to the same
      // id, breaking every <label for>. An English-only assertion passes
      // against that bug, which is how it shipped in the first place.
      respond()
      const wrapper = await mountView(locale)

      const ids = wrapper.findAll('input[id^="attachment-"]').map((i) => i.attributes('id'))
      expect(ids).toEqual([
        'attachment-permissions',
        'attachment-workflows',
        'attachment-tools',
        'attachment-credentials',
      ])
      expect(new Set(ids).size).toBe(ids.length)
    },
  )

  it('discards a reload that a role switch has already superseded', async () => {
    // Switching role while a post-mutation reload is in flight must not let the
    // slower response publish the previous role's data under the new role's
    // name — a wrong answer on a screen about who may reach what.
    const gate: Array<() => void> = []
    get.mockImplementation((url: string) => {
      if (url.endsWith('/roles/c1')) return Promise.resolve([ROLE, OTHER_ROLE])
      if (url.includes('/r1/permissions')) {
        // Hold r1's answer open until after r2 has loaded.
        return new Promise((resolve) => gate.push(() => resolve(['stale.permission'])))
      }
      if (url.includes('/permissions')) return Promise.resolve(['fresh.permission'])
      return Promise.resolve([])
    })

    const wrapper = await mountView()
    const vm = wrapper.vm as unknown as { selectRole: (id: string) => Promise<void> }

    await vm.selectRole('r2')
    await flushPromises()

    // r1's held response now arrives, late.
    gate.forEach((release) => release())
    await flushPromises()

    expect(wrapper.text()).toContain('fresh.permission')
    expect(wrapper.text()).not.toContain('stale.permission')
  })
})
