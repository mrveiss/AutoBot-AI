<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * TracingView - Distributed trace browser
 *
 * Provides filtering, sorting, pagination, and expandable span waterfall
 * for trace inspection.
 * Issue #752 - Comprehensive performance monitoring.
 */

import { ref, computed, onMounted, watch } from 'vue'
import { usePerformanceMonitoring } from '@/composables/usePerformanceMonitoring'
import type {
  TraceItem,
  TraceDetail,
  TraceSpan,
  TraceQueryParams,
} from '@/composables/usePerformanceMonitoring'

const {
  traces,
  traceTotal,
  loading,
  error,
  fetchTraces,
  fetchTraceDetail,
} = usePerformanceMonitoring()

// Filter state
const timeRange = ref('24')
const statusFilter = ref('all')
const nodeFilter = ref('')
const page = ref(1)
const pageSize = ref(50)

// Expanded trace detail
const expandedTraceId = ref<string | null>(null)
const expandedDetail = ref<TraceDetail | null>(null)
const detailLoading = ref(false)

const timeRangeOptions = [
  { label: '1h', value: '1' },
  { label: '6h', value: '6' },
  { label: '24h', value: '24' },
  { label: '7d', value: '168' },
]

const statusOptions = [
  { label: 'All', value: 'all' },
  { label: 'OK', value: 'ok' },
  { label: 'Error', value: 'error' },
  { label: 'Timeout', value: 'timeout' },
]

const totalPages = computed(() => Math.max(1, Math.ceil(traceTotal.value / pageSize.value)))

/**
 * Build query params from current filter state.
 */
function buildParams(): TraceQueryParams {
  return {
    hours: parseInt(timeRange.value, 10),
    status: statusFilter.value === 'all' ? undefined : statusFilter.value,
    node_id: nodeFilter.value || undefined,
    page: page.value,
    per_page: pageSize.value,
  }
}

/**
 * Load traces with current filters.
 */
async function loadTraces(): Promise<void> {
  await fetchTraces(buildParams())
}

/**
 * Reload traces with current filters.
 */
function reloadTraces(): void {
  page.value = 1
  loadTraces()
}

/**
 * Handle filter change.
 */
function onFilterChange(): void {
  page.value = 1
  loadTraces()
}

/**
 * Navigate to a page.
 */
function goToPage(p: number): void {
  if (p >= 1 && p <= totalPages.value) {
    page.value = p
    loadTraces()
  }
}

/**
 * Toggle trace detail expansion.
 */
async function toggleExpand(trace: TraceItem): Promise<void> {
  if (expandedTraceId.value === trace.trace_id) {
    expandedTraceId.value = null
    expandedDetail.value = null
    return
  }
  expandedTraceId.value = trace.trace_id
  detailLoading.value = true
  expandedDetail.value = await fetchTraceDetail(trace.trace_id)
  detailLoading.value = false
}

/**
 * Build a tree structure from flat spans.
 *
 * Helper for toggleExpand display (Issue #752).
 */
function buildSpanTree(
  spans: TraceSpan[]
): Array<TraceSpan & { children: TraceSpan[]; depth: number }> {
  type SpanNode = TraceSpan & { children: SpanNode[]; depth: number }

  const map = new Map<string, SpanNode>()
  const roots: SpanNode[] = []

  for (const span of spans) {
    map.set(span.span_id, { ...span, children: [], depth: 0 })
  }

  for (const node of map.values()) {
    if (node.parent_span_id && map.has(node.parent_span_id)) {
      const parent = map.get(node.parent_span_id)!
      node.depth = parent.depth + 1
      parent.children.push(node)
    } else {
      roots.push(node)
    }
  }

  return flattenTree(roots)
}

/**
 * Flatten nested span tree into ordered list for rendering.
 *
 * Helper for buildSpanTree (Issue #752).
 */
function flattenTree(
  nodes: Array<TraceSpan & { children: Array<TraceSpan & { children: unknown[]; depth: number }>; depth: number }>
): Array<TraceSpan & { children: TraceSpan[]; depth: number }> {
  const result: Array<TraceSpan & { children: TraceSpan[]; depth: number }> = []
  for (const node of nodes) {
    result.push(node as TraceSpan & { children: TraceSpan[]; depth: number })
    if (node.children.length > 0) {
      result.push(
        ...flattenTree(
          node.children as Array<TraceSpan & { children: Array<TraceSpan & { children: unknown[]; depth: number }>; depth: number }>
        )
      )
    }
  }
  return result
}

/**
 * Compute the width percentage of a span relative to total trace duration.
 */
function spanWidthPercent(span: TraceSpan, totalMs: number): number {
  if (totalMs <= 0) return 0
  return Math.max(1, (span.duration_ms / totalMs) * 100)
}

/**
 * Get status badge classes for a status string.
 */
function statusBadgeClass(status: string): string {
  switch (status) {
    case 'ok': return 'bg-green-100 text-green-700'
    case 'error': return 'bg-red-100 text-red-700'
    case 'timeout': return 'bg-amber-100 text-amber-700'
    default: return 'bg-gray-100 text-gray-700'
  }
}

/**
 * Get span bar color class for a status string.
 */
function spanBarColor(status: string): string {
  switch (status) {
    case 'ok': return 'bg-green-500'
    case 'error': return 'bg-red-500'
    case 'timeout': return 'bg-amber-500'
    default: return 'bg-gray-400'
  }
}

/**
 * Format duration for display.
 */
function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms.toFixed(0)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

/**
 * Format date string for display.
 */
function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString()
}


// Watch for filter changes that require immediate reload
watch([timeRange, statusFilter], () => {
  onFilterChange()
})

onMounted(() => {
  loadTraces()
})
</script>

<template>
  <div class="p-6">
    <!-- Error Banner -->
    <div
      v-if="error"
      class="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm"
    >
      {{ error }}
    </div>

    <!-- Filter Bar -->
    <div class="flex flex-wrap items-center gap-3 mb-4">
      <!-- Time Range -->
      <div class="flex items-center gap-1">
        <span class="text-sm text-gray-500">Time:</span>
        <div class="flex rounded-lg border border-gray-300 overflow-hidden">
          <button
            v-for="opt in timeRangeOptions"
            :key="opt.value"
            @click="timeRange = opt.value"
            :class="[
              'px-3 py-1.5 text-xs font-medium transition-colors',
              timeRange === opt.value
                ? 'bg-primary-600 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-50'
            ]"
          >
            {{ opt.label }}
          </button>
        </div>
      </div>

      <!-- Status Filter -->
      <div class="flex items-center gap-1">
        <span class="text-sm text-gray-500">Status:</span>
        <select
          v-model="statusFilter"
          class="text-sm border border-gray-300 rounded-lg px-2 py-1.5 bg-white"
        >
          <option v-for="opt in statusOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
      </div>

      <!-- Node Filter -->
      <div class="flex items-center gap-1">
        <span class="text-sm text-gray-500">Node:</span>
        <input
          v-model="nodeFilter"
          type="text"
          placeholder="Node ID..."
          class="text-sm border border-gray-300 rounded-lg px-2 py-1.5 w-36"
          @keyup.enter="onFilterChange"
        />
      </div>

      <button
        @click="onFilterChange"
        class="px-3 py-1.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
      >
        Apply
      </button>

      <div class="flex-1"></div>

      <span class="text-sm text-gray-400">
        {{ traceTotal.toLocaleString() }} trace{{ traceTotal !== 1 ? 's' : '' }}
      </span>
    </div>

    <!-- Traces Table -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 mb-4">
      <div v-if="traces.length === 0 && !loading" class="p-8 text-center text-gray-400">
        No traces found for the current filters
      </div>
      <div v-else class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th class="w-8 px-2 py-2"></th>
              <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                Name
              </th>
              <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                Duration
              </th>
              <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                Spans
              </th>
              <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                Status
              </th>
              <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                Node
              </th>
              <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                Time
              </th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200">
            <template v-for="trace in traces" :key="trace.trace_id">
              <!-- Trace Row -->
              <tr
                class="hover:bg-gray-50 cursor-pointer"
                @click="toggleExpand(trace)"
              >
                <td class="px-2 py-2 text-center text-gray-400">
                  <svg
                    :class="[
                      'w-4 h-4 transition-transform',
                      expandedTraceId === trace.trace_id ? 'rotate-90' : ''
                    ]"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      stroke-width="2"
                      d="M9 5l7 7-7 7"
                    />
                  </svg>
                </td>
                <td class="px-4 py-2 text-sm text-gray-900 font-medium max-w-xs truncate">
                  {{ trace.name }}
                </td>
                <td class="px-4 py-2 text-sm font-mono">
                  {{ formatDuration(trace.duration_ms) }}
                </td>
                <td class="px-4 py-2 text-sm text-gray-600">{{ trace.span_count }}</td>
                <td class="px-4 py-2">
                  <span
                    :class="[
                      'px-2 py-0.5 text-xs font-medium rounded-full',
                      statusBadgeClass(trace.status)
                    ]"
                  >
                    {{ trace.status }}
                  </span>
                </td>
                <td class="px-4 py-2 text-sm text-gray-500">
                  {{ trace.source_node_id ?? '-' }}
                </td>
                <td class="px-4 py-2 text-sm text-gray-500 whitespace-nowrap">
                  {{ formatDate(trace.created_at) }}
                </td>
              </tr>

              <!-- Expanded Span Waterfall -->
              <tr v-if="expandedTraceId === trace.trace_id">
                <td colspan="7" class="px-4 py-4 bg-gray-50">
                  <div v-if="detailLoading" class="text-center text-gray-400 py-4">
                    Loading span details...
                  </div>
                  <div v-else-if="expandedDetail" class="space-y-1">
                    <div class="text-xs font-medium text-gray-500 mb-2">
                      Span Waterfall - {{ expandedDetail.spans.length }} span{{ expandedDetail.spans.length !== 1 ? 's' : '' }}
                    </div>
                    <div
                      v-for="span in buildSpanTree(expandedDetail.spans)"
                      :key="span.span_id"
                      class="flex items-center gap-2"
                      :style="{ paddingLeft: `${span.depth * 20}px` }"
                    >
                      <span class="text-xs text-gray-500 w-32 truncate flex-shrink-0">
                        {{ span.service_name }}
                      </span>
                      <span class="text-xs text-gray-700 w-40 truncate flex-shrink-0">
                        {{ span.name }}
                      </span>
                      <div class="flex-1 h-5 bg-gray-200 rounded relative">
                        <div
                          :class="['h-full rounded', spanBarColor(span.status)]"
                          :style="{ width: `${spanWidthPercent(span, expandedDetail!.duration_ms)}%` }"
                        ></div>
                      </div>
                      <span class="text-xs font-mono text-gray-600 w-16 text-right flex-shrink-0">
                        {{ formatDuration(span.duration_ms) }}
                      </span>
                      <span
                        :class="[
                          'px-1.5 py-0.5 text-xs font-medium rounded',
                          statusBadgeClass(span.status)
                        ]"
                      >
                        {{ span.status }}
                      </span>
                    </div>
                  </div>
                  <div v-else class="text-center text-gray-400 py-4">
                    Failed to load span details
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Pagination -->
    <div v-if="totalPages > 1" class="flex items-center justify-between">
      <span class="text-sm text-gray-500">
        Page {{ page }} of {{ totalPages }}
      </span>
      <div class="flex items-center gap-1">
        <button
          @click="goToPage(1)"
          :disabled="page === 1"
          class="px-2 py-1 text-sm border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          First
        </button>
        <button
          @click="goToPage(page - 1)"
          :disabled="page === 1"
          class="px-2 py-1 text-sm border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Prev
        </button>
        <button
          @click="goToPage(page + 1)"
          :disabled="page >= totalPages"
          class="px-2 py-1 text-sm border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Next
        </button>
        <button
          @click="goToPage(totalPages)"
          :disabled="page >= totalPages"
          class="px-2 py-1 text-sm border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Last
        </button>
      </div>
    </div>
  </div>
</template>
