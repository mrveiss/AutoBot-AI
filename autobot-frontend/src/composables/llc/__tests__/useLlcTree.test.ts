// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * Unit tests for the shared LLC tree helpers (#9909).
 */

import { describe, it, expect } from 'vitest'
import { markExpanded, buildTreeFromParent, mapTree } from '../useLlcTree'

interface TestNode {
  id: string
  children: TestNode[]
  expanded?: boolean
}

interface FlatItem {
  id: string
  parent_id: string | null
}

const toNode = (item: FlatItem): TestNode => ({ id: item.id, children: [], expanded: false })

describe('markExpanded', () => {
  it('expands top-level nodes and collapses all descendants', () => {
    const tree: TestNode[] = [
      {
        id: 'root',
        expanded: false,
        children: [
          { id: 'child', expanded: true, children: [{ id: 'grandchild', expanded: true, children: [] }] },
        ],
      },
    ]
    markExpanded(tree, true)
    expect(tree[0].expanded).toBe(true)
    expect(tree[0].children[0].expanded).toBe(false)
    expect(tree[0].children[0].children[0].expanded).toBe(false)
  })

  it('collapses everything when called with false', () => {
    const tree: TestNode[] = [
      { id: 'a', expanded: true, children: [{ id: 'b', expanded: true, children: [] }] },
    ]
    markExpanded(tree, false)
    expect(tree[0].expanded).toBe(false)
    expect(tree[0].children[0].expanded).toBe(false)
  })

  it('handles an empty forest', () => {
    expect(() => markExpanded([], true)).not.toThrow()
  })
})

describe('buildTreeFromParent', () => {
  it('assembles a forest from flat parent edges', () => {
    const flat: FlatItem[] = [
      { id: 'r1', parent_id: null },
      { id: 'c1', parent_id: 'r1' },
      { id: 'c2', parent_id: 'r1' },
      { id: 'g1', parent_id: 'c1' },
      { id: 'r2', parent_id: null },
    ]
    const roots = buildTreeFromParent(flat, 'id', 'parent_id', toNode)
    expect(roots.map((r) => r.id)).toEqual(['r1', 'r2'])
    expect(roots[0].children.map((c) => c.id)).toEqual(['c1', 'c2'])
    expect(roots[0].children[0].children.map((g) => g.id)).toEqual(['g1'])
    expect(roots[1].children).toEqual([])
  })

  it('treats items with an unknown parent as roots', () => {
    const flat: FlatItem[] = [{ id: 'a', parent_id: 'missing' }]
    const roots = buildTreeFromParent(flat, 'id', 'parent_id', toNode)
    expect(roots.map((r) => r.id)).toEqual(['a'])
  })

  it('treats self-referencing items as roots (no cycle)', () => {
    const flat: FlatItem[] = [{ id: 'a', parent_id: 'a' }]
    const roots = buildTreeFromParent(flat, 'id', 'parent_id', toNode)
    expect(roots.map((r) => r.id)).toEqual(['a'])
    expect(roots[0].children).toEqual([])
  })

  it('returns an empty forest for empty input', () => {
    expect(buildTreeFromParent([] as FlatItem[], 'id', 'parent_id', toNode)).toEqual([])
  })
})

describe('mapTree', () => {
  interface RawNode {
    name: string
    children?: RawNode[]
  }

  it('recursively maps a nested raw tree', () => {
    const raw: RawNode = {
      name: 'root',
      children: [{ name: 'child', children: [{ name: 'grandchild' }] }],
    }
    const mapped = mapTree(raw, (item, children: TestNode[]) => ({
      id: item.name.toUpperCase(),
      children,
      expanded: false,
    }))
    expect(mapped.id).toBe('ROOT')
    expect(mapped.children[0].id).toBe('CHILD')
    expect(mapped.children[0].children[0].id).toBe('GRANDCHILD')
  })

  it('defaults missing children to an empty array', () => {
    const mapped = mapTree({ name: 'leaf' } as RawNode, (item, children: TestNode[]) => ({
      id: item.name,
      children,
    }))
    expect(mapped.children).toEqual([])
  })
})
