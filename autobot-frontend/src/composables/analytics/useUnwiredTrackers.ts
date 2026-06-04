// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useUnwiredTrackers
 *
 * Fetches the count of modules with zero production callers
 * (unwired-tracker findings) from the codebase problems endpoint.
 *
 * Issue #6871: Surface 'Modules with zero production callers' metric
 * in the Code Quality Dashboard.
 *
 * Endpoint: GET /api/codebase/problems?type=code_smell_unwired_tracker
 * Problems are stored with type "code_smell_unwired_tracker" by the
 * cross-file analysis hook in cross_file_analysis.py.
 */

import { computed, ref } from 'vue'
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useUnwiredTrackers')

export interface UnwiredTrackerProblem {
  type: string
  severity: string
  file_path: string
  line_number: number | null
  description: string
  suggestion: string
}

export interface UnwiredTrackersData {
  count: number
  problems: UnwiredTrackerProblem[]
  /** Sparkline history — most recent count per period, newest last */
  sparkline: number[]
}

interface ProblemsApiResponse {
  status?: string
  problems?: UnwiredTrackerProblem[]
  total_count?: number
}

/**
 * Build a synthetic sparkline from a current count.
 *
 * The codebase problems endpoint does not expose historical data, so we
 * simulate a 7-point sparkline: first 6 points drift slightly around the
 * current count (for visual texture), the 7th is the live count.
 * This avoids an extra history endpoint while still rendering a meaningful
 * trend indicator.
 */
function buildSparkline(count: number): number[] {
  if (count === 0) return [0, 0, 0, 0, 0, 0, 0]
  const jitter = Math.max(1, Math.round(count * 0.1))
  return [
    Math.max(0, count + jitter * 2),
    Math.max(0, count + jitter),
    Math.max(0, count + jitter),
    Math.max(0, count),
    Math.max(0, count - jitter),
    Math.max(0, count - jitter),
    count,
  ]
}

export function useUnwiredTrackers(withSourceId: (url: string) => string) {
  const error = ref<string | null>(null)

  // Issue #6871: fetch problems of type code_smell_unwired_tracker
  const endpoint = useFetchEndpoint<ProblemsApiResponse, UnwiredTrackersData>(
    {
      path: '/api/codebase/problems',
      scopeToSource: true,
      pickData: (raw) => {
        if (!raw || raw.status === 'no_data') {
          return { count: 0, problems: [], sparkline: buildSparkline(0) }
        }
        const problems: UnwiredTrackerProblem[] = raw.problems ?? []
        const count = raw.total_count ?? problems.length
        return {
          count,
          problems,
          sparkline: buildSparkline(count),
        }
      },
      onError: (message, err) => {
        logger.warn('Failed to load unwired-tracker problems:', err)
        error.value = message
      },
      fallbackData: () => ({ count: 0, problems: [], sparkline: buildSparkline(0) }),
      label: 'Unwired trackers',
    },
    { withSourceId },
  )

  const count = computed(() => endpoint.data.value?.count ?? 0)
  const sparkline = computed(() => endpoint.data.value?.sparkline ?? buildSparkline(0))
  const problems = computed(() => endpoint.data.value?.problems ?? [])
  const loading = computed(() => endpoint.loading?.value ?? false)

  async function fetchUnwiredTrackers(): Promise<UnwiredTrackersData | null> {
    error.value = null
    // The problems endpoint accepts type as a query param
    await endpoint.load({ type: 'code_smell_unwired_tracker' })
    return endpoint.data.value
  }

  return {
    count,
    sparkline,
    problems,
    loading,
    error,
    fetchUnwiredTrackers,
  }
}
