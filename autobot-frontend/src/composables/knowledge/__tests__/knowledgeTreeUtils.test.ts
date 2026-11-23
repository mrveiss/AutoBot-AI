// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The Knowledge Browser's pure tree helpers (#18244), pinned against the behaviour
 * KnowledgeBrowser.vue had before they moved out of it.
 */
import { describe, it, expect, vi } from 'vitest'
import type { TreeNode } from '@/components/knowledge/TreeNodeComponent.vue'
import {
  buildNestedTree,
  buildTreeFromCategoryFacts,
  buildTreeFromEntries,
  collectUnvectorizedFiles,
  expandedIdsForPaths,
  extractFileIdsAndNames,
  filterTreeByQuery,
  findNode,
  getExpandedPaths,
  matchesMainCategory,
} from '../knowledgeTreeUtils'

const fact = (filename: string, key?: string, content = 'snippet') => ({ key, title: filename, content, metadata: { filename } })

describe('matchesMainCategory', () => {
  it.each([
    ['autobot-documentation', 'AutoBot_Docs', true],
    ['autobot-documentation', 'cooking', false],
    ['system-knowledge', 'man_pages', true],
    ['system-knowledge', 'cooking', false],
    ['user-knowledge', 'cooking', true],
    ['user-knowledge', 'autobot_docs', false],
    ['user-knowledge', 'system_commands', false],
  ])('%s vs %s -> %s', (main, cat, expected) => {
    expect(matchesMainCategory(cat, main)).toBe(expected)
  })

  it('matches everything when no main category is chosen or the id is unknown', () => {
    expect(matchesMainCategory('anything', null)).toBe(true)
    expect(matchesMainCategory('anything', 'other')).toBe(true)
  })
})

describe('buildNestedTree', () => {
  const tree = buildNestedTree(
    [fact('docs/api/endpoints.md', 'fact:a'), fact('docs/readme.md', 'fact:b'), fact('top.md'), fact('Plain title', 'fact:c')],
    'cat',
  )

  it('nests by path segment: folders first, then root-level files', () => {
    expect(tree.map((n) => [n.type, n.name])).toEqual([
      ['folder', 'docs'],
      ['file', 'top.md'],
      ['file', 'Plain title'],
    ])
    const docs = tree[0]
    expect(docs).toMatchObject({ id: 'folder-cat-docs', path: '/cat/docs', category: 'cat' })
    expect(docs.children?.map((n) => n.name)).toEqual(['api', 'readme.md'])
    expect(docs.children?.[0].children?.[0]).toMatchObject({ name: 'endpoints.md', type: 'file' })
  })

  it('takes the file id from the fact key without its prefix, and keeps the key in metadata', () => {
    const leaf = tree[0].children![1]
    expect(leaf.id).toBe('b')
    expect(leaf.metadata?.key).toBe('fact:b')
    expect(leaf.path).toBe('/cat/docs/readme.md')
  })

  it('gives a keyless fact a synthetic id and carries the snippet as content and size', () => {
    const leaf = tree[1]
    expect(leaf.id).toBe('fact-cat-2')
    expect(leaf.content).toBe('snippet')
    expect(leaf.size).toBe('snippet'.length)
  })
})

describe('buildNestedTree with hostile path segments', () => {
  it('keeps __proto__ and _files as ordinary folders, with no prototype pollution and no throw', () => {
    const build = () =>
      buildNestedTree([fact('__proto__/x/y.md', 'fact:a'), fact('_files/a.md', 'fact:b'), fact('_files/b.md', 'fact:c')], 'cat')
    expect(build).not.toThrow()
    const tree = build()
    expect(({} as Record<string, unknown>).x).toBeUndefined()
    expect(tree.map((n) => n.name)).toEqual(['__proto__', '_files'])
    expect(tree[1].children?.map((n) => n.name)).toEqual(['a.md', 'b.md'])
  })
})

describe('buildTreeFromCategoryFacts / buildTreeFromEntries', () => {
  it('makes one numbered top-level folder per category, named by the formatter', () => {
    const nodes = buildTreeFromCategoryFacts({ a: [fact('x.md')], b: [] }, (c) => c.toUpperCase())
    expect(nodes.map((n) => [n.id, n.name, n.path])).toEqual([
      ['folder-0', 'A', '/a'],
      ['folder-1', 'B', '/b'],
    ])
    expect(nodes[0].children).toHaveLength(1)
  })

  it('groups flat entries by category, defaulting to Uncategorized', () => {
    const nodes = buildTreeFromEntries([{ title: 't1', category: 'c1' }, { source: 's2' }], (c) => c)
    expect(nodes.map((n) => n.name)).toEqual(['c1', 'Uncategorized'])
    expect(nodes[1].children?.[0].name).toBe('s2')
    expect(buildTreeFromEntries(null as never, (c) => c)).toEqual([])
  })
})

describe('filterTreeByQuery', () => {
  const nodes = buildNestedTree([fact('docs/Alpha.md', 'fact:a'), fact('docs/beta.md', 'fact:b'), fact('gamma.md', 'fact:c')], 'cat')

  it('keeps matching leaves and the folders that hold them, case-insensitively', () => {
    const open = vi.fn()
    const out = filterTreeByQuery(nodes, 'ALPHA', open)
    expect(out.map((n) => n.name)).toEqual(['docs'])
    expect(out[0].children?.map((n) => n.name)).toEqual(['Alpha.md'])
    expect(open).toHaveBeenCalledWith('folder-cat-docs')
  })

  it('keeps a matching folder with all its children', () => {
    const out = filterTreeByQuery(nodes, 'docs', () => {})
    expect(out[0].children).toHaveLength(2)
  })

  it('returns nothing for a query that matches nothing', () => {
    expect(filterTreeByQuery(nodes, 'zzz', () => {})).toEqual([])
  })
})

describe('expansion across a rebuild', () => {
  const before = buildTreeFromCategoryFacts({ cat: [fact('docs/a.md', 'fact:a')] }, (c) => c)
  const after = buildTreeFromCategoryFacts({ other: [], cat: [fact('docs/a.md', 'fact:a')] }, (c) => c)

  it('restores by path, so renumbered folder ids still open', () => {
    const paths = getExpandedPaths(before, new Set(['folder-0', 'folder-cat-docs']))
    expect([...paths].sort()).toEqual(['/cat', '/cat/docs'])
    expect([...expandedIdsForPaths(after, paths)].sort()).toEqual(['folder-1', 'folder-cat-docs'])
  })
})

describe('node lookups', () => {
  const tree = buildNestedTree([fact('docs/a.md', 'fact:a'), fact('docs/b.md', 'fact:b')], 'cat')

  it('finds a nested node by id, or null', () => {
    expect(findNode(tree, 'b')?.name).toBe('b.md')
    expect(findNode(tree, 'nope')).toBeNull()
  })

  it('lists every file id with its name, ignoring folders', () => {
    const { ids, names } = extractFileIdsAndNames(tree)
    expect(ids).toEqual(['a', 'b'])
    expect(names.get('a')).toBe('a.md')
  })

  it('collects the files under a folder that are not vectorized', () => {
    const status = (id: string) => (id === 'a' ? 'vectorized' : 'pending')
    expect(collectUnvectorizedFiles(tree[0] as TreeNode, status)).toEqual(['b'])
    expect(collectUnvectorizedFiles(tree[0].children![0], status)).toEqual([])
  })
})
