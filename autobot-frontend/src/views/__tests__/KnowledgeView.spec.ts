// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * KnowledgeView (#18244): the sub-navigation is the kit SectionNav in the mockup's order,
 * advanced entries carry `adv`, Vector Store is admin-only, Transcriber and Health stay (D1),
 * and the advanced-area notice shows only on advanced pages.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent } from 'vue'
import en from '@/i18n/locales/en.json'
import KnowledgeView from '../KnowledgeView.vue'
import { useUserStore } from '@/stores/useUserStore'

const Page = defineComponent({ template: '<p data-testid="page">page</p>' })
const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

// The router says which screens are advanced (`meta.adv`) and admin-only; the nav reads it from there.
const ADV = { adv: true }
const ROUTES = [
  ['knowledge-browser', '/knowledge/browser', {}],
  ['knowledge-graph', '/knowledge/graph', ADV],
  ['knowledge-vector-store', '/knowledge/vector-store', { ...ADV, admin: true }],
  ['knowledge-research', '/knowledge/research', ADV],
  ['knowledge-mcp-resources', '/knowledge/mcp-resources', ADV],
  ['knowledge-system-docs', '/knowledge/system-docs', ADV],
  ['knowledge-manage', '/knowledge/manage', {}],
  ['knowledge-entities', '/knowledge/entities', ADV],
  ['knowledge-health', '/knowledge/health', ADV],
  ['knowledge-transcriber', '/knowledge/transcriber', {}],
] as const

async function mountAt(path: string, admin = false) {
  const pinia = createPinia()
  setActivePinia(pinia)
  useUserStore().currentUser = admin ? ({ role: 'admin', roles: ['admin'] } as never) : null
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: Page },
      ...ROUTES.map(([name, p, meta]) => ({ name, path: p, meta, component: Page })),
      // A child of the Graph screen inherits its parent's meta.adv.
      { path: '/knowledge/graph-child', name: 'child-host', component: Page, meta: ADV, children: [{ path: 'timeline', name: 'knowledge-graph-timeline', component: Page }] },
    ],
  })
  router.push(path)
  await router.isReady()
  const w = mount(KnowledgeView, { global: { plugins: [i18n, router, pinia] } })
  await flushPromises()
  return w
}

const labels = (w: Awaited<ReturnType<typeof mountAt>>) => w.findAll('.aui-section-nav__link').map((a) => a.text())

beforeEach(() => {
  localStorage.clear()
  document.documentElement.setAttribute('data-ui', 'full')
})

describe('KnowledgeView navigation', () => {
  it('lists the items in the mockup order, then Transcriber (D1), Manage, Entities and Health', async () => {
    const w = await mountAt('/knowledge/browser', true)
    expect(labels(w)).toEqual([
      'Browser', 'Graph', 'Vector Store', 'Research', 'MCP Resources', 'System Docs', 'Transcriber',
      'Manage', 'Entities', 'Health', 'Web Research',
    ])
    expect(w.findAll('.aui-section-nav__sect').map((s) => s.text())).toEqual(['Browse', 'Manage', 'Research'])
  })

  it('marks exactly the advanced items with adv: Graph, Vector Store, Research, MCP, System Docs, Entities, Health, Web Research', async () => {
    const w = await mountAt('/knowledge/browser', true)
    const adv = w.findAll('.aui-section-nav__link.adv').map((a) => a.text())
    expect(adv).toEqual(['Graph', 'Vector Store', 'Research', 'MCP Resources', 'System Docs', 'Entities', 'Health', 'Web Research'])
    expect(w.findAll('.aui-section-nav__sect')[2].classes()).toContain('adv')
  })

  it('hides Vector Store from a non-admin', async () => {
    expect(labels(await mountAt('/knowledge/browser', false))).not.toContain('Vector Store')
  })

  it('marks the open page with aria-current, and Web Research apart from Research', async () => {
    const w = await mountAt('/knowledge/research?tab=webTools', true)
    const current = w.findAll('[aria-current="page"]').map((a) => a.text())
    expect(current).toEqual(['Web Research'])
    expect(labels(w)).toContain('Research')
  })

  it('keeps no empty section', async () => {
    const w = await mountAt('/knowledge/manage', false)
    w.findAll('.aui-section-nav__sect').forEach((sect) => {
      expect(sect.element.nextElementSibling?.querySelectorAll('li').length).toBeGreaterThan(0)
    })
  })
})

describe('KnowledgeView advanced-area notice', () => {
  it.each([
    ['/knowledge/graph', true],
    ['/knowledge/vector-store', true],
    ['/knowledge/entities', true],
    ['/knowledge/health', true],
    ['/knowledge/graph-child/timeline', true],
    ['/knowledge/browser', false],
    ['/knowledge/manage', false],
  ])('%s -> notice %s', async (path, shown) => {
    const w = await mountAt(path, true)
    expect(w.find('[data-testid="advanced-area-notice"]').exists()).toBe(shown)
    expect(w.find('[data-testid="page"]').exists()).toBe(true)
  })

  it('carries only-min, so the shared CSS shows it in Minimal mode only', async () => {
    const w = await mountAt('/knowledge/graph', true)
    expect(w.get('[data-testid="advanced-area-notice"]').classes()).toContain('only-min')
  })
})

describe('the real router marks the advanced Knowledge routes (#18244)', () => {
  it('carries meta.adv on exactly the advanced screens; Browser, Manage and Transcriber carry none', async () => {
    const { routes } = await import('@/router')
    const knowledge = routes.find((r) => r.name === 'knowledge')!
    const adv = (knowledge.children ?? []).filter((c) => c.meta?.adv).map((c) => c.name)
    expect(adv.sort()).toEqual([
      'knowledge-entities', 'knowledge-graph', 'knowledge-health', 'knowledge-mcp-resources',
      'knowledge-research', 'knowledge-system-docs', 'knowledge-vector-store',
    ])
    expect((knowledge.children ?? []).find((c) => c.name === 'knowledge-vector-store')?.meta?.admin).toBe(true)
  })
})
