// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #20936: the rules section is read-only and shown to everyone; the violations section only to an admin.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { HttpError } from '@autobot/ui'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import BacklogHierarchyPanel from '../BacklogHierarchyPanel.vue'

const RULES = {
  rules: [
    { type: 'epic', allowed_parent_types: [], project_required: true },
    { type: 'task', allowed_parent_types: ['pbi'], project_required: true },
  ],
}
const FOUND = { violations: [{ id: 'w1', identifier: 'WI-1', reason: 'a task has no project_id' }], count: 1 }
const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

function answer(report: unknown) {
  get.mockReset().mockImplementation((url: string) => {
    if (url.includes('hierarchy-rules')) return Promise.resolve(RULES)
    return report instanceof Error ? Promise.reject(report) : Promise.resolve(report)
  })
}

async function mountPanel() {
  const wrapper = mount(BacklogHierarchyPanel, { props: { companyId: 'c1' }, global: { plugins: [i18n] } })
  await flushPromises()
  // Both sections open, so the assertions read the bodies on a real accordion as well as a stubbed one.
  ;(wrapper.vm as unknown as { open: string[] }).open = ['rules', 'violations']
  await flushPromises()
  return wrapper
}

describe('BacklogHierarchyPanel', () => {
  beforeEach(() => {
    get.mockReset()
  })

  it('shows the rules to a member, and no violations section', async () => {
    answer(new HttpError(403, 'refused'))
    const wrapper = await mountPanel()

    expect(wrapper.text()).toContain(en.llc.backlog.hierarchyRulesTitle)
    expect(wrapper.get('[data-testid="hierarchy-rules"]').text()).toContain('Task')
    expect(wrapper.text()).not.toContain('Hierarchy violations')
    expect(wrapper.find('[data-testid="hierarchy-violations"]').exists()).toBe(false)
  })

  it('shows an admin the violations section with the rows', async () => {
    answer(FOUND)
    const wrapper = await mountPanel()

    expect(wrapper.text()).toContain('Hierarchy violations (1)')
    expect(wrapper.get('[data-testid="hierarchy-violations"]').text()).toContain('WI-1')
    expect(wrapper.text()).toContain('a task has no project_id')
  })

  it('says so when an admin has no violations', async () => {
    answer({ violations: [], count: 0 })
    const wrapper = await mountPanel()
    expect(wrapper.get('[data-testid="no-violations"]').text()).toBe(en.llc.backlog.hierarchyNoViolations)
  })

  it('shows a retryable failure to an admin whose report did not load', async () => {
    answer(new HttpError(500, 'down'))
    const wrapper = await mountPanel()

    expect(wrapper.text()).toContain(en.llc.backlog.hierarchyViolationsFailed)
    answer(FOUND)
    await wrapper.get('[data-testid="retry-violations"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="hierarchy-violations"]').exists()).toBe(true)
  })

  it('renders a type with no allowed parent as having no parent', async () => {
    answer(FOUND)
    const wrapper = await mountPanel()
    expect(wrapper.get('[data-testid="hierarchy-rules"]').text()).toContain(en.llc.backlog.hierarchyNoParent)
  })
})
