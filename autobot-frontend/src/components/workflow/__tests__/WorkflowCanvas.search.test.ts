// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #14611: canvas search — a large Company OS canvas has no other way to find
 * a node than panning until it scrolls into view.
 *
 * Every fixture node here comes from the real layout builders
 * (`buildOrgCanvasGraph`, `buildProcessCanvasNodes`, `buildToolCanvasNodes`,
 * `buildTeamCanvasNodes`) rather than a hand-rolled node object, so the search
 * text these tests exercise is exactly what the canvas actually receives from
 * `OrgChart.vue` — a hand-written fixture could drift from the real producers'
 * shape and pass against data the canvas never sees.
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ar from '@/i18n/locales/ar.json'

vi.mock('@/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: vi.fn().mockResolvedValue(true) }),
}))

import WorkflowCanvas from '../WorkflowCanvas.vue'
import {
  buildOrgCanvasGraph,
  buildProcessCanvasNodes,
  buildToolCanvasNodes,
  buildTeamCanvasNodes,
  canvasBottom,
  flattenOrgNodes,
} from '@/composables/llc/orgCanvasGraph'
import { buildOrgPeople } from '@/composables/llc/orgPeople'
import type { OrgNode } from '@/views/llc/OrgTreeNode.vue'
import type { CompanyTeam } from '@/composables/llc/orgPeople'

function orgNode(id: string, name: string, children: OrgNode[] = []): OrgNode {
  return {
    id,
    name,
    title: 'Engineer',
    status: 'idle',
    adapter_type: 'claude',
    is_human: false,
    last_heartbeat: null,
    budget_spent: 0,
    budget_total: 0,
    assigned_item_count: 0,
    parent_id: null,
    children,
  }
}

// One reporting unit (person + group), one process, one tool, one team — the
// four node kinds #14611 requires search to reach.
const FOREST: OrgNode[] = [orgNode('ceo', 'Ada Lovelace', [orgNode('dev', 'Bo Diddley')])]
const PEOPLE_NODES = buildOrgCanvasGraph(FOREST, (name) => `${name} unit`)
const PROCESS_NODES = buildProcessCanvasNodes(
  [{ role_id: 'r1', role_name: 'Head of Sales', workflow_id: 'wf-quarterly' }],
  canvasBottom(PEOPLE_NODES),
)
const TOOL_NODES = buildToolCanvasNodes(
  [{ role_id: 'r1', role_name: 'Head of Sales', tool_name: 'Salesforce' }],
  [{ role_id: 'r1', role_name: 'Head of Sales', workflow_id: 'wf-quarterly' }],
  canvasBottom([...PEOPLE_NODES, ...PROCESS_NODES]),
)
const TEAMS: CompanyTeam[] = [{ id: 't1', name: 'Platform', member_user_ids: [] }]
const TEAM_NODES = buildTeamCanvasNodes(
  flattenOrgNodes(FOREST),
  buildOrgPeople(FOREST, []),
  TEAMS,
  canvasBottom([...PEOPLE_NODES, ...PROCESS_NODES, ...TOOL_NODES]),
  (name) => `${name} team`,
  'Not on a team',
)

const ALL_NODES = [...PEOPLE_NODES, ...PROCESS_NODES, ...TOOL_NODES, ...TEAM_NODES]

function mountCanvas(locale: 'en' | 'ar' = 'en', nodes = ALL_NODES) {
  return mount(WorkflowCanvas, {
    props: { nodes, selectedNodeId: null, readonly: true },
    global: {
      plugins: [createI18n({ legacy: false, locale, fallbackLocale: 'en', messages: { en, ar } })],
    },
    attachTo: document.body,
  })
}

async function search(wrapper: ReturnType<typeof mountCanvas>, query: string) {
  await wrapper.get('[data-testid="canvas-search-input"]').setValue(query)
}

describe('canvas search box (#14611)', () => {
  it('is present when the canvas has nodes, and never gated on readonly', () => {
    const readonlyWrapper = mount(WorkflowCanvas, {
      props: { nodes: ALL_NODES, selectedNodeId: null, readonly: true },
      global: { plugins: [createI18n({ legacy: false, locale: 'en', messages: { en } })] },
    })
    const authoringWrapper = mount(WorkflowCanvas, {
      props: { nodes: ALL_NODES, selectedNodeId: null, readonly: false },
      global: { plugins: [createI18n({ legacy: false, locale: 'en', messages: { en } })] },
    })

    expect(readonlyWrapper.find('[data-testid="canvas-search-input"]').exists()).toBe(true)
    expect(authoringWrapper.find('[data-testid="canvas-search-input"]').exists()).toBe(true)
  })

  it('is absent from an empty canvas — nothing to search', () => {
    const wrapper = mount(WorkflowCanvas, {
      props: { nodes: [], selectedNodeId: null, readonly: true },
      global: { plugins: [createI18n({ legacy: false, locale: 'en', messages: { en } })] },
    })

    expect(wrapper.find('[data-testid="canvas-search-input"]').exists()).toBe(false)
  })

  it('finds a person node by name, and Enter jumps focus to the real reporting-hierarchy node', async () => {
    const wrapper = mountCanvas()
    await search(wrapper, 'Ada Lovelace')

    // Not asserted as exactly one: the fixture's "Platform" team has no
    // members assigned, so the real producer (`buildTeamCanvasNodes`) also
    // draws Ada as a person-less-team roster duplicate, and the unit
    // container's own label ("Ada Lovelace unit") is itself a substring
    // match — all legitimate hits on the actual data the canvas draws.
    const results = wrapper.findAll('[data-testid="canvas-search-result"]')
    expect(results.length).toBeGreaterThanOrEqual(1)
    expect(wrapper.find('[data-testid="canvas-search-no-results"]').exists()).toBe(false)

    // Enter with nothing highlighted jumps to the FIRST result — assert on
    // that, rather than the label text, since the exact ordering already
    // belongs to `buildOrgCanvasGraph`/`buildTeamCanvasNodes`, not to search.
    await wrapper.get('[data-testid="canvas-search-input"]').trigger('keydown', { key: 'Enter' })
    expect(document.activeElement).not.toBeNull()
    expect(document.activeElement?.getAttribute('data-node-id')).not.toBeNull()
  })

  it('finds a group/unit container by its label', async () => {
    const wrapper = mountCanvas()
    await search(wrapper, 'unit')

    const results = wrapper.findAll('[data-testid="canvas-search-result"]')
    expect(results.map((r) => r.text())).toEqual(
      expect.arrayContaining([expect.stringContaining('Ada Lovelace unit')]),
    )
  })

  it('finds a team container by its label', async () => {
    const wrapper = mountCanvas()
    await search(wrapper, 'Platform')

    const results = wrapper.findAll('[data-testid="canvas-search-result"]')
    expect(results.length).toBeGreaterThan(0)
    expect(results.some((r) => r.text().includes('Platform team'))).toBe(true)
  })

  it('finds a process node by its role name', async () => {
    const wrapper = mountCanvas()
    await search(wrapper, 'Head of Sales')

    const results = wrapper.findAll('[data-testid="canvas-search-result"]')
    expect(results.some((r) => r.text().includes('Head of Sales'))).toBe(true)
  })

  it('finds a tool node by its tool name', async () => {
    const wrapper = mountCanvas()
    await search(wrapper, 'Salesforce')

    const results = wrapper.findAll('[data-testid="canvas-search-result"]')
    expect(results).toHaveLength(1)
    expect(results[0].text()).toContain('Salesforce')
  })

  it('matches case-insensitively and on a partial name', async () => {
    const wrapper = mountCanvas()
    await search(wrapper, 'ada love')

    const results = wrapper.findAll('[data-testid="canvas-search-result"]')
    expect(results.length).toBeGreaterThanOrEqual(1)
    expect(results.every((r) => r.text().toLowerCase().includes('ada love'))).toBe(true)
  })

  it('reads "no match", never an empty canvas, for a query nothing satisfies', async () => {
    const wrapper = mountCanvas()
    await search(wrapper, 'zzz-nobody-here')

    const noResults = wrapper.get('[data-testid="canvas-search-no-results"]')
    expect(noResults.text()).toBe(
      en.workflow.canvas.searchNoResults.replace('{query}', 'zzz-nobody-here'),
    )
    expect(wrapper.find('[data-testid="canvas-search-result"]').exists()).toBe(false)
    // Paired positive: the canvas itself is unaffected by an unmatched search
    // — every node is still drawn, so this is a fact about the query, not a
    // canvas that failed to render (#14064/#13617/#14556's repeat defect).
    expect(wrapper.findAll('.workflow-node')).toHaveLength(ALL_NODES.length)
  })

  it('announces the match count to a screen reader via the live region', async () => {
    const wrapper = mountCanvas()
    await search(wrapper, 'Salesforce')

    expect(wrapper.get('[data-testid="canvas-search-status"]').text()).toBe(
      en.workflow.canvas.searchResultsStatus.replace('{count}', '1').replace('{query}', 'Salesforce'),
    )
  })

  it('announces zero matches to a screen reader too', async () => {
    const wrapper = mountCanvas()
    await search(wrapper, 'zzz-nobody-here')

    expect(wrapper.get('[data-testid="canvas-search-status"]').text()).toBe(
      en.workflow.canvas.searchNoResults.replace('{query}', 'zzz-nobody-here'),
    )
  })

  it('Enter jumps the viewport to the matched node', async () => {
    const wrapper = mountCanvas()
    const before = wrapper.get('.canvas-content').attributes('style')
    await search(wrapper, 'Salesforce')

    await wrapper.get('[data-testid="canvas-search-input"]').trigger('keydown', { key: 'Enter' })

    const after = wrapper.get('.canvas-content').attributes('style')
    expect(after).not.toBe(before)
    // "Zoom to a node" (#14611) is a fixed, comfortable level — scale(1) — not
    // a maximal fit; the reset button's own scale(1) default makes this the
    // one part of the transform that does NOT change on a jump.
    expect(after).toContain('scale(1)')
  })

  it('moves keyboard focus to the jumped-to node, for a screen-reader user', async () => {
    const wrapper = mountCanvas()
    await search(wrapper, 'Salesforce')
    await wrapper.get('[data-testid="canvas-search-input"]').trigger('keydown', { key: 'Enter' })

    const toolNode = wrapper.get('.workflow-node.org-tool')
    expect(toolNode.element).toBe(document.activeElement)
  })

  it('ArrowDown/ArrowUp cycle which result Enter would jump to', async () => {
    const wrapper = mountCanvas()
    // "e" matches several of the fixture's labels/roles across kinds.
    await search(wrapper, 'e')
    const input = wrapper.get('[data-testid="canvas-search-input"]')
    const resultCount = wrapper.findAll('[data-testid="canvas-search-result"]').length
    expect(resultCount).toBeGreaterThan(1)

    await input.trigger('keydown', { key: 'ArrowDown' })
    const activeAfterOne = wrapper.findAll('.canvas-search-result.active')
    expect(activeAfterOne).toHaveLength(1)

    await input.trigger('keydown', { key: 'ArrowDown' })
    const activeAfterTwo = wrapper.find('.canvas-search-result.active')
    // The highlight actually moved to a different result, not the same one.
    expect(activeAfterTwo.text()).not.toBe(activeAfterOne[0].text())
  })

  it('Escape clears the query and closes the results', async () => {
    const wrapper = mountCanvas()
    await search(wrapper, 'Salesforce')
    expect(wrapper.find('[data-testid="canvas-search-result"]').exists()).toBe(true)

    await wrapper.get('[data-testid="canvas-search-input"]').trigger('keydown', { key: 'Escape' })

    expect((wrapper.get('[data-testid="canvas-search-input"]').element as HTMLInputElement).value).toBe('')
    expect(wrapper.find('[data-testid="canvas-search-result"]').exists()).toBe(false)
  })

  it('the clear button empties the query', async () => {
    const wrapper = mountCanvas()
    await search(wrapper, 'Salesforce')

    await wrapper.get('[data-testid="canvas-search-clear"]').trigger('click')

    expect((wrapper.get('[data-testid="canvas-search-input"]').element as HTMLInputElement).value).toBe('')
    expect(wrapper.find('[data-testid="canvas-search-clear"]').exists()).toBe(false)
  })

  it('reads and operates in an RTL locale', async () => {
    const wrapper = mountCanvas('ar')

    expect(wrapper.get('[data-testid="canvas-search-input"]').attributes('placeholder')).toBe(
      ar.workflow.canvas.searchPlaceholder,
    )

    await search(wrapper, 'Salesforce')
    const results = wrapper.findAll('[data-testid="canvas-search-result"]')
    expect(results).toHaveLength(1)

    await wrapper.get('[data-testid="canvas-search-input"]').trigger('keydown', { key: 'Enter' })
    expect(wrapper.get('.workflow-node.org-tool').element).toBe(document.activeElement)
  })
})
