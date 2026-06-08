// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * useKnowledgeMaintenance Composable
 *
 * Extracts inline fetching from KnowledgeMaintenance.vue (#6053).
 * GET /knowledge-maintenance/health/dashboard → useFetchEndpoint (Pattern A).
 */

import { createLogger } from '@/utils/debugUtils'
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'

const logger = createLogger('useKnowledgeMaintenance')

// ==================== Types ====================

export interface HealthDashboardStats {
  total_facts: number
  total_vectors: number
  db_size: number
  categories: number
  embedding_cache: Record<string, unknown>
}

export interface HealthDashboardQuality {
  overall_score: number
  dimensions: Record<string, number>
  critical_issues: number
  warnings: number
}

export interface HealthDashboard {
  status: 'healthy' | 'warning' | 'degraded' | 'error'
  last_updated: string
  stats: HealthDashboardStats
  quality: HealthDashboardQuality
  top_recommendations: string[]
}

// ==================== Composable ====================

export function useKnowledgeMaintenance() {
  // GET health dashboard — useFetchEndpoint provides AbortController + race protection
  const healthEndpoint = useFetchEndpoint<HealthDashboard, HealthDashboard>({
    path: '/api/knowledge-maintenance/health/dashboard',
    label: 'fetchHealthDashboard',
    pickData: (raw) => raw ?? null,
    onSuccess: (data) => {
      logger.info('Health dashboard loaded:', data.status)
    },
    onError: (message) => {
      logger.error('Failed to load health dashboard:', message)
    },
  })

  return {
    /** Reactive health dashboard data, null until first successful load. */
    healthDashboard: healthEndpoint.data,
    /** True while the health dashboard fetch is in-flight. */
    isLoadingHealth: healthEndpoint.loading,
    /** Error message from the last failed health dashboard fetch, empty string if none. */
    healthError: healthEndpoint.error,
    /** Trigger (or re-trigger) the health dashboard fetch. */
    loadHealthDashboard: () => healthEndpoint.load(),
  }
}
