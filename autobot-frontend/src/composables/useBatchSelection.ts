// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * useBatchSelection Composable (#5192)
 *
 * Reusable multi-select state for list components. Extracted from
 * `useKnowledgeVectorization.ts:295-336` so 6+ KB list components can share the
 * same toggle/selectAll/clear logic.
 *
 * The composable owns a `Set<Key>` of selected keys, keeps derived `allSelected`
 * / `someSelected` / `selectedCount` / `selectedItems` in sync with a reactive
 * `items` source, and returns mutation helpers that trigger reactivity by
 * replacing the Set (Vue tracks identity, not internal mutations, for Sets).
 */

import { ref, computed, readonly, toValue } from 'vue'
import type { Ref, ComputedRef, MaybeRefOrGetter } from 'vue'

export interface UseBatchSelectionReturn<T, Key extends string | number = string | number> {
  /** Set of currently-selected keys. Read-only; mutate via the helpers below. */
  selected: Readonly<Ref<Set<Key>>>
  /** List of selected items (derived from `items` × `selected`). */
  selectedItems: Readonly<Ref<T[]>>
  /** Number of selected items. */
  selectedCount: Readonly<Ref<number>>
  /** True iff every item currently in the list is selected (and list non-empty). */
  allSelected: Readonly<Ref<boolean>>
  /** True iff at least one (but not all) items are selected — drives indeterminate checkbox state. */
  someSelected: Readonly<Ref<boolean>>
  /** Toggle selection for one item. */
  toggle: (item: T) => void
  /** Select one item (idempotent). */
  select: (item: T) => void
  /** Select one item by key (idempotent). Use when only the ID is available. */
  selectByKey: (key: Key) => void
  /** Deselect one item (idempotent). */
  deselect: (item: T) => void
  /** Deselect by key (when only the ID is available). */
  deselectByKey: (key: Key) => void
  /** Toggle selection by key. Use when only the ID is available. */
  toggleByKey: (key: Key) => void
  /** Select every item currently in the list. */
  selectAll: () => void
  /** Replace the entire selection with the given keys. */
  setSelected: (keys: Iterable<Key>) => void
  /** Clear all selections. */
  clear: () => void
  /** True if the given item is selected. */
  isSelected: (item: T) => boolean
}

/**
 * Reusable multi-select state for list components.
 *
 * @param items  Reactive source of selectable items (ref, computed, or getter).
 *               Non-reactive plain arrays are accepted too but will not update
 *               `selectedItems` / `allSelected` / `someSelected` automatically.
 * @param keyFn  Extract the unique key from an item. Defaults to treating the
 *               item itself as the key (correct when `T extends string | number`).
 */
export function useBatchSelection<T, Key extends string | number = string | number>(
  items: MaybeRefOrGetter<readonly T[]>,
  keyFn: (item: T) => Key = (item) => item as unknown as Key
): UseBatchSelectionReturn<T, Key> {
  const selected = ref(new Set<Key>()) as Ref<Set<Key>>

  const currentItems: ComputedRef<readonly T[]> = computed(() => toValue(items) ?? [])

  const selectedItems = computed(() =>
    currentItems.value.filter((item) => selected.value.has(keyFn(item)))
  ) as Readonly<Ref<T[]>>

  const selectedCount = computed(() => selected.value.size)

  const allSelected = computed(() => {
    const total = currentItems.value.length
    return total > 0 && selected.value.size === total
  })

  const someSelected = computed(() => {
    const count = selected.value.size
    return count > 0 && count < currentItems.value.length
  })

  function isSelected(item: T): boolean {
    return selected.value.has(keyFn(item))
  }

  // Item-based methods delegate to their *ByKey primitives so mutation
  // logic lives in exactly one place (#5331).
  function toggle(item: T): void {
    toggleByKey(keyFn(item))
  }

  function select(item: T): void {
    selectByKey(keyFn(item))
  }

  function deselect(item: T): void {
    deselectByKey(keyFn(item))
  }

  /**
   * Deselect by key directly. Useful when consumers only have the ID
   * (e.g. after an action processed an item by ID and the item object
   * is no longer in the items list). Idempotent.
   */
  function deselectByKey(key: Key): void {
    if (selected.value.has(key)) {
      const next = new Set(selected.value)
      next.delete(key)
      selected.value = next
    }
  }

  /**
   * Select by key directly. Mirror of `deselectByKey` for the common case
   * where consumers have an ID in hand (from a checkbox change event,
   * a URL param, a cross-page selection, etc.) and shouldn't have to
   * reach into the items list just to get an item reference. Idempotent.
   */
  function selectByKey(key: Key): void {
    if (!selected.value.has(key)) {
      const next = new Set(selected.value)
      next.add(key)
      selected.value = next
    }
  }

  /**
   * Toggle by key directly. Mirror of `toggle` for ID-only call sites —
   * replaces the `items.find(i => keyFn(i) === id)` + `toggle(item)` shim
   * with one O(1) call.
   */
  function toggleByKey(key: Key): void {
    const next = new Set(selected.value)
    if (next.has(key)) {
      next.delete(key)
    } else {
      next.add(key)
    }
    selected.value = next
  }

  function selectAll(): void {
    selected.value = new Set(currentItems.value.map(keyFn))
  }

  /**
   * Replace the entire selection with the given keys. Useful for
   * "select all matching the current filter" patterns where the items
   * to select aren't in the composable's `items` source (e.g. cross-page
   * selection in a paginated list whose `items` is just the current page).
   */
  function setSelected(keys: Iterable<Key>): void {
    selected.value = new Set(keys)
  }

  function clear(): void {
    selected.value = new Set()
  }

  return {
    // `readonly()` wraps the Set in DeepReadonly; we expose the original
    // surface (`Set<Key>`) as read-only because callers need `.has()` / `.size`
    // and we already control all mutations via the helpers. The double cast is
    // the standard Vue idiom for this TS2352 (non-overlapping types).
    selected: readonly(selected) as unknown as Readonly<Ref<Set<Key>>>,
    selectedItems,
    selectedCount,
    allSelected,
    someSelected,
    toggle,
    select,
    selectByKey,
    deselect,
    deselectByKey,
    toggleByKey,
    selectAll,
    setSelected,
    clear,
    isSelected
  }
}
