// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * useExpansion Composable (#5306)
 *
 * Reusable expansion state for tree / accordion / row-expand UIs. Sister
 * primitive to `useBatchSelection<T, Key>` — same Set-keyed shape, different
 * intent: expansion is about visibility / disclosure, selection is about
 * action targeting. Kept separate so reader intent is preserved at the call
 * site (`isExpanded(node)` reads differently from `isSelected(node)`).
 *
 * Owns a `Set<Key>` of expanded keys and exposes `isExpanded(key)` /
 * `toggle(key)` / `expand(key)` / `collapse(key)` / `expandAll(keys)` /
 * `collapseAll()`. Mutations replace the Set on every write — defensive but
 * compatible with both `ref` and `shallowRef` consumers.
 */

import { ref, readonly } from 'vue'
import type { Ref } from 'vue'

export interface UseExpansionReturn<Key extends string | number = string> {
  /** Set of currently-expanded keys. Read-only; mutate via the helpers below. */
  expanded: Readonly<Ref<Set<Key>>>
  /** True if the given key is expanded. */
  isExpanded: (key: Key) => boolean
  /** Toggle expansion for one key. */
  toggle: (key: Key) => void
  /** Expand one key (idempotent). */
  expand: (key: Key) => void
  /** Collapse one key (idempotent). */
  collapse: (key: Key) => void
  /** Replace the expansion set with the given keys. */
  expandAll: (keys: Iterable<Key>) => void
  /** Collapse everything. */
  collapseAll: () => void
}

/**
 * Reusable expansion state for tree / accordion / row-expand UIs.
 *
 * @param initialKeys  Optional iterable of keys to seed the expanded set
 *                     (e.g. default-open categories in a settings dashboard).
 */
export function useExpansion<Key extends string | number = string>(
  initialKeys?: Iterable<Key>
): UseExpansionReturn<Key> {
  const expanded = ref(new Set<Key>(initialKeys ?? [])) as Ref<Set<Key>>

  function isExpanded(key: Key): boolean {
    return expanded.value.has(key)
  }

  function toggle(key: Key): void {
    const next = new Set(expanded.value)
    if (next.has(key)) {
      next.delete(key)
    } else {
      next.add(key)
    }
    expanded.value = next
  }

  function expand(key: Key): void {
    if (!expanded.value.has(key)) {
      const next = new Set(expanded.value)
      next.add(key)
      expanded.value = next
    }
  }

  function collapse(key: Key): void {
    if (expanded.value.has(key)) {
      const next = new Set(expanded.value)
      next.delete(key)
      expanded.value = next
    }
  }

  function expandAll(keys: Iterable<Key>): void {
    expanded.value = new Set(keys)
  }

  function collapseAll(): void {
    expanded.value = new Set()
  }

  return {
    // `readonly()` wraps the Set in DeepReadonly; we expose the original
    // surface (`Set<Key>`) as read-only because callers need `.has()` / `.size`
    // and we already control all mutations via the helpers. The double cast is
    // the standard Vue idiom for this TS2352 (non-overlapping types).
    expanded: readonly(expanded) as unknown as Readonly<Ref<Set<Key>>>,
    isExpanded,
    toggle,
    expand,
    collapse,
    expandAll,
    collapseAll
  }
}
