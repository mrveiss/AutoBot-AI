// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #21512: the sidebar's company switch must not carry the old company's record ids into the new
// company's URL. Table-driven over every record of the company route tree, with the params of each
// record read from its own joined path, so a route added later is covered without a hand-kept list
// -- and one that brings a param of a new kind fails the guard case until someone decides what the
// switch does with it.

import { describe, it, expect, vi } from 'vitest'
import type { RouteRecordRaw } from 'vue-router'

vi.mock('@/views/WorkflowBuilderView.vue', () => ({ default: { render: () => null } }))

import { llcCompanyChildren } from '@/router/llcRoutes'
import { companySwitchTarget } from '@/router/llcCompanySwitch'

const PARENT_PATH = '/llc/companies/:companyId'

interface Flat {
  name: string | undefined
  path: string
  params: string[]
  redirect: boolean
}

/** Every record of the tree, nested ones included, with the path joined from its ancestors. */
function flatten(records: RouteRecordRaw[], base: string): Flat[] {
  return records.flatMap((record) => {
    const path = `${base}/${record.path}`.replace(/\/+$/, '')
    const own: Flat = {
      name: typeof record.name === 'string' ? record.name : undefined,
      path,
      params: [...path.matchAll(/:([A-Za-z0-9_]+)/g)].map((m) => m[1]),
      redirect: record.redirect !== undefined,
    }
    return [own, ...flatten(record.children ?? [], path)]
  })
}

const ALL = flatten(llcCompanyChildren, PARENT_PATH)
const NAMED = ALL.filter((r): r is Flat & { name: string } => r.name !== undefined)

/** Records whose URL carries an id owned by the company, and where the switch sends each. */
const OWNED_ID_TARGETS: Record<string, string> = {
  'llc-sprint-board': 'llc-backlog',
  'llc-kanban-board': 'llc-backlog',
  'llc-programs': 'llc-portfolios',
  'llc-projects': 'llc-portfolios',
}

const ownedIdParams = (r: Flat): string[] => r.params.filter((p) => p !== 'companyId' && p.endsWith('Id'))

/** The route as the sidebar sees it: the record's name and every param filled in. */
function currentRoute(r: Flat & { name: string }) {
  return { name: r.name, params: Object.fromEntries(r.params.map((p) => [p, `${p}-old`])) }
}

describe('companySwitchTarget over every company route (#21512)', () => {
  it('reads the tree it is supposed to cover', () => {
    expect(NAMED.length).toBeGreaterThan(20)
    expect(NAMED.map((r) => r.name)).toEqual(expect.arrayContaining(['llc-ledger', 'automation-section', 'llc-programs']))
  })

  it('has no unnamed record other than a redirect', () => {
    expect(ALL.filter((r) => r.name === undefined && !r.redirect).map((r) => r.path)).toEqual([])
  })

  it('knows every route that carries an id owned by the company', () => {
    const withOwnedId = NAMED.filter((r) => ownedIdParams(r).length > 0).map((r) => r.name)
    expect(withOwnedId.sort()).toEqual(Object.keys(OWNED_ID_TARGETS).sort())
  })

  it('has only companyId, owned ids and the automation section as params', () => {
    const unexpected = NAMED.flatMap((r) =>
      r.params.filter((p) => p !== 'companyId' && p !== 'section' && !p.endsWith('Id')).map((p) => `${r.name}:${p}`),
    )
    expect(unexpected).toEqual([])
  })

  it.each(Object.entries(OWNED_ID_TARGETS))('%s lands on %s with only the new company', (name, target) => {
    const record = NAMED.find((r) => r.name === name)!
    expect(companySwitchTarget(currentRoute(record), 'c2')).toEqual({ name: target, params: { companyId: 'c2' } })
  })

  it.each(NAMED.filter((r) => ownedIdParams(r).length === 0).map((r) => [r.name, r] as const))(
    '%s keeps its name and its other params',
    (_name, record) => {
      const { params, name } = currentRoute(record)
      const { companyId: _old, ...others } = params
      expect(companySwitchTarget({ name, params }, 'c2')).toEqual({ name, params: { ...others, companyId: 'c2' } })
    },
  )

  it('keeps the automation section: it selects a view, it is not an id the company owns', () => {
    const route = { name: 'automation-section', params: { companyId: 'c1', section: 'overview' } }
    expect(companySwitchTarget(route, 'c2')).toEqual({
      name: 'automation-section',
      params: { companyId: 'c2', section: 'overview' },
    })
  })
})
