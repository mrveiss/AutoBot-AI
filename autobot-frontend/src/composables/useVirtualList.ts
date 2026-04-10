/**
 * Virtual List Composable
 *
 * Issue #4037: Reusable virtual scrolling for large lists
 *
 * Provides efficient rendering of large lists by virtualizing items.
 * Only renders visible items and spacers for off-screen items.
 *
 * Usage:
 * ```vue
 * <script setup>
 * import { usV irtualList } from '@/composables/useVirtualList'
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

import { ref, computed, onMounted, onUnmounted, watch } from 'vue'

interface VirtualItem<T> {
  data: T
  index: number
  offset: number
}

/**
 * Virtual list composable
 * @param items - Array of items to virtualize
 * @param itemHeight - Height of each item in pixels
 * @param overscan - Number of items to render outside visible area (default: 3)
 * @returns Virtual list utilities
 */
export function useVirtualList<T extends { id: string | number }>(
  items: any, // Ref<T[]> or ComputedRef<T[]>
  itemHeight: number,
  overscan: number = 3
) {
  const containerRef = ref<HTMLElement | null>(null)
  const scrollTop = ref(0)

  // Compute visible items based on scroll position
  const visibleItems = computed<VirtualItem<T>[]>(() => {
    if (!containerRef.value) return []

    const container = containerRef.value
    const visibleHeight = container.clientHeight
    const itemsArray = (items.value || items) as T[]

    if (itemsArray.length === 0) return []

    // Calculate which items are visible
    const startIndex = Math.max(0, Math.floor(scrollTop.value / itemHeight) - overscan)
    const endIndex = Math.min(
      itemsArray.length,
      Math.ceil((scrollTop.value + visibleHeight) / itemHeight) + overscan
    )

    return itemsArray.slice(startIndex, endIndex).map((item, relativeIndex) => ({
      data: item,
      index: startIndex + relativeIndex,
      offset: (startIndex + relativeIndex) * itemHeight
    }))
  })

  // Total height of all items
  const totalHeight = computed(() => {
    const itemsArray = (items.value || items) as T[]
    return itemsArray.length * itemHeight
  })

  // Handle scroll events
  const handleScroll = (event: Event) => {
    const target = event.target as HTMLElement
    scrollTop.value = target.scrollTop
  }

  // Lifecycle
  onMounted(() => {
    if (containerRef.value) {
      containerRef.value.addEventListener('scroll', handleScroll, { passive: true })
    }
  })

  onUnmounted(() => {
    if (containerRef.value) {
      containerRef.value.removeEventListener('scroll', handleScroll)
    }
  })

  // Re-attach listener if container ref changes
  watch(
    () => containerRef.value,
    (newContainer, oldContainer) => {
      if (oldContainer) {
        oldContainer.removeEventListener('scroll', handleScroll)
      }
      if (newContainer) {
        newContainer.addEventListener('scroll', handleScroll, { passive: true })
      }
    }
  )

  return {
    containerRef,
    visibleItems,
    totalHeight,
    scrollTop
  }
}
