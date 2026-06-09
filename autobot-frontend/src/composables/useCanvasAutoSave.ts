// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { ref, watch, computed } from 'vue'
import { useCanvasStore } from '@/stores/useCanvasStore'
import { useDebounce } from '@/composables/useDebounce'
import { CANVAS_AUTOSAVE_DEBOUNCE_MS } from '@/constants/canvas'
import { createLogger } from '@/utils/debugUtils'
import type { AutoSaveStatus, CanvasCell } from '@/types/canvas'

const logger = createLogger('useCanvasAutoSave')

export function useCanvasAutoSave(
  saveFn: (canvasId: string, cells: CanvasCell[]) => Promise<void>
) {
  const store = useCanvasStore()
  const status = ref<AutoSaveStatus>('idle')
  const lastSavedAt = ref<string | undefined>()

  const isDirtyRef = computed(() => store.isDirty)
  const debouncedDirty = useDebounce(isDirtyRef, CANVAS_AUTOSAVE_DEBOUNCE_MS)

  watch(debouncedDirty, async (dirty) => {
    if (!dirty || !store.canvasId) return
    status.value = 'saving'
    try {
      await saveFn(store.canvasId, store.cells)
      localStorage.setItem(`canvas:${store.canvasId}`, JSON.stringify({
        cells: store.cells,
        savedAt: new Date().toISOString(),
      }))
      store.markSaved()
      status.value = 'saved'
      lastSavedAt.value = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    } catch (err) {
      logger.error('Auto-save failed', err)
      status.value = 'error'
    }
  })

  function loadFromLocalStorage(canvasId: string) {
    const raw = localStorage.getItem(`canvas:${canvasId}`)
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return null }
  }

  return { status, lastSavedAt, loadFromLocalStorage }
}
