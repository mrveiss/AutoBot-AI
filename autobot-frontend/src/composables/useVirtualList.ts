// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Virtual List Composable
 *
 * Issue #4037: Reusable virtual scrolling for large lists
 * GH#9061 consolidation: delegates to useVirtualScroll to eliminate
 * duplicate viewport-calculation logic.
 *
 * Provides efficient rendering of large lists by virtualizing items.
 * Only renders visible items and spacers for off-screen items.
 *
 * Usage:
 * ```vue
 * <script setup>
 * import { useVirtualList } from '@/composables/useVirtualList'
 *
 * const items = ref([...])
 * const { containerRef, visibleItems, totalHeight } = useVirtualList(items, 56) // 56px item height
 * </script>
 *
 * <template>
 *   <div ref="containerRef" style="height: 400px; overflow: auto;">
 *     <div :style="{ height: totalHeight + 'px', position: 'relative' }">
 *       <div
 *         v-for="(item, index) in visibleItems"
 *         :key="item.id"
 *         :style="{ transform: `translateY(${item.offset}px)` }"
 *       >
 *         {{ item.data.name }}
 *       </div>
 *     </div>
 *   </div>
 * </template>
 * ```
 */

import { computed, watch, onScopeDispose, getCurrentScope, toValue, type ComputedRef, type MaybeRefOrGetter } from 'vue'
import { useVirtualScroll } from '@/composables/useVirtualScroll'

export interface VirtualItem<T> {
  data: T
  index: number
  /** Absolute top offset in pixels — use as `translateY(${item.offset}px)` */
  offset: number
}

/**
 * Virtual list composable — thin wrapper over useVirtualScroll for the
 * fixed-height absolute-positioned rendering pattern.
 *
 * Callers bind `ref="containerRef"` on the scroll container; this composable
 * attaches the scroll listener imperatively (rather than via containerProps),
 * keeping existing templates unchanged.
 *
 * @param items - Array of items to virtualize
 * @param itemHeight - Height of each item in pixels (fixed)
 * @param overscan - Number of items to render outside visible area (default: 3)
 */
export function useVirtualList<T extends { id: string | number }>(
  items: MaybeRefOrGetter<T[]>,
  itemHeight: number,
  overscan: number = 3
) {
  const itemsRef = computed(() => toValue(items))

  const scroll = useVirtualScroll<T>({
    items: itemsRef,
    itemHeight,
    buffer: overscan,
  })

  // Adapt visibleItems from { item, index, key } → { data, index, offset }
  // offset = index * itemHeight is exact for uniform fixed-height items.
  const visibleItems: ComputedRef<VirtualItem<T>[]> = computed(() =>
    scroll.visibleItems.value.map(({ item, index }) => ({
      data: item,
      index,
      offset: index * itemHeight,
    }))
  )

  // Alias totalSize → totalHeight (public API name used by callers)
  const totalHeight = scroll.totalSize

  // Imperatively attach the scroll listener so callers can use ref="containerRef"
  // without needing to v-bind="containerProps".
  const handleScroll = (event: Event) => {
    scroll.scrollTop.value = (event.target as HTMLElement).scrollTop
  }

  watch(scroll.containerRef, (newEl: HTMLElement | null, oldEl: HTMLElement | null) => {
    oldEl?.removeEventListener('scroll', handleScroll)
    newEl?.addEventListener('scroll', handleScroll, { passive: true })
  })

  if (getCurrentScope()) {
    onScopeDispose(() => {
      scroll.containerRef.value?.removeEventListener('scroll', handleScroll)
    })
  }

  return {
    containerRef: scroll.containerRef,
    visibleItems,
    totalHeight,
    scrollTop: scroll.scrollTop,
  }
}
