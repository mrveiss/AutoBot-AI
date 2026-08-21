// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #14611: the "open this node" link contract shared by the Company OS org
// canvas (consumer, `OrgChart.vue`) and whatever produces the link (a copied
// URL from the address bar, or a future "copy link" affordance).
//
// Mirrors `workflowDeepLink.test.ts` (#13963) test-for-test: the failure mode
// is the same silent one — a link that carries a node id the consumer cannot
// parse still opens the canvas and simply focuses nothing. Nobody sees an
// error; the click just does less than it promised.

import { describe, it, expect } from 'vitest'
import {
  canvasNodeIdFromQuery,
  canvasNodeLinkQuery,
  CANVAS_NODE_QUERY_KEY,
} from '../canvasNodeDeepLink'

describe('canvasNodeIdFromQuery (#14611)', () => {
  it('reads the node the link names', () => {
    expect(canvasNodeIdFromQuery({ [CANVAS_NODE_QUERY_KEY]: 'ceo' })).toBe('ceo')
  })

  it('takes the first when the key repeats', () => {
    // vue-router types a repeated query parameter as an array. Focusing one
    // node is the only sensible reading, and throwing would break a link a
    // user can produce by accident.
    expect(canvasNodeIdFromQuery({ [CANVAS_NODE_QUERY_KEY]: ['a', 'b'] })).toBe('a')
  })

  it('keeps a namespaced id intact', () => {
    // A process/tool/team-member canvas id embeds ':' internally
    // (`process:<role>:<workflow>`, `org-team:<group>:member:<id>`).
    expect(canvasNodeIdFromQuery({ [CANVAS_NODE_QUERY_KEY]: 'process:role-1:wf-1' })).toBe(
      'process:role-1:wf-1',
    )
  })

  it('asks for nothing when the key is absent', () => {
    expect(canvasNodeIdFromQuery({})).toBeNull()
    expect(canvasNodeIdFromQuery(undefined)).toBeNull()
    expect(canvasNodeIdFromQuery({ section: 'runner' })).toBeNull()
  })

  it('treats an empty or whitespace value as no request', () => {
    // `?node=` is reachable by hand-editing the URL. Resolving a node named
    // '' would match nothing and read as a broken feature.
    expect(canvasNodeIdFromQuery({ [CANVAS_NODE_QUERY_KEY]: '' })).toBeNull()
    expect(canvasNodeIdFromQuery({ [CANVAS_NODE_QUERY_KEY]: '   ' })).toBeNull()
    expect(canvasNodeIdFromQuery({ [CANVAS_NODE_QUERY_KEY]: [] })).toBeNull()
  })

  it('ignores a null or non-string value', () => {
    expect(canvasNodeIdFromQuery({ [CANVAS_NODE_QUERY_KEY]: null })).toBeNull()
    expect(canvasNodeIdFromQuery({ [CANVAS_NODE_QUERY_KEY]: undefined })).toBeNull()
  })

  it('trims surrounding whitespace rather than passing it through', () => {
    expect(canvasNodeIdFromQuery({ [CANVAS_NODE_QUERY_KEY]: '  ceo  ' })).toBe('ceo')
  })

  it('never collides with the outbound workflow link\'s own query key', () => {
    // #13963's `?workflow=` and #14611's `?node=` name different targets and
    // must be able to coexist on the same URL without either shadowing the
    // other.
    expect(CANVAS_NODE_QUERY_KEY).not.toBe('workflow')
  })
})

describe('canvasNodeLinkQuery (#14611)', () => {
  it('builds a query object naming exactly one node', () => {
    expect(canvasNodeLinkQuery('ceo')).toEqual({ [CANVAS_NODE_QUERY_KEY]: 'ceo' })
  })

  it('round-trips through canvasNodeIdFromQuery', () => {
    const query = canvasNodeLinkQuery('user:123')
    expect(canvasNodeIdFromQuery(query)).toBe('user:123')
  })
})
