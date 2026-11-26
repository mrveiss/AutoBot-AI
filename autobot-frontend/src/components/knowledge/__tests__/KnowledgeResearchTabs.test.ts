// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/** KnowledgeResearchTabs follows ?tab= after mount: Research and Web Research share one route (#18244). */
import { describe, it, expect, beforeEach } from 'vitest'
import { reactive, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { vi } from 'vitest'

const route = vi.hoisted(() => ({ current: null as unknown as { query: Record<string, unknown> } }))
vi.mock('vue-router', () => ({ useRoute: () => route.current }))

import KnowledgeResearchTabs from '../KnowledgeResearchTabs.vue'

const stubs = {
  KnowledgeResearchPanel: { template: '<div class="p-research" />' },
  WebResearchPanel: { template: '<div class="p-web" />' },
  WebResearchStatus: { template: '<div class="p-settings" />' },
  Icon: true,
}
const mountTabs = () => mount(KnowledgeResearchTabs, { global: { stubs, mocks: { $t: (k: string) => k } } })

beforeEach(() => {
  route.current = reactive({ query: {} as Record<string, unknown> })
})

describe('KnowledgeResearchTabs', () => {
  it('opens on the tab named by ?tab= and falls back to research for an unknown one', () => {
    route.current.query.tab = 'webTools'
    expect(mountTabs().find('.p-web').exists()).toBe(true)
    route.current.query.tab = 'nope'
    expect(mountTabs().find('.p-research').exists()).toBe(true)
  })

  it('follows ?tab= when the route changes while the component stays mounted', async () => {
    const w = mountTabs()
    expect(w.find('.p-research').exists()).toBe(true)
    route.current.query.tab = 'webTools'
    await nextTick()
    expect(w.find('.p-web').exists()).toBe(true)
    delete route.current.query.tab
    await nextTick()
    expect(w.find('.p-research').exists()).toBe(true)
  })
})
