// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #20519: same-named agents are told apart; an agent the server says cannot run is marked.

import { describe, expect, it } from 'vitest'
import { agentLabel, agentLabelMap, agentOptionText, type LabelledAgent } from '../agentLabels'

const agent = (id: string, name: string, extra: Partial<LabelledAgent> = {}): LabelledAgent => ({ id, name, ...extra })

describe('agentLabelMap', () => {
  it('leaves a unique name alone', () => {
    const labels = agentLabelMap([agent('a1', 'Alex'), agent('b2', 'Blake')])
    expect([labels.get('a1'), labels.get('b2')]).toEqual(['Alex', 'Blake'])
  })

  it('adds the role only for agents whose names clash', () => {
    const labels = agentLabelMap([
      agent('a1', 'Alex', { title: 'CEO' }),
      agent('a2', 'alex', { title: 'Engineer' }),
      agent('b2', 'Blake', { title: 'CEO' }),
    ])
    expect(labels.get('a1')).toBe('Alex — CEO')
    expect(labels.get('a2')).toBe('alex — Engineer')
    expect(labels.get('b2')).toBe('Blake')
  })

  it('falls back to the adapter when there is no role', () => {
    const labels = agentLabelMap([
      agent('a1', 'Alex', { adapter_type: 'claude_code' }),
      agent('a2', 'Alex', { adapter_type: 'autobot_agent' }),
    ])
    expect(labels.get('a1')).toBe('Alex — claude_code')
  })

  it('adds a short id suffix only when name and role are both shared', () => {
    const labels = agentLabelMap([
      agent('node-0001-abcd', 'Alex', { title: 'Engineer' }),
      agent('node-0002-wxyz', 'Alex', { title: 'Engineer' }),
      agent('node-0003-qrst', 'Alex', { title: 'Lead' }),
    ])
    expect(labels.get('node-0001-abcd')).toBe('Alex — Engineer #abcd')
    expect(labels.get('node-0002-wxyz')).toBe('Alex — Engineer #wxyz')
    expect(labels.get('node-0003-qrst')).toBe('Alex — Lead')
    expect(new Set(labels.values()).size).toBe(3)
  })
})

describe('agentLabel', () => {
  it('uses the fallback for an id no agent has', () => {
    expect(agentLabel('gone', [agent('a1', 'Alex')], 'Unknown agent')).toBe('Unknown agent')
  })
})

describe('agentOptionText', () => {
  it('marks only an agent the server says cannot run', () => {
    const agents = [agent('a1', 'Alex', { can_run: true }), agent('a2', 'Blake', { can_run: false }), agent('a3', 'Casey')]
    const labels = agentLabelMap(agents)
    expect(agents.map((a) => agentOptionText(a, labels, 'Cannot run'))).toEqual(['Alex', 'Blake (Cannot run)', 'Casey'])
  })
})
