// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Tests for useEntityAnchors (#9479 — entity anchor click handler, #9297 follow-up)

import { describe, it, expect, vi } from 'vitest'
import {
  parseEntityAnchor,
  resolveEntityRoute,
  renderMarkdownLinks,
  createEntityAnchorClickHandler,
  type EntityKind,
} from '../useEntityAnchors'

describe('parseEntityAnchor', () => {
  it.each<[string, EntityKind, string]>([
    ['#session-abc123', 'session', 'abc123'],
    ['#document-42', 'document', '42'],
    ['#task-7', 'task', '7'],
    ['#workflow-build', 'workflow', 'build'],
    ['#knowledge-node-9', 'knowledge', 'node-9'],
  ])('parses %s into kind/id', (href, kind, id) => {
    expect(parseEntityAnchor(href)).toEqual({ kind, id })
  })

  it('returns null for non-entity hash anchors (headings)', () => {
    expect(parseEntityAnchor('#section-heading')).toBeNull() // "section" is not a kind
    expect(parseEntityAnchor('#heading')).toBeNull()
    expect(parseEntityAnchor('#unknown-1')).toBeNull()
  })

  it('returns null for external links and empty/missing hrefs', () => {
    expect(parseEntityAnchor('https://example.com')).toBeNull()
    expect(parseEntityAnchor('#')).toBeNull()
    expect(parseEntityAnchor('#document-')).toBeNull()
    expect(parseEntityAnchor('')).toBeNull()
    expect(parseEntityAnchor(null)).toBeNull()
    expect(parseEntityAnchor(undefined)).toBeNull()
  })
})

describe('resolveEntityRoute', () => {
  it('routes sessions and documents to their detail routes by param', () => {
    expect(resolveEntityRoute({ kind: 'session', id: 's1' })).toEqual({
      name: 'chat-session',
      params: { sessionId: 's1' },
    })
    expect(resolveEntityRoute({ kind: 'document', id: 'd1' })).toEqual({
      name: 'document-detail',
      params: { docId: 'd1' },
    })
  })

  it('routes tasks/workflows to automation and knowledge to the entity explorer via query', () => {
    expect(resolveEntityRoute({ kind: 'workflow', id: 'w1' })).toEqual({
      name: 'automation',
      query: { workflow: 'w1' },
    })
    expect(resolveEntityRoute({ kind: 'task', id: 't1' })).toEqual({
      name: 'automation',
      query: { task: 't1' },
    })
    expect(resolveEntityRoute({ kind: 'knowledge', id: 'k1' })).toEqual({
      name: 'knowledge-graph-entities',
      query: { entity: 'k1' },
    })
  })
})

describe('renderMarkdownLinks', () => {
  it('renders entity anchors as same-tab links', () => {
    expect(renderMarkdownLinks('see [Report](#document-42)')).toBe(
      'see <a href="#document-42">Report</a>',
    )
  })

  it('renders http(s) links as new-tab external links', () => {
    expect(renderMarkdownLinks('[site](https://example.com)')).toBe(
      '<a href="https://example.com" target="_blank" rel="noopener noreferrer">site</a>',
    )
  })

  it('drops unsafe schemes, keeping only the link text', () => {
    expect(renderMarkdownLinks('[x](javascript:doEvil)')).toBe('x')
  })

  it('escapes HTML in the link label', () => {
    expect(renderMarkdownLinks('[<b>hi</b>](#task-1)')).toBe(
      '<a href="#task-1">&lt;b&gt;hi&lt;/b&gt;</a>',
    )
  })
})

describe('createEntityAnchorClickHandler', () => {
  function clickEvent(anchor: { href: string } | null): MouseEvent {
    const anchorEl = anchor
      ? ({ getAttribute: () => anchor.href } as unknown as HTMLAnchorElement)
      : null
    const target = {
      closest: (sel: string) => (sel === 'a' ? anchorEl : null),
    } as unknown as HTMLElement
    return {
      target,
      preventDefault: vi.fn(),
    } as unknown as MouseEvent
  }

  it('navigates and prevents default for entity anchors', () => {
    const push = vi.fn().mockResolvedValue(undefined)
    const handler = createEntityAnchorClickHandler({ push })
    const ev = clickEvent({ href: '#document-42' })

    handler(ev)

    expect(ev.preventDefault).toHaveBeenCalled()
    expect(push).toHaveBeenCalledWith({ name: 'document-detail', params: { docId: '42' } })
  })

  it('does not interfere with external links', () => {
    const push = vi.fn()
    const handler = createEntityAnchorClickHandler({ push })
    const ev = clickEvent({ href: 'https://example.com' })

    handler(ev)

    expect(ev.preventDefault).not.toHaveBeenCalled()
    expect(push).not.toHaveBeenCalled()
  })

  it('does nothing when the click is not on an anchor', () => {
    const push = vi.fn()
    const handler = createEntityAnchorClickHandler({ push })
    const ev = clickEvent(null)

    handler(ev)

    expect(ev.preventDefault).not.toHaveBeenCalled()
    expect(push).not.toHaveBeenCalled()
  })
})
