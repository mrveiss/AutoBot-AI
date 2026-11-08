// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Keyboard grab mode for dashboard widgets (owner ruling on #18242).
 * Space/Enter grabs and drops, Arrows move, Shift+Left/Right changes the span,
 * Shift+Up/Down changes the height, and Esc restores the pre-grab state.
 * Every change is announced through `announcement`.
 */
import { ref, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  GRID_COLUMNS,
  HEIGHT_STEP,
  clampHeight,
  moveWidget,
  stepSpan,
  type DashboardWidget,
} from './dashboardLayoutModel'

export function useDashboardGrabMode<T extends DashboardWidget>(
  widgets: Ref<T[]>,
  labelOf: (w: T) => string = (w) => w.title || w.type,
) {
  const { t } = useI18n()
  const grabbedId = ref<string | null>(null)
  const announcement = ref('')
  let snapshot: T[] | null = null

  const indexOf = (id: string) => widgets.value.findIndex((w) => w.id === id)

  function announcePosition(id: string, key: string) {
    const i = indexOf(id)
    const w = widgets.value[i]
    announcement.value = t(key, { name: labelOf(w), position: i + 1, total: widgets.value.length, span: w.span, height: w.height })
  }

  function toggleGrab(id: string) {
    if (grabbedId.value === id) {
      grabbedId.value = null
      snapshot = null
      announcePosition(id, 'dashboardGrid.announce.dropped')
      return
    }
    snapshot = widgets.value.map((w) => ({ ...w }))
    grabbedId.value = id
    announcePosition(id, 'dashboardGrid.announce.grabbed')
  }

  function cancel() {
    const id = grabbedId.value
    if (!id || !snapshot) return
    widgets.value = snapshot
    snapshot = null
    grabbedId.value = null
    announcePosition(id, 'dashboardGrid.announce.cancelled')
  }

  function resize(id: string, key: string) {
    const i = indexOf(id)
    const cur = widgets.value[i]
    const change =
      key === 'ArrowLeft' || key === 'ArrowRight'
        ? { span: stepSpan(cur.span, key === 'ArrowRight' ? 1 : -1) }
        : { height: clampHeight(cur.height + (key === 'ArrowDown' ? HEIGHT_STEP : -HEIGHT_STEP)) }
    // The caller's widget type keeps its extra fields; only span or height changes.
    widgets.value = widgets.value.map((x, j) => (j === i ? ({ ...x, ...change } as T) : x))
    announcePosition(id, 'dashboardGrid.announce.resized')
  }

  // Up/Down jump by the number of same-span widgets that fit in one row: whole widgets only,
  // so span 8 (1.5 per row) steps by 1, not 2.
  function move(id: string, key: string) {
    const rowStep = Math.max(1, Math.floor(GRID_COLUMNS / (widgets.value[indexOf(id)].span || GRID_COLUMNS)))
    const delta = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -rowStep, ArrowDown: rowStep }[key] ?? 0
    widgets.value = moveWidget(widgets.value, indexOf(id), delta)
    announcePosition(id, 'dashboardGrid.announce.moved')
  }

  /** Returns true when the key was handled (caller then prevents default). */
  function onKeydown(id: string, e: KeyboardEvent): boolean {
    if (e.key === ' ' || e.key === 'Enter') return toggleGrab(id), true
    if (grabbedId.value !== id) return false
    if (e.key === 'Escape') return cancel(), true
    if (!e.key.startsWith('Arrow')) return false
    if (e.shiftKey) resize(id, e.key)
    else move(id, e.key)
    return true
  }

  return { grabbedId, announcement, onKeydown, cancel }
}
