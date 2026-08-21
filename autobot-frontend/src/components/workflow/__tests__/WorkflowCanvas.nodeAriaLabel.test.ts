// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #14657: `nodeAriaLabel` built its "name" half from `nodeTitle`, which for
 * `org-process` and `org-tool` is the generic type caption — the same string
 * `nodeKindLabel` already returns as the "kind" half. A screen reader heard
 * "Process: Process" and "Tool: Tool" for every process/tool node, with
 * nothing identifying which one it was.
 *
 * One case per node kind (person, group, process, tool), per the acceptance
 * criteria, so a regression on any single kind is caught — including the two
 * kinds (`org-person`, `org-group`) that were already correct, to guard the
 * `{kind}: {name}` template staying unchanged for them.
 *
 * Fixtures come from the real layout builders (`buildOrgCanvasGraph`,
 * `buildProcessCanvasNodes`, `buildToolCanvasNodes`) rather than a
 * hand-rolled node object — see `WorkflowCanvas.search.test.ts` for the same
 * reasoning: a hand-written node can drift into a shape nothing emits.
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ar from '@/i18n/locales/ar.json'

import WorkflowCanvas from '../WorkflowCanvas.vue'
import {
  buildOrgCanvasGraph,
  buildProcessCanvasNodes,
  buildToolCanvasNodes,
  canvasBottom,
} from '@/composables/llc/orgCanvasGraph'
import type { OrgNode } from '@/views/llc/OrgTreeNode.vue'

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

// One unit (a manager with a report, so it draws an org-group container too),
// one process and one tool carried by two roles — the four node kinds this
// issue's acceptance criteria names.
const FOREST: OrgNode[] = [orgNode('ceo', 'Ada Lovelace', [orgNode('dev', 'Bo Diddley')])]
const PEOPLE_NODES = buildOrgCanvasGraph(FOREST, (name) => `${name} unit`)
const PROCESS_NODES = buildProcessCanvasNodes(
  [{ role_id: 'r1', role_name: 'Head of Sales', workflow_id: 'wf-quarterly' }],
  canvasBottom(PEOPLE_NODES),
)
const TOOL_NODES = buildToolCanvasNodes(
  [
    { role_id: 'r1', role_name: 'Head of Sales', tool_name: 'Salesforce' },
    { role_id: 'r2', role_name: 'Head of Ops', tool_name: 'Salesforce' },
  ],
  [{ role_id: 'r1', role_name: 'Head of Sales', workflow_id: 'wf-quarterly' }],
  canvasBottom([...PEOPLE_NODES, ...PROCESS_NODES]),
)

const ALL_NODES = [...PEOPLE_NODES, ...PROCESS_NODES, ...TOOL_NODES]

function mountCanvas(locale: 'en' | 'ar' = 'en') {
  return mount(WorkflowCanvas, {
    props: { nodes: ALL_NODES, selectedNodeId: null, readonly: true },
    global: {
      plugins: [createI18n({ legacy: false, locale, fallbackLocale: 'en', messages: { en, ar } })],
    },
  })
}

function ariaLabel(wrapper: ReturnType<typeof mountCanvas>, nodeId: string): string | undefined {
  return wrapper.get(`[data-node-id="${nodeId}"]`).attributes('aria-label')
}

describe('node accessible name identifies the node, not only its type (#14657)', () => {
  it('org-person: names the person (unaffected by the fix, guards the template staying "{kind}: {name}")', () => {
    const wrapper = mountCanvas()
    const expected = en.workflow.canvas.nodeAriaLabelWithState
      .replace('{kind}', en.llc.orgChart.aiAgent)
      .replace('{name}', 'Ada Lovelace')
      .replace('{state}', en.llc.canvasRules.status.idle)

    expect(ariaLabel(wrapper, 'ceo')).toBe(expected)
  })

  it('org-group: names the unit (unaffected by the fix, guards the template staying "{kind}: {name}")', () => {
    const wrapper = mountCanvas()
    const expected = en.workflow.canvas.nodeAriaLabel
      .replace('{kind}', en.llc.orgChart.canvasGroupKind)
      .replace('{name}', 'Ada Lovelace unit')

    expect(ariaLabel(wrapper, 'org-group:ceo')).toBe(expected)
  })

  it('org-process: names the workflow and role, not the generic "Process" caption twice', () => {
    const wrapper = mountCanvas()
    const displayName = en.llc.orgChart.processDisplayName
      .replace('{workflow}', 'wf-quarterly')
      .replace('{role}', 'Head of Sales')
    const expected = en.workflow.canvas.nodeAriaLabel
      .replace('{kind}', en.llc.orgChart.processNodeLabel)
      .replace('{name}', displayName)

    expect(ariaLabel(wrapper, 'process:r1:wf-quarterly')).toBe(expected)
    expect(ariaLabel(wrapper, 'process:r1:wf-quarterly')).not.toBe(
      `${en.llc.orgChart.processNodeLabel}: ${en.llc.orgChart.processNodeLabel}`,
    )
  })

  it('org-tool: names the tool and the roles carrying it, not the generic "Tool" caption twice', () => {
    const wrapper = mountCanvas()
    const displayName = en.llc.orgChart.toolDisplayName
      .replace('{tool}', 'Salesforce')
      .replace('{roles}', 'Head of Ops, Head of Sales')
    const expected = en.workflow.canvas.nodeAriaLabel
      .replace('{kind}', en.llc.orgChart.toolNodeLabel)
      .replace('{name}', displayName)

    expect(ariaLabel(wrapper, 'tool:Salesforce')).toBe(expected)
    expect(ariaLabel(wrapper, 'tool:Salesforce')).not.toBe(
      `${en.llc.orgChart.toolNodeLabel}: ${en.llc.orgChart.toolNodeLabel}`,
    )
  })

  it('reads and identifies the tool node correctly in an RTL locale (ar)', () => {
    const wrapper = mountCanvas('ar')
    const displayName = ar.llc.orgChart.toolDisplayName
      .replace('{tool}', 'Salesforce')
      .replace('{roles}', 'Head of Ops, Head of Sales')
    const expected = ar.workflow.canvas.nodeAriaLabel
      .replace('{kind}', ar.llc.orgChart.toolNodeLabel)
      .replace('{name}', displayName)

    expect(ariaLabel(wrapper, 'tool:Salesforce')).toBe(expected)
    expect(ariaLabel(wrapper, 'tool:Salesforce')).not.toBe(
      `${ar.llc.orgChart.toolNodeLabel}: ${ar.llc.orgChart.toolNodeLabel}`,
    )
  })

  it('the search result label draws on the same "{kind}: {name}" text as the accessible name (#14611 consolidation)', async () => {
    const wrapper = mount(WorkflowCanvas, {
      props: { nodes: ALL_NODES, selectedNodeId: null, readonly: true },
      global: { plugins: [createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })] },
      attachTo: document.body,
    })

    await wrapper.get('[data-testid="canvas-search-input"]').setValue('Salesforce')
    const result = wrapper.get('[data-testid="canvas-search-result"]')
    const nodeAriaLabelText = ariaLabel(wrapper, 'tool:Salesforce')

    expect(result.text()).toBe(nodeAriaLabelText)
  })
})
