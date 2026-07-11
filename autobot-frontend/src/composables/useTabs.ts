// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * useTabs Composable (#11571)
 *
 * WAI-ARIA tab-bar pattern — roving tabindex, Arrow / Home / End keyboard
 * navigation with focus-follow via nextTick, and attribute builders that
 * produce correct id / aria-selected / aria-controls / tabindex / role
 * values for both the tab button and the panel container.
 *
 * Consumer pattern:
 *
 *   const { activeTab, tabAttrs, panelAttrs, handleKeydown, tablistRef } =
 *     useTabs(['a', 'b', 'c'] as const, { initial: 'b' })
 *
 *   <div ref="tablistRef" role="tablist">
 *     <button v-for="id in tabIds" v-bind="tabAttrs(id)" @click="selectTab(id)">
 *       {{ id }}
 *     </button>
 *   </div>
 *   <div v-bind="panelAttrs('a')">…</div>
 */

import { ref, nextTick } from 'vue'
import type { Ref } from 'vue'

export interface UseTabsReturn<T extends string> {
  /** Currently-active tab id. */
  activeTab: Ref<T>
  /** All tab ids in order — exposed so callers can iterate them. */
  tabIds: readonly T[]
  /** True when the given id is the active tab. */
  isActive: (id: T) => boolean
  /** Programmatically activate a tab. */
  selectTab: (id: T) => void
  /**
   * Keyboard handler — attach to the tablist container element or to each
   * individual tab button via `@keydown`.
   * Handles: ArrowLeft / ArrowRight (wrap-around), Home, End.
   * Focus follows selection after nextTick by querying [role="tab"] elements
   * within `tablistRef`.
   */
  handleKeydown: (event: KeyboardEvent) => void
  /**
   * Attribute builder for a tab button.
   * Returns: id, role, aria-selected, aria-controls, tabindex.
   */
  tabAttrs: (id: T) => {
    id: string
    role: 'tab'
    'aria-selected': boolean
    'aria-controls': string
    tabindex: 0 | -1
  }
  /**
   * Attribute builder for a panel container.
   * Returns: id, role, aria-labelledby.
   */
  panelAttrs: (id: T) => {
    id: string
    role: 'tabpanel'
    'aria-labelledby': string
  }
  /** Ref to attach to the element that wraps all tab buttons (role="tablist"). */
  tablistRef: Ref<HTMLElement | null>
}

export interface UseTabsOptions<T extends string> {
  /** The tab that should be active on first render. Defaults to `tabIds[0]`. */
  initial?: T
}

/**
 * WAI-ARIA tab-bar composable.
 *
 * @param tabIds — ordered tuple of string-literal tab identifiers
 * @param opts   — optional initial tab; defaults to first entry
 */
export function useTabs<T extends string>(
  tabIds: readonly T[],
  opts?: UseTabsOptions<T>,
): UseTabsReturn<T> {
  if (tabIds.length === 0) throw new Error('useTabs: tabIds must not be empty')

  const initial: T =
    opts?.initial !== undefined && (tabIds as string[]).includes(opts.initial)
      ? opts.initial
      : tabIds[0]

  const activeTab = ref<T>(initial) as Ref<T>
  const tablistRef = ref<HTMLElement | null>(null)

  const isActive = (id: T): boolean => activeTab.value === id

  const selectTab = (id: T): void => {
    activeTab.value = id
  }

  const handleKeydown = async (event: KeyboardEvent): Promise<void> => {
    const { key } = event
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(key)) return
    event.preventDefault()

    const currentIndex = (tabIds as string[]).indexOf(activeTab.value)
    let newIndex: number

    if (key === 'ArrowLeft') {
      newIndex = (currentIndex - 1 + tabIds.length) % tabIds.length
    } else if (key === 'ArrowRight') {
      newIndex = (currentIndex + 1) % tabIds.length
    } else if (key === 'Home') {
      newIndex = 0
    } else {
      // End
      newIndex = tabIds.length - 1
    }

    activeTab.value = tabIds[newIndex]

    await nextTick()
    const tabBtns = tablistRef.value?.querySelectorAll<HTMLElement>('[role="tab"]')
    tabBtns?.[newIndex]?.focus()
  }

  const tabAttrs = (id: T) => ({
    id: `tab-${id}`,
    role: 'tab' as const,
    'aria-selected': isActive(id),
    'aria-controls': `tabpanel-${id}`,
    tabindex: (isActive(id) ? 0 : -1) as 0 | -1,
  })

  const panelAttrs = (id: T) => ({
    id: `tabpanel-${id}`,
    role: 'tabpanel' as const,
    'aria-labelledby': `tab-${id}`,
  })

  return {
    activeTab,
    tabIds,
    isActive,
    selectTab,
    handleKeydown,
    tabAttrs,
    panelAttrs,
    tablistRef,
  }
}
