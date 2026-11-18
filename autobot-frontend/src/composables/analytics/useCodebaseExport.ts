// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Composable for codebase analytics export functionality.
 * Extracts report generation and section export from CodebaseAnalytics.vue (#1588).
 *
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 */
import { saveTextFile, isoTimestampStamp } from '@autobot/ui'
import type { Ref } from 'vue'
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import { createLogger } from '@/utils/debugUtils'
import { generateSectionMarkdown, type SectionType } from './sectionMarkdown'

const logger = createLogger('CodebaseExport')

export type { SectionType }
export { generateSectionMarkdown }

/** Download content as a file: the kit's one save path (#20770). */
const _downloadFile = saveTextFile

/**
 * Composable providing codebase export functionality.
 * @param deps - Reactive state and utilities from the parent component
 */
export function useCodebaseExport(deps: {
  sectionData: Record<SectionType, Ref<unknown>>
  exportingReport: Ref<boolean>
  progressStatus: Ref<string>
  /**
   * URL wrapper that appends `?source_id=<id>` for per-project scoping.
   * #5266: previously missing \u2014 both `/report` and `/env-analysis/export`
   * are source-scoped at the backend but the frontend was dropping the
   * scope, silently falling back to `get_default_source_id()` (same
   * bug class as #5111).
   */
  withSourceId: (url: string) => string
  notify: (msg: string, type: 'info' | 'success' | 'warning' | 'error') => void
  t: (key: string, params?: Record<string, unknown>) => string
}) {
  /**
   * Export full codebase analysis report (quick or full).
   *
   * #5388: routed through `useFetchEndpoint` via the `parseResponse`
   * hook (#5276) so the `text/markdown` response goes through the
   * same loading/error/source-scoping pipeline as every other
   * analytics fetcher. The old hand-rolled try/catch + manual
   * exportingReport flag + status-string juggling collapses to hooks.
   */
  // #5455: per-request context type for the export endpoint, threaded
  // through onSuccess via the context hook (#5457). Replaces the prior
  // module-scope `_currentReportType` let that raced on concurrent calls.
  type ReportContext = { reportType: 'quick' | 'full' }

  const reportEndpoint = useFetchEndpoint<string, string, ReportContext>(
    {
      path: '/api/analytics/codebase/report',
      scopeToSource: true,
      requireSource: true,
      parseResponse: async (r) => await r.text(),
      pickData: (raw) => raw,
      onSuccess: (content, _raw, ctx) => {
        const timestamp = isoTimestampStamp()
        _downloadFile(
          content,
          `code-analysis-report-${ctx.reportType}-${timestamp}.md`,
          'text/markdown;charset=utf-8',
        )
        deps.notify(deps.t('analytics.codebase.notify.reportExported'), 'success')
        deps.progressStatus.value = deps.t(
          'analytics.codebase.status.reportExported',
        )
      },
      onError: (msg) => {
        deps.notify(
          deps.t('analytics.codebase.notify.reportExportFailed', { error: msg }),
          'error',
        )
        deps.progressStatus.value = deps.t(
          'analytics.codebase.status.reportExportFailed',
        )
      },
      onResponse: async (response) => {
        // Preserve the original "Status N: <body-text>" error shape.
        const text = await response.text().catch(() => '')
        return `Status ${response.status}${text ? `: ${text}` : ''}`
      },
      label: 'Report export',
    },
    { withSourceId: deps.withSourceId },
  )

  // The Vue template binds to `deps.exportingReport` (component-owned).
  // Keep the bridge so consumers see the single flag they already wire.
  const exportReport = async (quick: boolean = true): Promise<void> => {
    const reportType: 'quick' | 'full' = quick ? 'quick' : 'full'
    deps.exportingReport.value = true
    deps.progressStatus.value = quick
      ? deps.t('analytics.codebase.status.generatingQuickReport')
      : deps.t('analytics.codebase.status.generatingFullReport')
    try {
      await reportEndpoint.load(
        { format: 'markdown', quick: String(quick) },
        { reportType },
      )
    } finally {
      deps.exportingReport.value = false
    }
  }

  /**
   * Fetch environment export data with fallback to cached display data.
   *
   * Issue #631: Uses dedicated export endpoint to avoid truncation.
   * Issue #5389: routed through useFetchEndpoint's fallbackData hook.
   * The composable's old strict error model required bespoke
   * try/catch + notify branches. Now:
   *   - onSuccess logs total_in_export / total_in_analysis.
   *   - onError fires the "using cached data" warning toast.
   *   - fallbackData returns the cached snapshot on failure, keeping
   *     error.value empty so downstream export code proceeds with
   *     the stale data rather than aborting.
   */
  const _fetchEnvironmentExportData = async (
    cachedData: unknown,
  ): Promise<unknown> => {
    const endpoint = useFetchEndpoint<unknown, unknown>(
      {
        path: '/api/analytics/codebase/env-analysis/export',
        scopeToSource: true,
        requireSource: true,
        pickData: (raw) => raw,
        onSuccess: (data) => {
          logger.info('Environment export: fetched full data', {
            total_in_export: (data as { total_in_export?: number }).total_in_export,
            total_in_analysis: (data as { total_in_analysis?: number }).total_in_analysis,
          })
        },
        onError: (_msg, err) => {
          logger.warn('Environment export: using display data', err)
          deps.notify(
            deps.t('analytics.codebase.notify.exportEndpointUnavailable'),
            'warning',
          )
        },
        fallbackData: cachedData,
        label: 'Environment export',
      },
      { withSourceId: deps.withSourceId },
    )
    await endpoint.load()
    return endpoint.data.value
  }

  /**
   * Export individual section data as MD or JSON. Issue #609.
   */
  const exportSection = async (
    section: SectionType,
    format: 'md' | 'json' = 'md',
  ): Promise<void> => {
    const timestamp = isoTimestampStamp()

    // Resolve section data (environment uses a special async fetch)
    let data: unknown
    if (section === 'environment') {
      data = await _fetchEnvironmentExportData(deps.sectionData[section]?.value)
    } else {
      data = deps.sectionData[section]?.value
    }

    if (!data) {
      deps.notify(deps.t('analytics.codebase.notify.noDataAvailable', { section }), 'warning')
      return
    }

    // Build filename from section type
    const nameMap: Record<SectionType, string> = {
      'bug-prediction': 'bug-prediction', 'code-smells': 'code-smells',
      'problems': 'problems-report', 'duplicates': 'duplicate-analysis',
      'declarations': 'declarations', 'api-endpoints': 'api-endpoints',
      'cross-language': 'cross-language', 'config-duplicates': 'config-duplicates',
      'code-intelligence': 'code-intelligence-scores', 'environment': 'environment-analysis',
      'statistics': 'codebase-statistics', 'ownership': 'ownership-analysis',
      'hardcodes': 'hardcoded-values',
    }
    const baseName = nameMap[section] || section
    const ext = format === 'json' ? '.json' : '.md'
    const filename = `${baseName}-${timestamp}${ext}`

    const content = format === 'json'
      ? JSON.stringify(data, null, 2)
      : generateSectionMarkdown(section, data)

    const mimeType = format === 'json' ? 'application/json' : 'text/markdown'
    _downloadFile(content, filename, mimeType)
    deps.notify(deps.t('analytics.codebase.notify.sectionExported', { section, format: format.toUpperCase() }), 'success')
  }

  return { exportReport, exportSection, generateSectionMarkdown }
}
