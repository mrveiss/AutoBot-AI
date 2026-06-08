// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useCodeQualityData
 *
 * Encapsulates all API calls for the Code Quality Dashboard.
 * Extracted from CodeQualityDashboard.vue (Issue #6055).
 *
 * Migrated from bare fetchWithAuth to useFetchEndpoint (#6152) for
 * AbortController, race protection, and consistent error handling.
 *
 * Endpoints (all under /api/quality/*):
 *   GET  /quality/health-score
 *   GET  /quality/metrics
 *   GET  /quality/patterns
 *   GET  /quality/complexity?top_n=5
 *   GET  /quality/trends?period=<period>
 *   GET  /quality/snapshot
 *   GET  /quality/drill-down/<category>
 *   GET  /quality/export?format=<format>
 */

import { computed, ref } from 'vue'
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useCodeQualityData')

// Issue #6671: Backend returns _no_data_response with status:"no_data" when no
// scan has happened yet (analytics_quality.py:_no_data_response). The frontend
// must treat that as a distinct empty state — not silently fall back to zeros.
export type QualityStatus = 'ok' | 'no_data'

export interface QualityHealthScore {
  status: QualityStatus
  message?: string
  overall: number
  grade: string
  trend: number
  breakdown: Record<string, number>
  components: Record<string, number>
  recommendations: string[]
}

export interface QualityMetric {
  name: string
  category: string
  value: number
  grade: string
  trend: number
  weight: number
}

export interface QualityPattern {
  type: string
  display_name: string
  count: number
  percentage: number
  severity: string
}

export interface QualityComplexity {
  status: QualityStatus
  message?: string
  averages: { cyclomatic: number; cognitive: number }
  maximums: { cyclomatic: number; cognitive: number }
  hotspots: Array<{ file: string; complexity: number; lines: number }>
}

export interface QualityDrillDown {
  total_files: number
  total_issues: number
  average_score: number
  files: Array<{ path: string; issues: number; score: number; top_issue: string }>
}

export interface QualityExportResult {
  format: string
  content?: string
  [key: string]: unknown
}

export interface QualitySnapshot {
  status: QualityStatus
  message?: string
  files: number
  lines: number
  issues: number
}

function readStatus(raw: Record<string, unknown>): QualityStatus {
  return (raw.status as QualityStatus | undefined) === 'no_data' ? 'no_data' : 'ok'
}

function readMessage(raw: Record<string, unknown>): string | undefined {
  const msg = raw.message
  return typeof msg === 'string' ? msg : undefined
}

export function useCodeQualityData(withSourceId: (url: string) => string) {
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  // Issue #6671: track no-data state independently for each endpoint so the
  // dashboard can render an empty-state banner instead of silent zeros.
  const noDataMessage = ref<string | null>(null)
  const noDataFlags = ref({
    healthScore: false,
    metrics: false,
    patterns: false,
    complexity: false,
    trends: false,
    snapshot: false,
  })
  const noDataState = computed(() => ({
    noData: Object.values(noDataFlags.value).some(Boolean),
    message: noDataMessage.value,
  }))

  function recordStatus(key: keyof typeof noDataFlags.value, raw: Record<string, unknown>) {
    const status = readStatus(raw)
    noDataFlags.value[key] = status === 'no_data'
    if (status === 'no_data' && !noDataMessage.value) {
      noDataMessage.value = readMessage(raw) ?? null
    }
    if (Object.values(noDataFlags.value).every((flag) => !flag)) {
      noDataMessage.value = null
    }
  }

  // ---- Health Score --------------------------------------------------------
  // Issue #552: backend uses /api/quality/* not /api/analytics/quality/*
  // Issue #3436: scope to project when sourceId is present

  const healthScoreEndpoint = useFetchEndpoint<Record<string, unknown>, QualityHealthScore>(
    {
      path: '/api/quality/health-score',
      scopeToSource: true,
      pickData: (raw) => {
        recordStatus('healthScore', raw)
        return {
          status: readStatus(raw),
          message: readMessage(raw),
          overall: (raw.overall as number) ?? 0,
          grade: (raw.grade as string) || 'C',
          trend: (raw.trend as number) ?? 0,
          breakdown: (raw.breakdown as Record<string, number>) || {},
          components: (raw.components as Record<string, number>) || { code_quality: 0, security: 0, performance: 0 },
          recommendations: (raw.recommendations as string[]) || [],
        }
      },
      onError: (message, err) => {
        logger.warn('Failed to load health score:', err)
        error.value = message
      },
      label: 'Health score',
    },
    { withSourceId },
  )

  async function fetchHealthScore(): Promise<QualityHealthScore | null> {
    error.value = null
    isLoading.value = true
    try {
      await healthScoreEndpoint.load()
      return healthScoreEndpoint.data.value
    } finally {
      isLoading.value = false
    }
  }

  // ---- Metrics ------------------------------------------------------------

  const metricsEndpoint = useFetchEndpoint<unknown, QualityMetric[]>(
    {
      // Issue #552 / #3436
      path: '/api/quality/metrics',
      scopeToSource: true,
      pickData: (raw) => {
        if (Array.isArray(raw)) {
          noDataFlags.value.metrics = false
          return raw as QualityMetric[]
        }
        const obj = (raw as Record<string, unknown>) ?? {}
        recordStatus('metrics', obj)
        return (obj.metrics as QualityMetric[]) || []
      },
      onError: (message, err) => {
        logger.warn('Failed to load metrics:', err)
        error.value = message
      },
      fallbackData: () => [],
      label: 'Metrics',
    },
    { withSourceId },
  )

  async function fetchMetrics(): Promise<QualityMetric[]> {
    error.value = null
    isLoading.value = true
    try {
      await metricsEndpoint.load()
      return metricsEndpoint.data.value ?? []
    } finally {
      isLoading.value = false
    }
  }

  // ---- Patterns -----------------------------------------------------------

  const patternsEndpoint = useFetchEndpoint<unknown, QualityPattern[]>(
    {
      // Issue #552 / #3436
      path: '/api/quality/patterns',
      scopeToSource: true,
      pickData: (raw) => {
        if (Array.isArray(raw)) {
          noDataFlags.value.patterns = false
          return raw as QualityPattern[]
        }
        const obj = (raw as Record<string, unknown>) ?? {}
        recordStatus('patterns', obj)
        return (obj.patterns as QualityPattern[]) || []
      },
      onError: (message, err) => {
        logger.warn('Failed to load patterns:', err)
        error.value = message
      },
      fallbackData: () => [],
      label: 'Patterns',
    },
    { withSourceId },
  )

  async function fetchPatterns(): Promise<QualityPattern[]> {
    error.value = null
    isLoading.value = true
    try {
      await patternsEndpoint.load()
      return patternsEndpoint.data.value ?? []
    } finally {
      isLoading.value = false
    }
  }

  // ---- Complexity ---------------------------------------------------------

  const complexityEndpoint = useFetchEndpoint<Record<string, unknown>, QualityComplexity>(
    {
      // Issue #552 / #3436
      path: '/api/quality/complexity',
      scopeToSource: true,
      pickData: (raw) => {
        recordStatus('complexity', raw)
        return {
          status: readStatus(raw),
          message: readMessage(raw),
          averages: (raw.averages as { cyclomatic: number; cognitive: number }) || { cyclomatic: 0, cognitive: 0 },
          maximums: (raw.maximums as { cyclomatic: number; cognitive: number }) || { cyclomatic: 0, cognitive: 0 },
          hotspots: (raw.hotspots as Array<{ file: string; complexity: number; lines: number }>) || [],
        }
      },
      onError: (message, err) => {
        logger.warn('Failed to load complexity:', err)
        error.value = message
      },
      label: 'Complexity',
    },
    { withSourceId },
  )

  async function fetchComplexity(): Promise<QualityComplexity | null> {
    error.value = null
    isLoading.value = true
    try {
      await complexityEndpoint.load({ top_n: '5' })
      return complexityEndpoint.data.value
    } finally {
      isLoading.value = false
    }
  }

  // ---- Trends -------------------------------------------------------------

  const trendsEndpoint = useFetchEndpoint<Record<string, unknown>, Array<{ date: string; score: number }>>(
    {
      // Issue #552 / #3436
      path: '/api/quality/trends',
      scopeToSource: true,
      pickData: (raw) => {
        recordStatus('trends', raw)
        return (raw.data_points as Array<{ date: string; score: number }>) || []
      },
      onError: (message, err) => {
        logger.warn('Failed to load trends:', err)
        error.value = message
      },
      fallbackData: () => [],
      label: 'Trends',
    },
    { withSourceId },
  )

  async function fetchTrends(period: string): Promise<Array<{ date: string; score: number }>> {
    error.value = null
    isLoading.value = true
    try {
      await trendsEndpoint.load({ period })
      return trendsEndpoint.data.value ?? []
    } finally {
      isLoading.value = false
    }
  }

  // ---- Snapshot -----------------------------------------------------------

  const snapshotEndpoint = useFetchEndpoint<Record<string, unknown>, QualitySnapshot>(
    {
      // Issue #552 / #3436
      path: '/api/quality/snapshot',
      scopeToSource: true,
      pickData: (raw) => {
        recordStatus('snapshot', raw)
        const stats =
          (raw.codebase_stats as { files: number; lines: number; issues: number }) || {
            files: 0,
            lines: 0,
            issues: 0,
          }
        return {
          status: readStatus(raw),
          message: readMessage(raw),
          ...stats,
        }
      },
      onError: (message, err) => {
        logger.warn('Failed to load snapshot:', err)
        error.value = message
      },
      label: 'Snapshot',
    },
    { withSourceId },
  )

  async function fetchSnapshot(): Promise<QualitySnapshot | null> {
    error.value = null
    isLoading.value = true
    try {
      await snapshotEndpoint.load()
      return snapshotEndpoint.data.value
    } finally {
      isLoading.value = false
    }
  }

  // ---- Drill-down ---------------------------------------------------------
  // Dynamic path (includes category) — create a fresh endpoint per call so the
  // AbortController still fires for in-flight requests from the same invocation.

  async function fetchDrillDown(category: string): Promise<QualityDrillDown | null> {
    error.value = null
    isLoading.value = true
    try {
      // Issue #552 / #3436
      const ep = useFetchEndpoint<Record<string, unknown>, QualityDrillDown>(
        {
          path: `/api/quality/drill-down/${encodeURIComponent(category)}`,
          scopeToSource: true,
          pickData: (raw) => raw as unknown as QualityDrillDown,
          onError: (message, err) => {
            logger.warn('Failed to load drill-down data:', err)
            error.value = message
          },
          label: 'Drill-down',
        },
        { withSourceId },
      )
      await ep.load()
      return ep.data.value
    } finally {
      isLoading.value = false
    }
  }

  // ---- Export -------------------------------------------------------------

  async function fetchExport(format: string): Promise<QualityExportResult | null> {
    error.value = null
    isLoading.value = true
    try {
      // Issue #552: no source scoping for export
      const ep = useFetchEndpoint<Record<string, unknown>, QualityExportResult>(
        {
          path: '/api/quality/export',
          scopeToSource: false,
          pickData: (raw) => raw as QualityExportResult,
          onError: (message, err) => {
            logger.warn('Failed to export report:', err)
            error.value = message
          },
          label: 'Export',
        },
      )
      await ep.load({ format })
      return ep.data.value
    } finally {
      isLoading.value = false
    }
  }

  return {
    isLoading,
    error,
    noDataState,
    fetchHealthScore,
    fetchMetrics,
    fetchPatterns,
    fetchComplexity,
    fetchTrends,
    fetchSnapshot,
    fetchDrillDown,
    fetchExport,
  }
}
