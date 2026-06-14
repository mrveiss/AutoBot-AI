// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { ref, type Ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useInlineEdit')

/**
 * Generic inline edit-on-blur composable (#9205).
 *
 * Manages the edit state for a list of items where a single item at a time
 * can be edited inline (e.g. double-click to edit, save on blur/enter).
 * `saveEdit` is a no-op when the value is unchanged, awaits the provided
 * `save` callback (where the caller performs the API call and any optimistic
 * store update), logs failures, and always resets the editing state.
 *
 * @param getValue - extracts the current (pre-edit) string value from an item
 * @param save - persists the new value; rejections are caught and logged
 */
export function useInlineEdit<T extends { id: number }>(
  getValue: (item: T) => string,
  save: (item: T, value: string) => Promise<void>
) {
  const editingId: Ref<number | null> = ref(null)
  const editText = ref('')

  function startEdit(item: T) {
    editingId.value = item.id
    editText.value = getValue(item)
  }

  async function saveEdit(item: T) {
    if (editText.value === getValue(item)) {
      editingId.value = null
      return
    }
    try {
      await save(item, editText.value)
    } catch (err) {
      logger.error('Failed to save inline edit', err)
    }
    editingId.value = null
  }

  return {
    editingId,
    editText,
    startEdit,
    saveEdit,
  }
}
