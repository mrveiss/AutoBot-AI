// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useLogPatternData
 *
 * Encapsulates all log-pattern API calls: mining patterns and fetching
 * real-time log summary data.
 *
 * Issue #6064: Extracted from LogPatternDashboard.vue.
 */

import { createLogger } from '@/utils/debugUtils'
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'

const logger = createLogger('useLogPatternData')

export interface LogPattern {
  pattern_id: string
  pattern_template: string
  occurrences: number
  first_seen: string
  last_seen: string
  log_levels: string[]
  sources: string[]
  sample_messages: string[]
  frequency_per_hour: number
  is_error_pattern: boolean
  is_anomaly: boolean
}

export interface LogAnomaly {
  anomaly_id: string
  anomaly_type: string
  severity: string
  description: string
  timestamp: string
  affected_sources: string[]
  metric_before: number
  metric_after: number
  confidence: number
}

export interface LogTrend {
  trend_id: string
  metric_name: string
  direction: string
  change_percent: number
  time_period: string
  data_points: Array<Record<string, unknown>>
}

export interface MiningResult {
  patterns: LogPattern[]
  anomalies: LogAnomaly[]
  trends: LogTrend[]
  summary: {
    total_logs: number
    unique_patterns: number
    error_patterns: number
    anomalies_detected: number
  }
  analysis_time_ms: number
  logs_analyzed: number
}

export interface RealtimeData {
  logs_last_5min: number
  error_count: number
  level_counts: Record<string, number>
  recent_errors: Array<Record<string, unknown>>
}

export function useLogPatternData() {
  const mineEndpoint = useFetchEndpoint<MiningResult, MiningResult>(
    {
      path: '/api/log-patterns/mine',
      pickData: (raw) => raw,
      onError: (_message, err) => { logger.error('Failed to run log analysis:', err) },
      label: 'Log pattern mining',
    },
  )

  const realtimeEndpoint = useFetchEndpoint<RealtimeData, RealtimeData>(
    {
      path: '/api/log-patterns/realtime',
      pickData: (raw) => raw,
      onError: (_message, err) => { logger.error('Failed to fetch realtime data:', err) },
      label: 'Log pattern realtime',
    },
  )

  async function fetchMiningResult(hours: number): Promise<MiningResult | null> {
    await mineEndpoint.load({
      hours: String(hours),
      include_anomalies: 'true',
      include_trends: 'true',
    })
    return mineEndpoint.data.value
  }

  async function fetchRealtimeData(): Promise<RealtimeData | null> {
    await realtimeEndpoint.load()
    return realtimeEndpoint.data.value
  }

  return { fetchMiningResult, fetchRealtimeData }
}
