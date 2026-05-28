<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss | Author: mrveiss -->
<template>
  <div class="chart-cell space-y-2">
    <!-- Error state: render fallback -->
    <div v-if="renderError" class="p-4 rounded border border-error bg-error-bg">
      <p class="text-error font-medium text-sm">❌ Chart render failed</p>
      <p class="text-text-secondary text-xs mt-1">{{ renderError }}</p>
      <details class="mt-2 text-xs cursor-pointer">
        <summary class="font-medium hover:underline">Show details</summary>
        <pre class="mt-1 p-2 bg-bg-card rounded overflow-auto text-[10px]">{{ renderError }}</pre>
      </details>
    </div>

    <!-- Success: render chart + data table -->
    <div v-else-if="chartSpec">
      <!-- Chart container (Vega embed renders here) -->
      <div
        ref="chartContainer"
        class="rounded border border-border-default overflow-hidden"
        :style="{ minHeight: '300px' }"
        role="img"
        :aria-label="`Chart: ${chartSpec.title || 'untitled'}`"
      />

      <!-- Data table (accessible fallback for screen readers) -->
      <details class="text-xs mt-2 border border-border-secondary rounded p-2">
        <summary class="font-medium cursor-pointer hover:underline">
          📊 View data table
        </summary>
        <div class="mt-2 overflow-x-auto">
          <table class="border-collapse text-xs w-full">
            <thead>
              <tr class="border-b border-border-secondary">
                <th
                  v-for="(col, i) in dataTableColumns"
                  :key="i"
                  class="text-left px-2 py-1 bg-bg-secondary font-medium"
                >
                  {{ col }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in dataTableRows" :key="i" class="border-b border-border-secondary">
                <td v-for="(val, j) in row" :key="j" class="px-2 py-1">
                  {{ val }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>
    </div>

    <!-- Loading: skeleton -->
    <div
      v-else
      :class="[
        'p-4 rounded border border-border-default space-y-2',
        !prefersReducedMotion && 'animate-pulse',
      ]"
      aria-busy="true"
      aria-label="Loading chart…"
    >
      <div class="h-64 bg-bg-tertiary rounded" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import type { ChartPayload } from '@/types/canvas'

const props = defineProps<{
  richPayload: ChartPayload | null
}>()

const chartContainer = ref<HTMLDivElement>()
const renderError = ref<string>('')
const vegaEmbedLoaded = ref(false)
const prefersReducedMotion = typeof window !== 'undefined'
  ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
  : false

const chartSpec = computed(() => props.richPayload?.spec)

// Parse data from spec for a11y table
const dataTableColumns = computed(() => {
  const data = chartSpec.value?.data?.[0]
  if (Array.isArray(data)) {
    return Object.keys(data[0] || {})
  }
  return []
})

const dataTableRows = computed(() => {
  const data = chartSpec.value?.data?.[0]
  if (Array.isArray(data)) {
    return data.slice(0, 10).map(row =>
      dataTableColumns.value.map(col => String((row as Record<string, unknown>)[col] || ''))
    )
  }
  return []
})

// Lazy-load vega-embed on first render
async function loadVegaEmbed() {
  if (vegaEmbedLoaded.value) return

  try {
    const vegaEmbed = await import('vega-embed')
    const embed = vegaEmbed.default
    vegaEmbedLoaded.value = true
    return embed
  } catch (err) {
    renderError.value = `Failed to load vega-embed: ${err instanceof Error ? err.message : String(err)}`
    throw err
  }
}

// Render chart when payload updates
async function renderChart() {
  renderError.value = ''

  if (!chartSpec.value || !chartContainer.value) {
    return
  }

  try {
    const embed = await loadVegaEmbed()
    if (!embed) return

    // Apply prefers-reduced-motion: disable animations
    const spec = { ...chartSpec.value } as any
    if (prefersReducedMotion && spec.config) {
      spec.config = {
        ...spec.config,
        animation: { duration: 0, delay: 0 },
      }
    } else if (prefersReducedMotion) {
      spec.config = { animation: { duration: 0, delay: 0 } }
    }

    // Apply theme: detect dark mode from CSS var or media query
    const isDark = typeof window !== 'undefined'
      ? window.matchMedia('(prefers-color-scheme: dark)').matches
      : false
    const themeColors = isDark
      ? { background: 'var(--color-bg-primary)', foreground: 'var(--color-text-primary)' }
      : { background: 'var(--color-bg-primary)', foreground: 'var(--color-text-primary)' }
    spec.config = {
      ...spec.config,
      ...themeColors,
    }

    // Render
    await embed(chartContainer.value, spec, {
      actions: true,
      responsive: true,
      tooltip: { theme: isDark ? 'dark' : 'light' },
    })
  } catch (err) {
    renderError.value = `Chart render failed: ${err instanceof Error ? err.message : String(err)}`
    console.error('[ChartCell] render error:', err)
  }
}

// Watch payload changes and render
watch(() => props.richPayload, renderChart, { immediate: true, deep: true })

// Initial render on mount
onMounted(() => {
  if (props.richPayload) {
    renderChart()
  }
})
</script>

<style scoped>
.chart-cell {
  /* Ensure chart container is properly sized for vega-embed */
}

/* Accessibility: focus styles for keyboard navigation */
:deep([role="img"]) {
  outline: none;
}

:deep([role="img"]:focus-visible) {
  outline: 2px solid var(--color-focus-ring);
  outline-offset: 2px;
}

/* Ensure table is readable in both light/dark modes */
:deep(table) {
  background-color: var(--color-bg-secondary);
}

:deep(th) {
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

:deep(td) {
  color: var(--color-text-primary);
}
</style>
