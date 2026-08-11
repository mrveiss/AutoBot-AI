// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// GH#13938: the kind of a person is derived from provenance plus the honest
// `is_human` flag — no fourth vocabulary for the actor axis (#13970). These
// tests pin the derivation and the grouping, including the cases where team
// data does not cover a kind at all.

import { describe, it, expect } from 'vitest'
import {
  buildOrgPeople,
  countByKind,
  groupPeopleByTeam,
  personKindOfOrgNode,
  UNGROUPED_TEAM_ID,
} from '../orgPeople'
import type { CompanyTeam, ContactSource, OrgChartPersonSource } from '../orgPeople'

const USER_ID = '11111111-1111-1111-1111-111111111111'

const ORG_NODES: OrgChartPersonSource[] = [
  {
    id: 'ceo',
    name: 'Ada',
    title: 'CEO',
    is_human: false,
    children: [{ id: 'dev', name: 'Alan', title: 'Engineer', is_human: false, children: [] }],
  },
  { id: `user:${USER_ID}`, name: 'Grace', title: 'lead', is_human: true, children: [] },
]

const CONTACTS: ContactSource[] = [
  { id: 'k1', full_name: 'Hedy', role_title: 'Supplier', email: 'hedy@example.test', phone: null },
]

describe('personKindOfOrgNode (#13938)', () => {
  it('reads an agent and a user out of the two-valued flag', () => {
    expect(personKindOfOrgNode({ is_human: false })).toBe('agent')
    expect(personKindOfOrgNode({ is_human: true })).toBe('user')
  })
})

describe('buildOrgPeople (#13938)', () => {
  it('returns every person of every kind, children included', () => {
    const people = buildOrgPeople(ORG_NODES, CONTACTS)

    expect(people.map((person) => person.name)).toEqual(['Ada', 'Alan', 'Grace', 'Hedy'])
    expect(people.map((person) => person.kind)).toEqual(['agent', 'agent', 'user', 'contact'])
  })

  it('keeps a contact out of the hierarchy — it has no org-chart node to open', () => {
    const contact = buildOrgPeople(ORG_NODES, CONTACTS).find((person) => person.kind === 'contact')!

    expect(contact.orgNodeId).toBeNull()
    expect(contact.userId).toBeNull()
    expect(contact.channel).toBe('hedy@example.test')
  })

  it('falls back to the phone when a contact has no email', () => {
    const people = buildOrgPeople(
      [],
      [{ id: 'k2', full_name: 'Bo', email: null, phone: '+371 20000000' }],
    )

    expect(people[0].channel).toBe('+371 20000000')
  })

  it('unwraps the `user:` namespace so team membership can key on the user id', () => {
    const user = buildOrgPeople(ORG_NODES, []).find((person) => person.kind === 'user')!

    expect(user.userId).toBe(USER_ID)
  })
})

describe('groupPeopleByTeam (#13938)', () => {
  const people = buildOrgPeople(ORG_NODES, CONTACTS)

  it('puts a user in their team and everyone else in the no-team bucket', () => {
    const teams: CompanyTeam[] = [{ id: 't1', name: 'Platform', member_user_ids: [USER_ID] }]

    const groups = groupPeopleByTeam(people, teams)

    expect(groups.map((group) => group.id)).toEqual(['t1', UNGROUPED_TEAM_ID])
    expect(groups[0].people.map((person) => person.name)).toEqual(['Grace'])
    expect(groups[1].people.map((person) => person.name)).toEqual(['Ada', 'Alan', 'Hedy'])
  })

  it('keeps an empty team rather than dropping it', () => {
    const groups = groupPeopleByTeam(people, [{ id: 't2', name: 'Legal', member_user_ids: [] }])

    expect(groups[0]).toEqual({ id: 't2', name: 'Legal', people: [] })
  })

  it('lists a person who is in two teams under both', () => {
    const groups = groupPeopleByTeam(people, [
      { id: 't1', name: 'Platform', member_user_ids: [USER_ID] },
      { id: 't3', name: 'Security', member_user_ids: [USER_ID] },
    ])

    expect(groups[0].people.map((person) => person.name)).toEqual(['Grace'])
    expect(groups[1].people.map((person) => person.name)).toEqual(['Grace'])
    // …and only once in the leftovers: not at all.
    expect(groups[2].people.map((person) => person.name)).toEqual(['Ada', 'Alan', 'Hedy'])
  })

  it('returns one ungrouped bucket when the company has no team at all', () => {
    const groups = groupPeopleByTeam(people, [])

    expect(groups).toHaveLength(1)
    expect(groups[0].id).toBe(UNGROUPED_TEAM_ID)
    expect(groups[0].people).toHaveLength(4)
  })

  it('ignores a team membership for a user the company does not list', () => {
    const groups = groupPeopleByTeam(people, [
      { id: 't4', name: 'Ghosts', member_user_ids: ['99999999-9999-9999-9999-999999999999'] },
    ])

    expect(groups[0].people).toEqual([])
    expect(groups[1].people).toHaveLength(4)
  })
})

describe('countByKind (#13938)', () => {
  it('counts all three kinds, including the zeroes', () => {
    expect(countByKind(buildOrgPeople(ORG_NODES, CONTACTS))).toEqual({
      agent: 2,
      user: 1,
      contact: 1,
    })
    expect(countByKind([])).toEqual({ agent: 0, user: 0, contact: 0 })
  })
})
