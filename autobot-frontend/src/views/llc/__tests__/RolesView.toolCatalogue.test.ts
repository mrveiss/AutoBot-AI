// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #14852: the Roles tab reads the tool catalogue.
//
// Attaching a tool meant typing its name. A typo surfaced as a server
// rejection after the round trip, and nothing told you what was available.
// These tests cover the two states that matter and are easy to get backwards:
// a catalogue that loaded (picker) and one that did not (text box).
//
// The catalogue URL shares the '/tools' substring with the role's own tool
// list, so the mocks here match the company-scoped path first. Getting that
// ordering wrong feeds the picker the role's attached names and it still
// renders — which is why it is asserted rather than assumed.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { memoizeByLocale } from '@/test/utils/i18n-cache'
import en from '@/i18n/locales/en.json'

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

const CATALOGUE = [
  {
    name: 'crm.salesforce',
    description: 'Customer records',
    tags: ['crm'],
    url: 'https://example.invalid/crm',
    logo_url: null,
    role_count: 1,
  },
  { name: 'chat.slack', description: '', tags: [], url: null, logo_url: null, role_count: 0 },
]

function respond(catalogue: unknown): void {
  get.mockImplementation((url: string) => {
    // Company-scoped catalogue first — see the header note.
    if (url.startsWith('/api/llc/tools/')) {
      return catalogue instanceof Error ? Promise.reject(catalogue) : Promise.resolve(catalogue)
    }
    if (url.includes('/holders')) return Promise.resolve([])
    if (url.includes('/permissions')) return Promise.resolve([])
    if (url.includes('/workflows')) return Promise.resolve([])
    if (url.includes('/tools')) return Promise.resolve(['crm.salesforce'])
    if (url.includes('/credentials')) return Promise.resolve([])
    if (url.includes('/rate')) return Promise.resolve(null)
    return Promise.resolve([ROLE])
  })
}

const makeI18n = memoizeByLocale((locale: string) =>
  createI18n({ legacy: false, locale, messages: { en } }),
)

async function mountView() {
  const wrapper = mount(RolesView, {
    global: { plugins: [makeI18n('en')], stubs: { BaseModal: true } },
  })
  await flushPromises()
  return wrapper
}

function toolsPanel(wrapper: ReturnType<typeof mount>) {
  return wrapper
    .findAllComponents(RoleAttachmentPanel)
    .find((panel) => panel.props('panelKey') === 'tools')
}

describe('RolesView tool catalogue (#14852)', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
    del.mockReset()
  })

  it('requests the company-scoped catalogue, not a role-scoped one', async () => {
    respond(CATALOGUE)
    await mountView()

    expect(get).toHaveBeenCalledWith('/api/llc/tools/c1')
  })

  it('hands the panel one option per catalogue entry', async () => {
    respond(CATALOGUE)
    const wrapper = await mountView()

    const options = toolsPanel(wrapper)?.props('options') as { value: string; label: string }[]
    expect(options.map((o) => o.value)).toEqual(['crm.salesforce', 'chat.slack'])
    // A description is appended when present and omitted when blank, rather
    // than rendering a dangling separator.
    expect(options[0].label).toBe('crm.salesforce — Customer records')
    expect(options[1].label).toBe('chat.slack')
  })

  it('falls back to the text box when the catalogue is unavailable', async () => {
    // A 503 here means the tool registry is unpopulated — an environment
    // problem. `undefined`, not `[]`: the panel reads a missing prop as "use
    // the text box" and an empty array as "the catalogue is genuinely empty",
    // and showing an empty picker would read as "this company has no tools".
    respond(new Error('registry unavailable'))
    const wrapper = await mountView()

    expect(toolsPanel(wrapper)?.props('options')).toBeUndefined()
  })

  it('does not fail the tab when the catalogue rejects', async () => {
    respond(new Error('registry unavailable'))
    const wrapper = await mountView()

    // The roles themselves still loaded; a picker that could not populate must
    // not take the Roles tab down with it.
    expect(wrapper.text()).toContain('Head of Sales')
  })
})
