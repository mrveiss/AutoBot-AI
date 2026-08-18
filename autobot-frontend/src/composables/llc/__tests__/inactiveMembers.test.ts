// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #13956: deactivated and soft-deleted users kept appearing in the members
// picker and, since #13936, in the org chart — still selectable as assignees.
//
// The two surfaces answer different questions, and the issue is explicit that
// they must not diverge in what they consider inactive:
//
//   picker    — who can be given work?      inactive people are NOT offered
//   org chart — who is in this company?     inactive people ARE shown, marked
//
// Filtering the org chart instead would be the wrong fix: their work items and
// the role they held stay behind, so a chart that omits them cannot explain who
// those belong to.

import { describe, it, expect } from 'vitest'
import { buildOrgPeople } from '../orgPeople'
import type { OrgChartPersonSource } from '../orgPeople'

const NODES: OrgChartPersonSource[] = [
  { id: 'user:active', name: 'Ada', title: 'lead', is_human: true, is_active: true },
  { id: 'user:gone', name: 'Grace', title: 'member', is_human: true, is_active: false },
  // An agent: the field is absent entirely, which must not read as inactive.
  { id: 'agent-1', name: 'Runner', title: 'worker', is_human: false },
]

describe('inactive people on the org chart (#13956)', () => {
  it('marks a deactivated person instead of dropping them', () => {
    const people = buildOrgPeople(NODES, [])

    // Present — the chart still explains who holds their work and role.
    expect(people.map((p) => p.name)).toContain('Grace')
    expect(people.find((p) => p.name === 'Grace')?.isInactive).toBe(true)
  })

  it('does not mark an active person', () => {
    const people = buildOrgPeople(NODES, [])
    expect(people.find((p) => p.name === 'Ada')?.isInactive).toBe(false)
  })

  it('does not mark an agent, which has no account to deactivate', () => {
    // The field is absent for agents. A falsy test would mark every one of
    // them, and would mark every person too against a server that predates
    // the field.
    const people = buildOrgPeople(NODES, [])
    expect(people.find((p) => p.name === 'Runner')?.isInactive).toBe(false)
  })

  it('does not mark a contact, which has no account at all', () => {
    const people = buildOrgPeople([], [{ id: 'c1', full_name: 'Supplier' }])
    expect(people.find((p) => p.name === 'Supplier')?.isInactive).toBe(false)
  })
})
