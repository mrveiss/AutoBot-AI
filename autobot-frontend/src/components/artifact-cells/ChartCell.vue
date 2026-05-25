<!--
  AutoBot - AI-Powered Automation Platform
  Copyright (c) 2025 mrveiss
  Author: mrveiss

  ChartCell.vue - Vega-Lite v5 chart rendering component
  Renders rich chart visualizations with lazy-loading, error boundaries, and a11y support
  Issue MVA-485
-->
<template>
  <div class="chart-cell">
    <!-- Placeholder for empty content -->
    <div v-if="!richPayload" class="chart-placeholder">
      <div class="placeholder-content">
        <Icon name="chart-bar" />
        <span>{{ $t('charts.cellPlaceholder', 'Chart') }}</span>
      </div>
    </div>

    <!-- Error state -->
    <div v-else-if="hasError" class="chart-error-boundary">
      <div class="error-content">
        <Icon name="exclamation-circle" />
        <div class="error-message">
          <h4>{{ $t('charts.renderError', 'Chart rendering failed') }}</h4>
          <p v-if="errorMessage" class="error-details">{{ errorMessage }}</p>
        </div>
        <button class="retry-button" @click="retryRender">
          {{ $t('common.retry', 'Retry') }}
        </button>
      </div>

      <!-- Accessible data table fallback for screen readers -->
      <details class="chart-data-fallback">
        <summary>{{ $t('charts.viewData', 'View raw data') }}</summary>
        <div class="data-table-wrapper" role="region" aria-label="Chart data table">
          <table class="data-table">
            <tbody>
              <tr v-for="(value, key) in getChartData()" :key="key">
                <th scope="row">{{ key }}</th>
                <td>{{ formatValue(value) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>
    </div>

    <!-- Success state -->
    <div v-else class="chart-container" :id="`chart-${chartId}`" role="img" :aria-label="chartAriaLabel" aria-live="polite" />

    <!-- Accessible data table for screen readers (always present but hidden for sighted users) -->
    <details v-if="richPayload && !hasError" class="chart-data-fallback">
      <summary>{{ $t('charts.viewData', 'View raw data') }}</summary>
      <div class="data-table-wrapper" role="region" aria-label="Chart data table">
        <table class="data-table">
          <tbody>
            <tr v-for="(value, key) in getChartData()" :key="key">
              <th scope="row">{{ key }}</th>
              <td>{{ formatValue(value) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

// Props
interface ChartCellProps {
  richPayload?: Record<string, unknown> | null
  title?: string
  height?: string | number
  width?: string | number
  renderer?: 'canvas' | 'svg' // vega-embed RendererType
  actions?: Record<string, unknown>
}

const props = withDefaults(defineProps<ChartCellProps>(), {
  richPayload: null,
  title: undefined,
  height: 'auto',
  width: '100%',
  renderer: 'canvas',
  actions: () => ({
    export: true,
    source: true,
    editor: false
  })
})

// Emits
interface ChartCellEmits {
  error: [error: Error]
  rendered: [spec: Record<string, unknown>]
}

defineEmits<ChartCellEmits>()

// State
const chartId = ref<string>(`chart-${crypto.randomUUID()}`)
const hasError = ref<boolean>(false)
const errorMessage = ref<string>('')
let vegaEmbed: any = null

// Computed
const chartAriaLabel = computed(() => {
  return props.title ? t('charts.ariaLabel', { title: props.title }) : t('charts.defaultAriaLabel', 'Data visualization chart')
})

const prefersReducedMotion = computed(() => {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
})

// Methods
const loadVegaEmbed = async () => {
  if (!vegaEmbed) {
    vegaEmbed = await import('vega-embed')
  }
  return vegaEmbed
}

const getChartData = (): Record<string, unknown> => {
  if (!props.richPayload || typeof props.richPayload !== 'object') {
    return {}
  }

  const payload = props.richPayload as Record<string, unknown>
  if (Array.isArray(payload.data)) {
    return {
      'Data Points': payload.data.length,
      'Type': payload.mark || 'unknown'
    }
  }

  return {}
}

const formatValue = (value: unknown): string => {
  if (value === null || value === undefined) {
    return '-'
  }
  if (typeof value === 'object') {
    return JSON.stringify(value)
  }
  return String(value)
}

const renderChart = async () => {
  if (!props.richPayload) {
    return
  }

  try {
    hasError.value = false
    errorMessage.value = ''

    const vega = await loadVegaEmbed()
    if (!vega) {
      throw new Error('Failed to load vega-embed')
    }

    const containerEl = document.getElementById(chartId.value)
    if (!containerEl) {
      throw new Error(`Container element not found: ${chartId.value}`)
    }

    const spec = props.richPayload as Record<string, unknown>

    // Apply reduced-motion preference by disabling animations
    if (prefersReducedMotion.value) {
      spec.config = {
        ...((spec.config as Record<string, unknown>) || {}),
        mark: { ...((spec.config as Record<string, unknown>)?.mark || {}), animationDuration: 0 },
        axis: { ...((spec.config as Record<string, unknown>)?.axis || {}), minExtent: 30 }
      }
    }

    await vega.embed(containerEl, spec, {
      renderer: props.renderer,
      actions: props.actions
    })
  } catch (error) {
    hasError.value = true
    errorMessage.value = error instanceof Error ? error.message : 'Unknown error occurred'
  }
}

const retryRender = () => {
  renderChart()
}

// Lifecycle
onMounted(() => {
  renderChart()
})
</script>

<style scoped>
/**
 * Chart cell styling with design tokens
 * Supports light/dark themes and WCAG AA accessibility
 */
.chart-cell {
  position: relative;
  width: 100%;
  height: auto;
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  padding: var(--spacing-md);
  border: 1px solid var(--border-subtle);
  overflow: hidden;
}

.chart-placeholder,
.chart-error-boundary {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 300px;
  gap: var(--spacing-md);
  color: var(--text-secondary);
  text-align: center;
}

.placeholder-content,
.error-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-sm);
}

.placeholder-content i,
.error-content i {
  font-size: 48px;
  color: var(--text-tertiary);
}

.error-content i {
  color: var(--color-error);
}

.error-message {
  max-width: 400px;
}

.error-message h4 {
  margin: 0;
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.error-details {
  margin: var(--spacing-sm) 0 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  font-family: var(--font-mono);
  word-break: break-word;
}

.retry-button {
  margin-top: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-button-primary);
  color: var(--text-on-primary);
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.retry-button:hover {
  background: var(--bg-button-primary-hover);
}

.retry-button:active {
  background: var(--bg-button-primary-active);
}

.chart-container {
  width: 100%;
  height: auto;
  min-height: 300px;
}

.chart-data-fallback {
  margin-top: var(--spacing-md);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--border-subtle);
}

.chart-data-fallback summary {
  cursor: pointer;
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-secondary);
  user-select: none;
  padding: var(--spacing-sm);
  margin: calc(-1 * var(--spacing-sm));
  border-radius: var(--radius-sm);
  transition: background-color 0.2s ease;
}

.chart-data-fallback summary:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.data-table-wrapper {
  margin-top: var(--spacing-md);
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}

.data-table th,
.data-table td {
  padding: var(--spacing-sm);
  text-align: left;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-primary);
}

.data-table th {
  font-weight: var(--font-semibold);
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.data-table tbody tr:hover {
  background: var(--bg-tertiary);
}

/* Vega-embed specific styles */
:deep(.vega-embed) {
  width: 100%;
  height: auto;
}

:deep(.vega-embed-wrapper) {
  width: 100%;
  height: auto;
}

/* Tooltip styling for light/dark theme */
:deep(.vega-tooltip) {
  background: var(--bg-elevated);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  color: var(--text-primary);
  font-size: var(--text-sm);
}

/* Ensure focus visibility for keyboard navigation */
.retry-button:focus-visible {
  outline: 2px solid var(--color-focus);
  outline-offset: 2px;
}

.chart-data-fallback summary:focus-visible {
  outline: 2px solid var(--color-focus);
  outline-offset: 2px;
}
</style>
