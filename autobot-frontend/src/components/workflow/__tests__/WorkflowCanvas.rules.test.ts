// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * GH#13941: rule-based node colouring and the legend, asserted on rendered
 * output.
 *
 * Every case below reads the DOM the user gets — the class the node actually
 * carries, the text inside its chip, the entries the legend actually lists.
 * Mounting the component proves nothing; five features in this umbrella shipped
 * displaying nothing behind tests that asserted exactly that (#14062).
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
import type { CanvasNode } from '../canvasNode'

const RULES = en.llc.canvasRules

/** One org-chart person as `buildOrgCanvasGraph` hands it to the canvas. */
function person(id: string, data: Record<string, unknown>): CanvasNode {
  return {
    id,
    type: 'org-person',
    position: { x: 0, y: 0 },
    data: { label: id, title: 'role', ...data },
    connections: [],
  }
}

/**
 * Four people covering every branch the rules have: a running agent, a paused
 * agent on a second adapter, a person, and an agent whose status is outside the
 * display vocabulary and which carries no adapter at all.
 */
const ORG_NODES: CanvasNode[] = [
  person('ada', { status: 'active', adapter_type: 'claude', is_human: false }),
  person('bo', { status: 'paused', adapter_type: 'ollama', is_human: false }),
  person('cy', { status: 'idle', adapter_type: 'human', is_human: true }),
  person('dee', { status: 'on_leave', adapter_type: '', is_human: false }),
]

const WORKFLOW_NODES: CanvasNode[] = [
  {
    id: 'n1',
    type: 'step',
    position: { x: 10, y: 10 },
    data: { command: '', description: '', risk_level: 'low', requires_confirmation: true },
    connections: [],
  },
]

function mountCanvas(props: Record<string, unknown>, locale: 'en' | 'ar' = 'en') {
  return mount(WorkflowCanvas, {
    props: { selectedNodeId: null, readonly: true, ...props },
    global: {
      plugins: [createI18n({ legacy: false, locale, fallbackLocale: 'en', messages: { en, ar } })],
    },
  })
}

/** `data-rule-id` of each drawn person node, in document order. */
function ruleIds(wrapper: ReturnType<typeof mountCanvas>): (string | undefined)[] {
  return wrapper
    .findAll('.workflow-node.org-person')
    .map((node) => node.attributes('data-rule-id'))
}

/** The text of each legend entry, in document order. */
function legendLabels(wrapper: ReturnType<typeof mountCanvas>): string[] {
  return wrapper.findAll('.canvas-legend-item').map((item) => item.text())
}

describe('rules colour org nodes by status (#13941)', () => {
  it('gives every node the rule its own status selects', () => {
    const wrapper = mountCanvas({ nodes: ORG_NODES })

    expect(ruleIds(wrapper)).toEqual([
      'status-active',
      'status-paused',
      'status-idle',
      'status-unknown',
    ])
  })

  it('binds the swatch and the shape as classes on the node', () => {
    const wrapper = mountCanvas({ nodes: ORG_NODES })
    const paused = wrapper.findAll('.workflow-node.org-person')[1]

    expect(paused.classes()).toContain('rule-status-paused')
    expect(paused.classes()).toContain('rule-shape-bar')
  })

  it('names the rule in text on the node — colour is never the only signal', () => {
    const wrapper = mountCanvas({ nodes: ORG_NODES })
    const chips = wrapper.findAll('.workflow-node.org-person .rule-chip')

    expect(chips.map((chip) => chip.text())).toEqual([
      RULES.status.active,
      RULES.status.paused,
      RULES.status.idle,
      RULES.status.unknown,
    ])
  })

  it('pairs every node with a marker shape as well as a colour', () => {
    const wrapper = mountCanvas({ nodes: ORG_NODES })

    for (const node of wrapper.findAll('.workflow-node.org-person')) {
      expect(node.classes().some((cls) => cls.startsWith('rule-shape-'))).toBe(true)
      expect(node.find('.rule-marker').exists()).toBe(true)
      expect(node.find('.rule-chip-label').text()).not.toBe('')
    }
  })

  it('re-colours in place when a status changes without a relayout', () => {
    // #13996 merges a pause/resume into the drawn nodes rather than rebuilding
    // the graph, so the rule must follow the mutated data.
    const nodes = [person('ada', { status: 'active', adapter_type: 'claude', is_human: false })]
    const wrapper = mountCanvas({ nodes })

    expect(ruleIds(wrapper)).toEqual(['status-active'])

    return wrapper
      .setProps({
        nodes: [person('ada', { status: 'paused', adapter_type: 'claude', is_human: false })],
      })
      .then(() => {
        expect(ruleIds(wrapper)).toEqual(['status-paused'])
        expect(wrapper.get('.rule-chip').text()).toBe(RULES.status.paused)
      })
  })
})

describe('the legend lists what is on screen (#13941)', () => {
  it('lists exactly the rules that won on a drawn node', () => {
    const wrapper = mountCanvas({ nodes: ORG_NODES })

    expect(legendLabels(wrapper)).toEqual([
      RULES.status.active,
      RULES.status.idle,
      RULES.status.paused,
      RULES.status.unknown,
    ])
    // The case that must stay caught: nothing on screen is errored or
    // terminated, so neither may appear in the legend.
    expect(legendLabels(wrapper)).not.toContain(RULES.status.error)
    expect(legendLabels(wrapper)).not.toContain(RULES.status.terminated)
  })

  it('shrinks when the nodes it described leave the canvas', async () => {
    const wrapper = mountCanvas({ nodes: ORG_NODES })
    expect(legendLabels(wrapper)).toHaveLength(4)

    await wrapper.setProps({ nodes: [ORG_NODES[0]] })

    expect(legendLabels(wrapper)).toEqual([RULES.status.active])
  })

  it('carries the same swatch and shape the nodes carry', () => {
    const wrapper = mountCanvas({ nodes: ORG_NODES })
    const entry = wrapper.get('[data-rule-id="status-paused"].canvas-legend-item')

    expect(entry.classes()).toContain('rule-status-paused')
    expect(entry.classes()).toContain('rule-shape-bar')
    expect(entry.find('.rule-marker').exists()).toBe(true)
  })

  it('renders in the active locale, not in hard-coded English', () => {
    const wrapper = mountCanvas({ nodes: ORG_NODES }, 'ar')

    expect(wrapper.get('.canvas-legend-title').text()).toBe(ar.llc.canvasRules.legendTitle)
    expect(legendLabels(wrapper)).toContain(ar.llc.canvasRules.status.paused)
    expect(legendLabels(wrapper)).not.toContain(RULES.status.paused)
  })
})

describe('the colour dimension is switchable (#13941)', () => {
  async function switchTo(wrapper: ReturnType<typeof mountCanvas>, dimension: string) {
    await wrapper.get(`[data-testid="rule-mode-${dimension}"]`).trigger('click')
  }

  it('offers the three dimensions, with status selected by default', () => {
    const wrapper = mountCanvas({ nodes: ORG_NODES })
    const buttons = wrapper.findAll('.rule-mode-btn')

    expect(buttons.map((button) => button.text())).toEqual([
      RULES.dimension.status,
      RULES.dimension.owner,
      RULES.dimension.tool,
    ])
    expect(buttons[0].attributes('aria-pressed')).toBe('true')
  })

  it('re-colours by owner kind and re-derives the legend', async () => {
    const wrapper = mountCanvas({ nodes: ORG_NODES })

    await switchTo(wrapper, 'owner')

    expect(ruleIds(wrapper)).toEqual([
      'owner-agent',
      'owner-agent',
      'owner-human',
      'owner-unassigned',
    ])
    expect(legendLabels(wrapper)).toEqual([
      en.llc.orgChart.human,
      en.llc.orgChart.aiAgent,
      RULES.owner.unassigned,
    ])
  })

  it('re-colours by tool, labelling each bucket with the adapter itself', async () => {
    const wrapper = mountCanvas({ nodes: ORG_NODES })

    await switchTo(wrapper, 'tool')

    expect(ruleIds(wrapper)).toEqual(['tool-claude', 'tool-ollama', 'tool-none', 'tool-none'])
    expect(legendLabels(wrapper)).toEqual(['claude', 'ollama', RULES.tool.none])
    // A person's adapter_type is the literal "human" (#13936) — it must never
    // become a tool bucket of its own.
    expect(legendLabels(wrapper)).not.toContain('human')
  })

  it('assigns distinct palette swatches to distinct tools', async () => {
    const wrapper = mountCanvas({ nodes: ORG_NODES })

    await switchTo(wrapper, 'tool')
    const [ada, bo] = wrapper.findAll('.workflow-node.org-person')

    expect(ada.classes()).toContain('rule-tool-1')
    expect(bo.classes()).toContain('rule-tool-2')
  })
})

describe('workflow authoring is untouched by the rule layer (#13941)', () => {
  it('renders no legend and no colour-by control without org nodes', () => {
    const wrapper = mountCanvas({ nodes: WORKFLOW_NODES, readonly: false })

    expect(wrapper.find('[data-testid="canvas-legend"]').exists()).toBe(false)
    expect(wrapper.find('.rule-mode').exists()).toBe(false)
  })

  it('leaves an authoring node without a rule class or a rule id', () => {
    const wrapper = mountCanvas({ nodes: WORKFLOW_NODES, readonly: false })
    const step = wrapper.get('.workflow-node.step')

    expect(step.attributes('data-rule-id')).toBeUndefined()
    expect(step.classes().some((cls) => cls.startsWith('rule-'))).toBe(false)
  })

  it('keeps the three pan/zoom buttons the org canvas relies on', () => {
    // The colour-by control lives in the left half deliberately: #13939 pins
    // the right half at exactly three buttons in read-only mode.
    const wrapper = mountCanvas({ nodes: ORG_NODES })

    expect(wrapper.findAll('.toolbar-right .tool-btn')).toHaveLength(3)
  })
})
