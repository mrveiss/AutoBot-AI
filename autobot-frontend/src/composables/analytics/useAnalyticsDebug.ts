// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useAnalyticsDebug
 *
 * Encapsulates debug/testing utilities for the codebase analytics
 * dashboard: NPU connection test, endpoint health checks,
 * data state inspection, state reset, and display utility functions.
 *
 * Issues #2228, #2230: Extracted from CodebaseAnalytics.vue
 */

import { type Ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'
import type { ToastType } from '@/composables/useToast'

const logger = createLogger('useAnalyticsDebug')

export interface UseAnalyticsDebugDeps {
  rootPath: Ref<string>
  analyzing: Ref<boolean>
  progressStatus: Ref<string>
  currentJobId: Ref<string | null>
  currentJobStatus: Ref<string | null>
  progressPercent: Ref<number>
  codebaseStats: Ref<Record<string, unknown> | null>
  problemsReport: Ref<Array<{ severity: string; [key: string]: unknown }>>
  declarationAnalysis: Ref<unknown[]>
  duplicateAnalysis: Ref<unknown[]>
  stopJobPolling: () => void
  t: (key: string, params?: Record<string, unknown>) => string
  notify: (msg: string, type?: ToastType) => void
}

// Endpoint configs for API health check (#1588)
const _testEndpointConfigs = [
  { name: 'Declarations', path: `${getApiBase()}/analytics/codebase/declarations` },
  { name: 'Duplicates', path: `${getApiBase()}/analytics/codebase/duplicates` },
  { name: 'Hardcodes', path: `${getApiBase()}/analytics/codebase/hardcodes` },
  { name: 'NPU', path: `${getApiBase()}/npu/status` },
  { name: 'Stats', path: `${getApiBase()}/analytics/codebase/stats` },
]

export function useAnalyticsDebug(deps: UseAnalyticsDebugDeps) {
  const {
    rootPath,
    analyzing,
    progressStatus,
    currentJobId,
    currentJobStatus,
    progressPercent,
    codebaseStats,
    problemsReport,
    declarationAnalysis,
    duplicateAnalysis,
    stopJobPolling,
    t,
    notify,
  } = deps

  // Issue #1007: NPU health check via backend proxy
  const testNpuConnection = async () => {
    const startTime = Date.now()
    try {
      const data = await apiClient.get<{
        available?: boolean
        status?: string
        workers_connected?: number
        total_workers?: number
      }>('/api/npu/status')
      const responseTime = Date.now() - startTime
      const available =
        data.available ||
        data.status === 'ok' ||
        (data.workers_connected ?? 0) > 0
      const workerCount =
        data.workers_connected ?? data.total_workers ?? 0
      notify(
        t('analytics.codebase.notify.npuStatus', {
          status: available
            ? t('analytics.codebase.available')
            : t('analytics.codebase.notAvailable'),
          workers: workerCount,
          time: responseTime,
        }),
        available ? 'success' : 'warning',
      )
    } catch (error: unknown) {
      const responseTime = Date.now() - startTime
      const errorMessage =
        error instanceof Error ? error.message : String(error)
      logger.error('NPU connection failed:', error)
      notify(
        t('analytics.codebase.notify.npuFailed', {
          error: errorMessage,
          time: responseTime,
        }),
        'error',
      )
    }
  }

  // Test all endpoints functionality
  const testAllEndpoints = async () => {
    progressStatus.value = t(
      'analytics.codebase.status.testingApis',
    )
    try {
      const results: string[] = []
      for (const ep of _testEndpointConfigs) {
        try {
          await apiClient.get<any>(ep.path)
          results.push(`${ep.name}: OK`)
        } catch (err) {
          const msg =
            err instanceof Error ? err.message : String(err)
          results.push(`${ep.name}: FAIL (${msg})`)
        }
      }
      const passed = results.filter((r) =>
        r.includes('OK'),
      ).length
      const failed = results.filter((r) =>
        r.includes('FAIL'),
      ).length
      notify(
        t('analytics.codebase.notify.apiTestResults', {
          passed,
          total: results.length,
        }),
        failed === 0 ? 'success' : 'warning',
      )
      logger.debug(
        'API Test Results:',
        results.join('\n'),
      )
    } catch (error: unknown) {
      const errorMessage =
        error instanceof Error ? error.message : String(error)
      logger.error('API tests failed:', error)
      notify(
        t('analytics.codebase.notify.apiTestsFailed', {
          error: errorMessage,
        }),
        'error',
      )
    } finally {
      progressStatus.value = t(
        'analytics.codebase.status.ready',
      )
    }
  }

  // Debug function to check data state
  const testDataState = () => {
    const summary = {
      analyzing: analyzing.value,
      rootPath: rootPath.value,
      currentJobId: currentJobId.value,
      problems: problemsReport.value?.length || 0,
      declarations: declarationAnalysis.value?.length || 0,
      duplicates: duplicateAnalysis.value?.length || 0,
      stats: codebaseStats.value ? 'Available' : 'Not loaded',
    }
    logger.info('Debug State:', summary)
    notify(
      t('analytics.codebase.notify.debugState', {
        analyzing: summary.analyzing,
        path: summary.rootPath ? 'set' : 'empty',
        jobId: summary.currentJobId || 'none',
        problems: summary.problems,
      }),
      'info',
    )
  }

  // Reset stuck state (debug helper)
  const resetState = () => {
    analyzing.value = false
    currentJobId.value = null
    currentJobStatus.value = null
    stopJobPolling()
    progressPercent.value = 0
    progressStatus.value = t(
      'analytics.codebase.status.stateReset',
    )
    notify(
      t('analytics.codebase.notify.stateReset'),
      'success',
    )
  }

  // --- Display utility functions ---

  const getSeverityClass = (severity: string): string => {
    switch (severity?.toLowerCase()) {
      case 'critical':
        return 'severity-critical'
      case 'high':
        return 'severity-high'
      case 'medium':
        return 'severity-medium'
      case 'low':
        return 'severity-low'
      default:
        return 'severity-info'
    }
  }

  const truncateValue = (
    value: string,
    maxLength = 50,
  ): string => {
    if (!value) return 'Unknown'
    const str = String(value)
    if (str.length <= maxLength) return str
    return str.substring(0, maxLength) + '...'
  }

  const getRiskClass = (riskScore: number): string => {
    if (riskScore >= 80) return 'item-critical'
    if (riskScore >= 60) return 'item-warning'
    if (riskScore >= 40) return 'item-info'
    return 'item-success'
  }

  const formatFactorName = (factor: string): string => {
    return factor
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (l) => l.toUpperCase())
  }

  const getGradeClass = (grade: string): string => {
    const gradeUpper = grade?.toUpperCase() || ''
    if (gradeUpper === 'A' || gradeUpper === 'A+')
      return 'grade-a'
    if (gradeUpper === 'B' || gradeUpper === 'B+')
      return 'grade-b'
    if (gradeUpper === 'C' || gradeUpper === 'C+')
      return 'grade-c'
    if (gradeUpper === 'D' || gradeUpper === 'D+')
      return 'grade-d'
    return 'grade-f'
  }

  const formatTimestamp = (
    timestamp: string | number | Date | undefined,
  ): string => {
    if (!timestamp) return 'Unknown'
    try {
      const date = new Date(timestamp)
      return date.toLocaleString()
    } catch {
      return String(timestamp)
    }
  }

  const getScoreClass = (score: number): string => {
    if (score >= 80) return 'score-high'
    if (score >= 60) return 'score-medium'
    return 'score-low'
  }

  const getPriorityClass = (
    severity: string | undefined,
  ): string => {
    switch (severity?.toLowerCase()) {
      case 'critical':
        return 'priority-critical'
      case 'high':
        return 'priority-high'
      case 'medium':
        return 'priority-medium'
      default:
        return 'priority-low'
    }
  }

  return {
    // Debug functions
    testNpuConnection,
    testAllEndpoints,
    testDataState,
    resetState,
    // Display utilities
    getSeverityClass,
    truncateValue,
    getRiskClass,
    formatFactorName,
    getGradeClass,
    formatTimestamp,
    getScoreClass,
    getPriorityClass,
  }
}
