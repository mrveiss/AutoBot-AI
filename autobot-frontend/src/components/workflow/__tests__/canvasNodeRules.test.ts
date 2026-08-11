// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * GH#13941: the rule layer itself — evaluation order, the derived tool rules,
 * and the legend derivation.
 *
 * The legend cases are the ones that matter: a legend built from
 * `rule.matches(facts)` rather than from the rule that actually *won* would
 * list swatches that appear nowhere on the canvas, which is precisely the
 * "renders something the data never says" failure this umbrella keeps hitting.
 */

import { describe, it, expect } from 'vitest'

import {
  OWNER_RULES,
  RULE_DIMENSIONS,
  STATUS_RULES,
  activeRules,
  matchRule,
  orgNodeFacts,
  rulesForDimension,
  toolRules,
  type CanvasNodeFacts,
} from '../canvasNodeRules'
import type { CanvasNode } from '../canvasNode'

function facts(over: Partial<CanvasNodeFacts> = {}): CanvasNodeFacts {
  return { status: 'idle', isHuman: false, adapterType: 'claude', ...over }
}

function personNode(data: Record<string, unknown>): CanvasNode {
  return { id: 'n', type: 'org-person', position: { x: 0, y: 0 }, data, connections: [] }
}

describe('canvas node facts (#13941)', () => {
  it('reads status, human flag and adapter off the node data bag', () => {
    const result = orgNodeFacts(
      personNode({ status: ' Paused ', is_human: false, adapter_type: ' claude ' }),
    )

    expect(result).toEqual({ status: 'paused', isHuman: false, adapterType: 'claude' })
  })

  it('returns null for a node the rules do not apply to', () => {
    const step: CanvasNode = {
      id: 's',
      type: 'step',
      position: { x: 0, y: 0 },
      data: { status: 'active' },
      connections: [],
    }

    expect(orgNodeFacts(step)).toBeNull()
  })

  it('treats a missing status and a non-boolean human flag as absent', () => {
    const result = orgNodeFacts(personNode({ is_human: 'yes' }))

    expect(result).toEqual({ status: '', isHuman: false, adapterType: '' })
  })
})

describe('rule evaluation (#13941)', () => {
  it('resolves each agent status to its own rule', () => {
    for (const status of ['active', 'idle', 'paused', 'error', 'terminated']) {
      expect(matchRule(STATUS_RULES, facts({ status })).id).toBe(`status-${status}`)
    }
  })

  it('falls through to the unknown rule for a status outside the vocabulary', () => {
    expect(matchRule(STATUS_RULES, facts({ status: 'in_sprint' })).id).toBe('status-unknown')
    expect(matchRule(STATUS_RULES, facts({ status: '' })).id).toBe('status-unknown')
  })

  it('separates a person, an agent and a node with no owner information', () => {
    expect(matchRule(OWNER_RULES, facts({ isHuman: true })).id).toBe('owner-human')
    expect(matchRule(OWNER_RULES, facts({ isHuman: false, adapterType: 'ollama' })).id).toBe(
      'owner-agent',
    )
    expect(matchRule(OWNER_RULES, facts({ isHuman: false, adapterType: '' })).id).toBe(
      'owner-unassigned',
    )
  })

  it('gives every rule a distinct shape within its dimension', () => {
    // Colour is never the only signal: two rules that share a hue in a
    // colour-blind rendering must still differ by marker shape.
    const shapes = STATUS_RULES.map((rule) => rule.shape)
    expect(new Set(shapes).size).toBe(STATUS_RULES.length)
    expect(new Set(OWNER_RULES.map((rule) => rule.shape)).size).toBe(OWNER_RULES.length)
  })
})

describe('tool rules are derived from the data (#13941)', () => {
  const onCanvas = [
    facts({ adapterType: 'ollama' }),
    facts({ adapterType: 'claude' }),
    facts({ adapterType: 'ollama' }),
    facts({ isHuman: true, adapterType: 'human' }),
  ]

  it('emits one rule per distinct adapter, in sorted order, plus a catch-all', () => {
    const rules = toolRules(onCanvas)

    expect(rules.map((rule) => rule.id)).toEqual(['tool-claude', 'tool-ollama', 'tool-none'])
    expect(rules.map((rule) => rule.swatch)).toEqual(['tool-1', 'tool-2', 'tool-none'])
  })

  it('labels a tool with the raw data value, never an invented UI string', () => {
    const [claude] = toolRules(onCanvas)

    expect(claude.labelKey).toBeNull()
    expect(claude.labelText).toBe('claude')
  })

  it('never assigns a person an adapter bucket — their adapter_type is "human"', () => {
    const rules = toolRules(onCanvas)

    expect(matchRule(rules, facts({ isHuman: true, adapterType: 'human' })).id).toBe('tool-none')
    expect(rules.some((rule) => rule.labelText === 'human')).toBe(false)
  })

  it('wraps the palette rather than running out of swatches', () => {
    const many = Array.from({ length: 10 }, (_, i) => facts({ adapterType: `a${i}` }))

    const swatches = toolRules(many).map((rule) => rule.swatch)
    expect(swatches.slice(0, 10)).toEqual([
      'tool-1',
      'tool-2',
      'tool-3',
      'tool-4',
      'tool-5',
      'tool-6',
      'tool-7',
      'tool-8',
      'tool-1',
      'tool-2',
    ])
  })
})

describe('legend derivation (#13941)', () => {
  it('lists only the rules that won on a node currently drawn', () => {
    const drawn = [facts({ status: 'active' }), facts({ status: 'paused' })]

    expect(activeRules(STATUS_RULES, drawn).map((rule) => rule.id)).toEqual([
      'status-active',
      'status-paused',
    ])
  })

  it('never lists a catch-all that lost to an earlier rule', () => {
    // The case that must stay caught: `status-unknown` matches everything, so a
    // legend built from `matches()` would always show it.
    const drawn = [facts({ status: 'active' })]

    expect(activeRules(STATUS_RULES, drawn).map((rule) => rule.id)).toEqual(['status-active'])
  })

  it('lists the catch-all once a node actually falls through to it', () => {
    const drawn = [facts({ status: 'active' }), facts({ status: 'on_leave' })]

    expect(activeRules(STATUS_RULES, drawn).map((rule) => rule.id)).toEqual([
      'status-active',
      'status-unknown',
    ])
  })

  it('is empty when nothing is drawn', () => {
    expect(activeRules(STATUS_RULES, [])).toEqual([])
  })
})

describe('dimension lookup (#13941)', () => {
  it('offers exactly status, owner and tool', () => {
    expect([...RULE_DIMENSIONS]).toEqual(['status', 'owner', 'tool'])
  })

  it('returns the right rule set for each dimension', () => {
    const drawn = [facts()]

    expect(rulesForDimension('status', drawn)).toBe(STATUS_RULES)
    expect(rulesForDimension('owner', drawn)).toBe(OWNER_RULES)
    expect(rulesForDimension('tool', drawn).map((rule) => rule.id)).toEqual([
      'tool-claude',
      'tool-none',
    ])
  })
})
