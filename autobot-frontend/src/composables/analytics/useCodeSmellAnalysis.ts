// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useCodeSmellAnalysis
 *
 * Code smell detection and health score calculation.
 * Extracted from useCodeIntelAnalysis (Issue #2260).
 */

import { ref, computed } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import appConfig from '@/config/AppConfig.js'
import { createLogger } from '@/utils/debugUtils'
import type {
  UseCodeIntelAnalysisDeps,
  CodeSmellsReportData,
  CodeHealthScoreData,
} from './codeIntelTypes'

const logger = createLogger('useCodeSmellAnalysis')

export function useCodeSmellAnalysis(deps: UseCodeIntelAnalysisDeps) {
  const { rootPath, t, notify } = deps

  const codeSmellsReport = ref<CodeSmellsReportData | null>(null)
  const codeHealthScore = ref<CodeHealthScoreData | null>(null)
  const analyzingCodeSmells = ref(false)
  const codeSmellsAnalysisType = ref('')
  const exportingReport = ref(false)

  const codeSmellsProgressTitle = computed(() => {
    return codeSmellsAnalysisType.value === 'health'
      ? t('analytics.codebase.progress.calculatingHealth')
      : t('analytics.codebase.progress.analyzingSmells')
  })

  const runCodeSmellAnalysis = async () => {
    const startTime = Date.now()
    codeSmellsAnalysisType.value = 'smells'
    const analysisPath = rootPath.value
    if (analysisPath.includes('/data/code-sources/')) {
      notify(
        t('analytics.codebase.notify.codeIntelLocalPathRequired'),
        'warning',
      )
      return
    }
    analyzingCodeSmells.value = true
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const response = await fetchWithAuth(
        `${backendUrl}/api/code-intelligence/analyze`,
        {
          method: 'POST',
          headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            path: analysisPath,
            exclude_dirs: [
              'node_modules',
              '.venv',
              '__pycache__',
              '.git',
              'archives',
            ],
            min_severity: 'low',
          }),
        },
      )
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`Status ${response.status}: ${errorText}`)
      }
      const data = await response.json()
      const responseTime = Date.now() - startTime
      codeSmellsReport.value = data.report
      const totalIssues = data.report?.anti_patterns?.length || 0
      const filesAnalyzed = data.report?.total_files || 0
      notify(
        t('analytics.codebase.notify.codeSmellsFound', {
          count: totalIssues,
          files: filesAnalyzed,
          time: responseTime,
        }),
        totalIssues > 0 ? 'warning' : 'success',
      )
    } catch (error: unknown) {
      const responseTime = Date.now() - startTime
      const errorMessage =
        error instanceof Error ? error.message : String(error)
      logger.error('Code smell analysis failed:', error)
      notify(
        t('analytics.codebase.notify.codeSmellsFailed', {
          error: errorMessage,
          time: responseTime,
        }),
        'error',
      )
    } finally {
      analyzingCodeSmells.value = false
    }
  }

  const getCodeHealthScore = async () => {
    const startTime = Date.now()
    codeSmellsAnalysisType.value = 'health'
    const analysisPath = rootPath.value
    if (analysisPath.includes('/data/code-sources/')) {
      notify(
        t('analytics.codebase.notify.healthScoreLocalPathRequired'),
        'warning',
      )
      return
    }
    analyzingCodeSmells.value = true
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const healthEndpoint = `${backendUrl}/api/code-intelligence/health-score?path=${encodeURIComponent(analysisPath)}`
      const response = await fetchWithAuth(healthEndpoint, {
        method: 'GET',
        headers: { Accept: 'application/json' },
      })
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`Status ${response.status}: ${errorText}`)
      }
      const data = await response.json()
      const responseTime = Date.now() - startTime
      codeHealthScore.value = data
      const score = data.health_score || 0
      const grade = data.grade || 'N/A'
      const issues = data.total_issues || 0
      notify(
        t('analytics.codebase.notify.healthScoreResult', {
          score,
          grade,
          issues,
          time: responseTime,
        }),
        score >= 70 ? 'success' : 'warning',
      )
    } catch (error: unknown) {
      const responseTime = Date.now() - startTime
      const errorMessage =
        error instanceof Error ? error.message : String(error)
      logger.error('Health score failed:', error)
      notify(
        t('analytics.codebase.notify.healthScoreFailed', {
          error: errorMessage,
          time: responseTime,
        }),
        'error',
      )
    } finally {
      analyzingCodeSmells.value = false
    }
  }

  return {
    codeSmellsReport,
    codeHealthScore,
    analyzingCodeSmells,
    codeSmellsAnalysisType,
    codeSmellsProgressTitle,
    exportingReport,
    runCodeSmellAnalysis,
    getCodeHealthScore,
  }
}
