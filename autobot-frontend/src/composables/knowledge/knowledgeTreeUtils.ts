// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Pure tree helpers for the Knowledge Browser (#18244).
 *
 * Moved out of KnowledgeBrowser.vue unchanged in behaviour: nesting facts by the
 * path segments of their filename, filtering by main category and by a search
 * query, and saving / restoring which folders are expanded across a rebuild.
 */
import type { TreeNode } from '@/components/knowledge/TreeNodeComponent.vue'

/** Loose shape of a knowledge fact as the KB endpoints return it (Record<string, unknown> on the wire). */
export interface KnowledgeFactLike {
  key?: string
  title?: string
  source?: string
  content?: string
  // Issue #12370: full_content is not in the browse list; it is lazy-loaded per fact.
  timestamp?: string
  created_at?: string
  category?: string
  metadata?: Record<string, unknown>
}

/**
 * Nested folder scaffold. Folders live in a Map and leaves in their own field, so a
 * user-controlled path segment (`__proto__`, `constructor`, `_files`) can neither reach
 * the prototype chain nor collide with the leaf bucket.
 */
interface NestedDir {
  files: TreeNode[]
  dirs: Map<string, NestedDir>
}

const newDir = (): NestedDir => ({ files: [], dirs: new Map() })

const AUTOBOT_DOC_HINTS = ['autobot', 'documentation', 'docs']
const SYSTEM_HINTS = ['man', 'system', 'command', 'os', 'machine']

const hasHint = (name: string, hints: string[]) => hints.some((h) => name.includes(h))

/** True when a category name belongs to the given main category (user = everything else). */
export function matchesMainCategory(category: string | undefined, mainId: string | null): boolean {
  if (!mainId) return true
  const name = category?.toLowerCase() || ''
  if (mainId === 'autobot-documentation') return hasHint(name, AUTOBOT_DOC_HINTS)
  if (mainId === 'system-knowledge') return hasHint(name, SYSTEM_HINTS)
  if (mainId === 'user-knowledge') return !hasHint(name, AUTOBOT_DOC_HINTS) && !hasHint(name, SYSTEM_HINTS)
  return true
}

function toFileNode(fact: KnowledgeFactLike, part: string, category: string, filename: string, idx: number): TreeNode {
  // The actual fact ID is the Redis key without its "fact:" prefix.
  const factId = fact.key ? fact.key.replace('fact:', '') : `fact-${category}-${idx}`
  // Issue #12370: the list carries only the snippet; the full text is lazy-loaded on open.
  const snippet = (fact.content || '') as string
  return {
    id: factId,
    name: part,
    type: 'file' as const,
    path: `/${category}/${filename}`,
    category,
    size: snippet.length,
    content: snippet,
    metadata: { ...fact.metadata, key: fact.key },
  }
}

function insertFact(root: NestedDir, fact: KnowledgeFactLike, category: string, idx: number): void {
  const filename = (fact.metadata?.filename || fact.title || `Fact ${idx + 1}`) as string
  const parts = filename.split('/').filter((p: string) => p)
  let current = root
  parts.forEach((part, i) => {
    if (i === parts.length - 1) {
      current.files.push(toFileNode(fact, part, category, filename, idx))
      return
    }
    let next = current.dirs.get(part)
    if (!next) {
      next = newDir()
      current.dirs.set(part, next)
    }
    current = next
  })
}

function toFolderNodes(dir: NestedDir, category: string, prefix = ''): TreeNode[] {
  return Array.from(dir.dirs.entries())
    .map(([key, sub]) => {
      const folderPath = prefix ? `${prefix}/${key}` : key
      return {
        id: `folder-${category}-${folderPath}`,
        name: key,
        type: 'folder' as const,
        path: `/${category}/${folderPath}`,
        category,
        children: [...toFolderNodes(sub, category, folderPath), ...sub.files],
      }
    })
}

/** Nest a category's facts into folders by the path segments of their filename. */
export function buildNestedTree(facts: Record<string, unknown>[], category: string): TreeNode[] {
  const root = newDir()
  ;(facts as KnowledgeFactLike[]).forEach((fact, idx) => insertFact(root, fact, category, idx))
  return [...toFolderNodes(root, category), ...root.files]
}

/** One top-level folder per category, each holding its nested tree. */
export function buildTreeFromCategoryFacts(
  byCategory: Record<string, Record<string, unknown>[]>,
  folderName: (category: string) => string,
): TreeNode[] {
  return Object.keys(byCategory).map((category, idx) => ({
    id: `folder-${idx}`,
    name: folderName(category),
    type: 'folder' as const,
    path: `/${category}`,
    category,
    children: buildNestedTree(byCategory[category] || [], category),
  }))
}

/** Group flat entries by category (the cursor-paginated /entries shape). */
export function buildTreeFromEntries(entries: Record<string, unknown>[], folderName: (c: string) => string): TreeNode[] {
  const byCategory = new Map<string, TreeNode[]>()
  ;(Array.isArray(entries) ? (entries as KnowledgeFactLike[]) : []).forEach((entry, idx) => {
    const category = entry.category || 'Uncategorized'
    const file: TreeNode = {
      id: `file-${idx}`,
      name: entry.title || entry.source || `Entry ${idx + 1}`,
      type: 'file',
      path: `/${category}/${entry.title || entry.source}`,
      size: entry.content?.length || 0,
      date: entry.timestamp || entry.created_at,
      category,
      metadata: entry,
    }
    byCategory.set(category, [...(byCategory.get(category) ?? []), file])
  })
  return Array.from(byCategory.entries()).map(([category, files], idx) => ({
    id: `folder-${idx}`,
    name: folderName(category),
    type: 'folder' as const,
    path: `/${category}`,
    category,
    children: files,
  }))
}

/**
 * Keep the nodes whose name matches (or that hold a match). `onFolderMatch` is told
 * about every folder kept, so the caller can expand it.
 */
export function filterTreeByQuery(nodes: TreeNode[], query: string, onFolderMatch: (id: string) => void): TreeNode[] {
  const q = query.toLowerCase()
  return nodes.reduce((acc: TreeNode[], node) => {
    const matches = node.name.toLowerCase().includes(q)
    const children = node.children ? filterTreeByQuery(node.children, q, onFolderMatch) : []
    if (!matches && children.length === 0) return acc
    acc.push({ ...node, children: children.length > 0 ? children : node.children })
    if (node.type === 'folder') onFolderMatch(node.id)
    return acc
  }, [])
}

export function findNode(nodes: TreeNode[], id: string): TreeNode | null {
  for (const node of nodes) {
    if (node.id === id) return node
    const found = node.children ? findNode(node.children, id) : null
    if (found) return found
  }
  return null
}

/** Paths of the expanded nodes, so the expansion survives a rebuild that renumbers ids. */
export function getExpandedPaths(nodes: TreeNode[], expandedIds: Set<string>): Set<string> {
  const paths = new Set<string>()
  const walk = (list: TreeNode[]) => {
    for (const node of list) {
      if (expandedIds.has(node.id)) paths.add(node.path)
      if (node.children) walk(node.children)
    }
  }
  walk(nodes)
  return paths
}

/** The ids, in the rebuilt tree, of the nodes whose path was expanded. */
export function expandedIdsForPaths(nodes: TreeNode[], paths: Set<string>): Set<string> {
  const ids = new Set<string>()
  const walk = (list: TreeNode[]) => {
    for (const node of list) {
      if (paths.has(node.path)) ids.add(node.id)
      if (node.children) walk(node.children)
    }
  }
  walk(nodes)
  return ids
}

/** Every file id under the nodes, with its display name (for the vectorization status fetch). */
export function extractFileIdsAndNames(nodes: TreeNode[]): { ids: string[]; names: Map<string, string> } {
  const ids: string[] = []
  const names = new Map<string, string>()
  const walk = (list: TreeNode[]) => {
    for (const node of list) {
      if (node.type === 'file') {
        ids.push(node.id)
        names.set(node.id, node.name)
      } else if (node.children) {
        walk(node.children)
      }
    }
  }
  walk(nodes)
  return { ids, names }
}

/** Ids of the files under a node whose status is not 'vectorized'. */
export function collectUnvectorizedFiles(node: TreeNode, statusOf: (id: string) => string): string[] {
  if (node.type === 'file') return statusOf(node.id) !== 'vectorized' ? [node.id] : []
  return (node.children ?? []).flatMap((child) => collectUnvectorizedFiles(child, statusOf))
}
