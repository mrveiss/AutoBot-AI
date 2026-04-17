import { ref, onMounted, onUnmounted, nextTick, type Ref } from 'vue'

const MORE_BUTTON_WIDTH = 90
const GAP = 16

export function useNavOverflow(
  containerRef: Ref<HTMLElement | null>,
  itemCount: Ref<number>
) {
  const visibleCount = ref(itemCount.value)
  let naturalWidths: number[] = []
  let ro: ResizeObserver | null = null

  function measureNaturalWidths() {
    const container = containerRef.value
    if (!container) return
    naturalWidths = Array.from(
      container.querySelectorAll<HTMLElement>('[data-nav-item]')
    ).map(el => el.getBoundingClientRect().width)
  }

  function recalculate() {
    const container = containerRef.value
    if (!container) return
    if (naturalWidths.length === 0) measureNaturalWidths()
    if (naturalWidths.length === 0) return

    const totalNatural = naturalWidths.reduce((s, w) => s + w + GAP, 0)
    const available = container.clientWidth

    if (totalNatural <= available) {
      visibleCount.value = naturalWidths.length
      return
    }

    const budget = available - MORE_BUTTON_WIDTH
    let consumed = 0
    let count = 0
    for (const w of naturalWidths) {
      consumed += w + GAP
      if (consumed > budget) break
      count++
    }
    visibleCount.value = Math.max(1, count)
  }

  onMounted(async () => {
    await nextTick()
    measureNaturalWidths()
    recalculate()
    ro = new ResizeObserver(recalculate)
    if (containerRef.value) ro.observe(containerRef.value)
  })

  onUnmounted(() => ro?.disconnect())

  return { visibleCount }
}
