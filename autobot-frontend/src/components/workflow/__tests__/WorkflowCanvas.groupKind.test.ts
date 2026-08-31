// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #14596, second half: a team box and a reporting-unit box looked identical.
//
// #14614 gave teams their own id namespace, caption and section, but both
// reused `org-group`'s CSS — so the only visual difference was the words
// inside. The renderer now reads a `kind` off the container and styles the two
// differently.
//
// Colour is not the only signal: the border style differs too, which is the
// rule #13941 established on this canvas after a coloured dot was found to be
// the sole carrier of node status.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

import WorkflowCanvas from '../WorkflowCanvas.vue'
import {
  buildOrgCanvasGraph,
  buildTeamCanvasNodes,
  GROUP_KIND_TEAM,
  GROUP_KIND_UNIT,
} from '@/composables/llc/orgCanvasGraph'
import { buildOrgPeople } from '@/composables/llc/orgPeople'

const TREE = [
  {
    id: 'lead',
    node_id: 'n-lead',
    name: 'Ada',
    title: 'Lead',
    is_human: true,
    children: [
      { id: 'rep', node_id: 'n-rep', name: 'Grace', title: 'Rep', is_human: true, children: [] },
    ],
  },
]

const TEAMS = [{ id: 't1', name: 'Sales', member_user_ids: ['lead'] }]

// #14860: one shared instance for the whole file. A fresh createI18n per
// mount re-ingested the ~400KB message bundle every time; nothing here
// mutates the instance, so building it once is enough.
const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

function mountCanvas(nodes: unknown[]) {
  return mount(WorkflowCanvas, {
    props: { nodes, selectedNodeId: null, readonly: true },
    global: { plugins: [i18n] },
  })
}

/** Both container kinds on one canvas — the case where confusing them matters. */
function bothKinds() {
  // Built by the real producers, never hand-rolled: a hand-written node can
  // drift into a shape nothing emits, and then the test passes against data
  // the canvas never receives.
  const unitNodes = buildOrgCanvasGraph(TREE as never, (name: string) => `${name} unit`)
  const people = buildOrgPeople(TREE as never, [])
  const teamNodes = buildTeamCanvasNodes(
    new Map(),
    people,
    TEAMS as never,
    0,
    (name: string) => `${name} team`,
  )
  return [...unitNodes, ...teamNodes]
}

describe('a team container is drawn differently from a reporting unit (#14596)', () => {
  it('marks each container with its kind', () => {
    const wrapper = mountCanvas(bothKinds())
    const kinds = wrapper
      .findAll('.workflow-node.org-group')
      .map((n) => n.attributes('data-group-kind'))
      .filter(Boolean)

    // Both kinds present, and they differ — the whole point.
    expect(kinds).toContain(GROUP_KIND_UNIT)
    expect(kinds).toContain(GROUP_KIND_TEAM)
  })

  it('refuses the attribute on a non-container even if its data carries a kind', () => {
    // The guard is on the node TYPE, not on the presence of the field. Without
    // this case the guard is untestable: no producer puts `kind` on a person
    // today, so removing the type check changes nothing observable — and a
    // test that cannot fail is not evidence. This pins the rule against a
    // future producer that adds the field for its own reasons.
    const wrapper = mountCanvas([
      {
        id: 'user:ada',
        type: 'org-person',
        position: { x: 0, y: 0 },
        data: { title: 'Ada', kind: GROUP_KIND_TEAM },
        connections: [],
      },
    ])
    const person = wrapper.find('.workflow-node.org-person')

    expect(person.exists()).toBe(true)
    expect(person.attributes('data-group-kind')).toBeUndefined()
  })

  it('does not put the attribute on nodes that are not containers', () => {
    // An empty attribute still matches [data-group-kind] in CSS, so a person
    // node carrying one would pick up container styling.
    const wrapper = mountCanvas(bothKinds())
    const people = wrapper.findAll('.workflow-node.org-person')

    expect(people.length).toBeGreaterThan(0)
    for (const person of people) {
      expect(person.attributes('data-group-kind')).toBeUndefined()
    }
  })
})
