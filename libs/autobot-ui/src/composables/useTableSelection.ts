// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Row keys and the selection of BaseTable (#17562), kept out of the component so it stays small.

import { computed, ref, watch, type Ref } from 'vue'
import { toggleAllSelection } from '../utils/tableView'

type Row = Record<string, unknown>
export type SelectionKey = string | number

/**
 * `rowKeyOf` keys a row by its `rowKey` field, else by object identity (never position: `rows`
 * and the sorted order differ, so a positional key would select another row after a sort).
 * Identity keys are negative so they cannot collide with ids. Select-all covers `scope()`
 * (the filtered set, every page); rows the app removes stop being selected.
 */
export function useTableSelection(
  rows: () => Row[],
  scope: () => Row[],
  rowKey: () => string,
  onChange: (keys: SelectionKey[]) => void,
) {
  const selected: Ref<Set<SelectionKey>> = ref(new Set())
  const identityKeys = new WeakMap<Row, number>()
  let nextIdentityKey = -1

  function rowKeyOf(row: Row): SelectionKey {
    const own = row[rowKey()] as SelectionKey | undefined
    if (own !== undefined && own !== null) return own
    let key = identityKeys.get(row)
    if (key === undefined) {
      key = nextIdentityKey--
      identityKeys.set(row, key)
    }
    return key
  }

  const keysOf = (list: Row[]): SelectionKey[] => list.map((r) => rowKeyOf(r))
  const allSelected = computed(() => {
    const keys = keysOf(scope())
    return keys.length > 0 && keys.every((k) => selected.value.has(k))
  })

  function commit(next: Set<SelectionKey>): void {
    selected.value = next
    onChange(Array.from(next))
  }

  function toggleRow(key: SelectionKey): void {
    const next = new Set(selected.value)
    if (!next.delete(key)) next.add(key)
    commit(next)
  }

  const toggleAll = (): void => commit(toggleAllSelection(selected.value, keysOf(scope())))

  // The source is the key list, not the array reference, so an in-place splice prunes too.
  watch(
    () => keysOf(rows()),
    (keys) => {
      const present = new Set(keys)
      const kept = new Set([...selected.value].filter((k) => present.has(k)))
      if (kept.size !== selected.value.size) commit(kept)
    },
  )

  return { selected, allSelected, rowKeyOf, toggleRow, toggleAll }
}
