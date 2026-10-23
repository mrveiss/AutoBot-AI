// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// WorkItemDetail on the kit BaseDrawer (#14780, #19145 review): the drawer's title carries the
// identifier and the type/status badges, Escape closes it, and HandoffModal opens as a sibling
// dialog outside the drawer.

import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { defineComponent, h } from 'vue'
import en from '@/i18n/locales/en.json'

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get: vi.fn(async () => []), post: vi.fn(), patch: vi.fn() }) }))
vi.mock('@/utils/debugUtils', () => ({ createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }) }))
vi.mock('@/composables/llc/useCompanyPeople', () => ({
  useCompanyPeople: () => ({ agents: { value: [] }, humans: { value: [] }, isLoading: { value: false }, load: vi.fn() }),
}))

import WorkItemDetail from '../WorkItemDetail.vue'

const ITEM = {
  id: 'w1', identifier: 'ACME-42', title: 'Ship it', description: '', type: 'task', status: 'todo',
  priority: 'medium', acceptance_criteria: [], acceptance_criteria_done: [],
}
const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', missingWarn: false, messages: { en } })
const Badge = defineComponent({ props: ['kind', 'value'], setup: (p) => () => h('span', { class: 'badge' }, `${p.kind}:${p.value}`) })
const Handoff = defineComponent({ name: 'HandoffModal', setup: () => () => h('div', { class: 'handoff-stub' }) })

async function mountDetail() {
  const w = mount(WorkItemDetail, {
    props: { item: { ...ITEM }, companyId: 'c1' },
    global: { plugins: [i18n], stubs: { Teleport: true, WorkItemBadge: Badge, HandoffModal: Handoff } },
    attachTo: document.body,
  })
  await flushPromises()
  return w
}

describe('WorkItemDetail on BaseDrawer', () => {
  it('titles the drawer with the identifier and both badges', async () => {
    const w = await mountDetail()
    const title = w.find(`#${w.find('[role="dialog"]').attributes('aria-labelledby')}`)
    expect(title.text()).toContain('ACME-42')
    expect(title.text()).toContain('type:task')
    expect(title.text()).toContain('status:todo')
    w.unmount()
  })

  it('emits close on Escape', async () => {
    const w = await mountDetail()
    await w.find('.aui-drawer-overlay').trigger('keydown', { key: 'Escape' })
    expect(w.emitted('close')).toHaveLength(1)
    w.unmount()
  })

  it('opens HandoffModal as a sibling dialog, outside the drawer', async () => {
    const w = await mountDetail()
    ;(w.vm as unknown as { handoffDirection: string | null }).handoffDirection = 'to_agent'
    await flushPromises()
    const handoff = w.find('.handoff-stub')
    expect(handoff.exists()).toBe(true)
    expect(w.find('.aui-drawer').element.contains(handoff.element)).toBe(false)
    w.unmount()
  })
})
