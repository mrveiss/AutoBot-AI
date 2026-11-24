// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import { describe, expect, it } from 'vitest'
import { joinAgents, summarise } from './agentsRoster'
import type { AgentOrgStatusItem, AvailableAgent } from '@/types/agents'

const available = (name: string, status = 'available'): AvailableAgent => ({
  name,
  description: '',
  capabilities: [],
  status,
})

const org = (id: string, name: string, tasks: number | null, rate: number | null): AgentOrgStatusItem => ({
  id,
  name,
  type: 'worker',
  status: null,
  tasksCompleted: tasks,
  successRate: rate,
})

describe('joinAgents', () => {
  it('joins an org item to a roster agent by id', () => {
    const [row] = joinAgents([available('research_agent')], [org('research_agent', 'Research Agent', 4, 90)], {})
    expect(row.tasksCompleted).toBe(4)
    expect(row.successRate).toBe(90)
    expect(row.type).toBe('worker')
  })

  it('joins by display name too', () => {
    const [row] = joinAgents([available('Research Agent')], [org('research_agent', 'Research Agent', 1, 50)], {})
    expect(row.tasksCompleted).toBe(1)
  })

  it('leaves stats null (never 0) when no org item matches', () => {
    const [row] = joinAgents([available('llama3.2:3b')], [org('other', 'Other', 9, 99)], { 'llama3.2:3b': 'llama3_2_3b' })
    expect(row.tasksCompleted).toBeNull()
    expect(row.successRate).toBeNull()
    expect(row.type).toBe('llama3_2_3b')
  })
})

describe('summarise', () => {
  it('keeps totals null when nothing is measured', () => {
    const rows = joinAgents([available('a')], [], {})
    expect(summarise(rows, 1)).toMatchObject({ total_tasks: null, avg_success_rate: null, active_agents: 1 })
  })

  it('sums and averages only measured values', () => {
    const rows = joinAgents([available('a'), available('b'), available('c')], [org('a', 'A', 2, 80), org('b', 'B', 3, 100)], {})
    expect(summarise(rows, 3)).toMatchObject({ total_tasks: 5, avg_success_rate: 90 })
  })
})
