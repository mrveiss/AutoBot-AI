// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useCodeSmellAnalysis
 *
 * Code smell detection and health score calculation.
 * Extracted from useCodeIntelAnalysis (Issue #2260).
 * Routed through useAnalyticsEndpoint<T> (Issue #5153 wave 2).
 *
 * The two backing endpoints live under `/api/code-intelligence/*` and are
 * NOT source-scoped (they take the repo root path directly), so both
 * endpoints opt out of source scoping via `scopeToSource: false`.
 */

import { ref, computed } from 'vue'
import type {
  UseCodeIntelAnalysisDeps,
  CodeSmellsReportData,
  CodeHealthScoreData,
} from './codeIntelTypes'
import { useAnalyticsEndpoint } from './useAnalyticsEndpoint'

interface AnalyzeResponse {
  report?: CodeSmellsReportData
}

const LOCAL_PATH_MARKER = '/data/code-sources/'

export function useCodeSmellAnalysis(deps: UseCodeIntelAnalysisDeps) {
  const { rootPath, t, notify } = deps
  // Never source-scoped: /api/code-intelligence/* takes the raw repo path.
  const withSourceId = (url: string) => url

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

  // Times an async load, toggles the shared analyzing flag, and fans out
  // to per-endpoint success / failure toasts with the elapsed duration.
  const notifyTimed = async (
    fn: () => Promise<void>,
    onFinish: (responseTimeMs: number) => void,
    onFail: (responseTimeMs: number, message: string) => void,
  ): Promise<void> => {
    const startTime = Date.now()
    analyzingCodeSmells.value = true
    try {
      await fn()
      onFinish(Date.now() - startTime)
    } catch (err: unknown) {
      const responseTime = Date.now() - startTime
      const message = err instanceof Error ? err.message : String(err)
      onFail(responseTime, message)
    } finally {
      analyzingCodeSmells.value = false
    }
  }

  const smellsEndpoint = useAnalyticsEndpoint<
    AnalyzeResponse,
    CodeSmellsReportData
  >(
    {
      path: '/api/code-intelligence/analyze',
      method: 'POST',
      scopeToSource: false,
      body: () => ({
        path: rootPath.value,
        exclude_dirs: [
          'node_modules',
          '.venv',
          '__pycache__',
          '.git',
          'archives',
        ],
        min_severity: 'low',
      }),
      pickData: (raw) => raw.report ?? null,
      onSuccess: (report) => {
        codeSmellsReport.value = report
      },
      // Preserve original behavior: a no-report response clears stale state.
      onNoData: () => {
        codeSmellsReport.value = null
      },
      label: 'Code smell analysis',
    },
    { withSourceId },
  )

  const healthEndpoint = useAnalyticsEndpoint<
    CodeHealthScoreData,
    CodeHealthScoreData
  >(
    {
      path: '/api/code-intelligence/health-score',
      scopeToSource: false,
      pickData: (raw) => raw,
      onSuccess: (data) => {
        codeHealthScore.value = data
      },
      onNoData: () => {
        codeHealthScore.value = null
      },
      label: 'Health score',
    },
    { withSourceId },
  )

  const runCodeSmellAnalysis = async () => {
    codeSmellsAnalysisType.value = 'smells'
    if (rootPath.value.includes(LOCAL_PATH_MARKER)) {
      notify(
        t('analytics.codebase.notify.codeIntelLocalPathRequired'),
        'warning',
      )
      return
    }
    await notifyTimed(
      async () => {
        await smellsEndpoint.load()
        if (smellsEndpoint.error.value) {
          throw new Error(smellsEndpoint.error.value)
        }
      },
      (responseTime) => {
        // CodeSmellsReportData is index-signatured; narrow the fields we
        // actually read from the /analyze backend contract.
        const report = codeSmellsReport.value as
          | ({ anti_patterns?: unknown[]; total_files?: number } & CodeSmellsReportData)
          | null
        const totalIssues = Array.isArray(report?.anti_patterns)
          ? report.anti_patterns.length
          : 0
        const filesAnalyzed = report?.total_files ?? 0
        notify(
          t('analytics.codebase.notify.codeSmellsFound', {
            count: totalIssues,
            files: filesAnalyzed,
            time: responseTime,
          }),
          totalIssues > 0 ? 'warning' : 'success',
        )
      },
      (responseTime, message) => {
        notify(
          t('analytics.codebase.notify.codeSmellsFailed', {
            error: message,
            time: responseTime,
          }),
          'error',
        )
      },
    )
  }

  const getCodeHealthScore = async () => {
    codeSmellsAnalysisType.value = 'health'
    if (rootPath.value.includes(LOCAL_PATH_MARKER)) {
      notify(
        t('analytics.codebase.notify.healthScoreLocalPathRequired'),
        'warning',
      )
      return
    }
    await notifyTimed(
      async () => {
        await healthEndpoint.load({ path: rootPath.value })
        if (healthEndpoint.error.value) {
          throw new Error(healthEndpoint.error.value)
        }
      },
      (responseTime) => {
        const h = codeHealthScore.value as
          | (CodeHealthScoreData & { total_issues?: number })
          | null
        const score = h?.health_score ?? 0
        const grade = h?.grade ?? 'N/A'
        const issues = h?.total_issues ?? 0
        notify(
          t('analytics.codebase.notify.healthScoreResult', {
            score,
            grade,
            issues,
            time: responseTime,
          }),
          score >= 70 ? 'success' : 'warning',
        )
      },
      (responseTime, message) => {
        notify(
          t('analytics.codebase.notify.healthScoreFailed', {
            error: message,
            time: responseTime,
          }),
          'error',
        )
      },
    )
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
