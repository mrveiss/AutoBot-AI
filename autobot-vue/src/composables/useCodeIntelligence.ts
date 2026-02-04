// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Code Intelligence API composable
 * Issue #772 - Code Intelligence & Repository Analysis
 */

import { ref } from 'vue'
import appConfig from '@/config/AppConfig.js'
import { createLogger } from '@/utils/debugUtils'
import type {
  HealthScoreResponse,
  SecurityScoreResponse,
  PerformanceScoreResponse,
  RedisHealthScoreResponse,
  AntiPatternType,
  VulnerabilityType,
  PerformanceIssueType,
  RedisOptimizationType,
  ReportResponse
} from '@/types/codeIntelligence'

const logger = createLogger('useCodeIntelligence')

export function useCodeIntelligence() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Health scores
  const healthScore = ref<HealthScoreResponse | null>(null)
  const securityScore = ref<SecurityScoreResponse | null>(null)
  const performanceScore = ref<PerformanceScoreResponse | null>(null)
  const redisScore = ref<RedisHealthScoreResponse | null>(null)

  // Type definitions
  const patternTypes = ref<Record<string, AntiPatternType> | null>(null)
  const vulnerabilityTypes = ref<VulnerabilityType[] | null>(null)
  const performanceIssueTypes = ref<PerformanceIssueType[] | null>(null)
  const redisOptimizationTypes = ref<Record<string, RedisOptimizationType> | null>(null)

  async function getBackendUrl(): Promise<string> {
    return await appConfig.getServiceUrl('backend')
  }

  async function fetchHealthScore(path: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(
        `${backendUrl}/api/code-intelligence/health-score?path=${encodeURIComponent(path)}`
      )
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      healthScore.value = await response.json()
    } catch (e) {
      error.value = `Failed to fetch health score: ${e}`
      logger.error('fetchHealthScore failed:', e)
    } finally {
      loading.value = false
    }
  }

  async function fetchSecurityScore(path: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(
        `${backendUrl}/api/code-intelligence/security/score?path=${encodeURIComponent(path)}`
      )
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      securityScore.value = await response.json()
    } catch (e) {
      error.value = `Failed to fetch security score: ${e}`
      logger.error('fetchSecurityScore failed:', e)
    } finally {
      loading.value = false
    }
  }

  async function fetchPerformanceScore(path: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(
        `${backendUrl}/api/code-intelligence/performance/score?path=${encodeURIComponent(path)}`
      )
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      performanceScore.value = await response.json()
    } catch (e) {
      error.value = `Failed to fetch performance score: ${e}`
      logger.error('fetchPerformanceScore failed:', e)
    } finally {
      loading.value = false
    }
  }

  async function fetchRedisScore(path: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(
        `${backendUrl}/api/code-intelligence/redis/health-score?path=${encodeURIComponent(path)}`
      )
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      redisScore.value = await response.json()
    } catch (e) {
      error.value = `Failed to fetch Redis score: ${e}`
      logger.error('fetchRedisScore failed:', e)
    } finally {
      loading.value = false
    }
  }

  async function fetchPatternTypes(): Promise<void> {
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(`${backendUrl}/api/code-intelligence/pattern-types`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      patternTypes.value = data.pattern_types
    } catch (e) {
      logger.error('fetchPatternTypes failed:', e)
    }
  }

  async function fetchVulnerabilityTypes(): Promise<void> {
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(`${backendUrl}/api/code-intelligence/security/vulnerability-types`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      vulnerabilityTypes.value = data.vulnerability_types
    } catch (e) {
      logger.error('fetchVulnerabilityTypes failed:', e)
    }
  }

  async function fetchPerformanceIssueTypes(): Promise<void> {
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(`${backendUrl}/api/code-intelligence/performance/issue-types`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      performanceIssueTypes.value = data.issue_types
    } catch (e) {
      logger.error('fetchPerformanceIssueTypes failed:', e)
    }
  }

  async function fetchRedisOptimizationTypes(): Promise<void> {
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(`${backendUrl}/api/code-intelligence/redis/optimization-types`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      redisOptimizationTypes.value = data.optimization_types
    } catch (e) {
      logger.error('fetchRedisOptimizationTypes failed:', e)
    }
  }

  async function downloadReport(
    path: string,
    type: 'security' | 'performance',
    format: 'json' | 'markdown'
  ): Promise<void> {
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(
        `${backendUrl}/api/code-intelligence/${type}/report?path=${encodeURIComponent(path)}&format=${format}`
      )
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data: ReportResponse = await response.json()

      // Create download
      const content = format === 'json'
        ? JSON.stringify(data.report, null, 2)
        : data.report as string
      const blob = new Blob([content], {
        type: format === 'json' ? 'application/json' : 'text/markdown'
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${type}-report-${new Date().toISOString().split('T')[0]}.${format === 'json' ? 'json' : 'md'}`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      error.value = `Failed to download report: ${e}`
      logger.error('downloadReport failed:', e)
    }
  }

  async function fetchAllScores(path: string): Promise<void> {
    await Promise.all([
      fetchHealthScore(path),
      fetchSecurityScore(path),
      fetchPerformanceScore(path),
      fetchRedisScore(path)
    ])
  }

  async function fetchAllTypes(): Promise<void> {
    await Promise.all([
      fetchPatternTypes(),
      fetchVulnerabilityTypes(),
      fetchPerformanceIssueTypes(),
      fetchRedisOptimizationTypes()
    ])
  }

  return {
    // State
    loading,
    error,
    healthScore,
    securityScore,
    performanceScore,
    redisScore,
    patternTypes,
    vulnerabilityTypes,
    performanceIssueTypes,
    redisOptimizationTypes,
    // Actions
    fetchHealthScore,
    fetchSecurityScore,
    fetchPerformanceScore,
    fetchRedisScore,
    fetchPatternTypes,
    fetchVulnerabilityTypes,
    fetchPerformanceIssueTypes,
    fetchRedisOptimizationTypes,
    fetchAllScores,
    fetchAllTypes,
    downloadReport
  }
}
