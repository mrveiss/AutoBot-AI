/**
 * Composable for codebase analytics export functionality.
 * Extracts report generation and section export from CodebaseAnalytics.vue (#1588).
 *
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 */
import type { Ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('CodebaseExport')

// Re-export the section type for consumers
export type SectionType =
  | 'bug-prediction' | 'code-smells' | 'problems' | 'duplicates'
  | 'declarations' | 'api-endpoints' | 'cross-language' | 'config-duplicates'
  | 'code-intelligence' | 'environment' | 'statistics' | 'ownership'

interface OwnershipExportData {
  summary: {
    total_files: number
    total_contributors: number
    knowledge_gaps_count: number
    critical_gaps: number
  }
  metrics: {
    overall_bus_factor: number
    ownership_concentration: number
    team_coverage: number
  }
  expertise_scores: Array<{
    author_name: string
    total_lines: number
    overall_score: number
  }>
  knowledge_gaps: Array<{
    risk_level: string
    area: string
    description: string
  }>
}

interface EnvExportData {
  total_in_export?: number
  total_in_analysis?: number
  total_hardcoded_values?: number
  high_priority_count?: number
  categories?: Record<string, number>
  hardcoded_values?: Array<{
    type: string
    severity: string
    value: string
    file?: string
    line?: number
    variable_name?: string
    suggested_env_var?: string
    context?: string
    current_usage?: string
  }>
  recommendations?: Array<{
    priority?: string
    description?: string
    env_var_name?: string
  }>
}

// --- Per-section markdown generators (#1588: Extract Method) ---

function _mdHeader(section: SectionType): string {
  const title = section.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
  return `# ${title} Report\n\n**Generated:** ${new Date().toISOString()}\n\n`
}

function _generateBugPredictionMd(data: unknown): string {
  const bp = data as { total_files?: number; high_risk_count?: number; files?: Array<{ file_path: string; risk_score: number; risk_level: string }> }
  let md = `## Summary\n\n`
  md += `- **Total Files Analyzed:** ${bp.total_files || 0}\n`
  md += `- **High Risk Files:** ${bp.high_risk_count || 0}\n\n`
  if (bp.files && bp.files.length > 0) {
    md += `## Files by Risk\n\n| File | Risk Score | Risk Level |\n|------|------------|------------|\n`
    bp.files.forEach(f => { md += `| ${f.file_path} | ${f.risk_score} | ${f.risk_level} |\n` })
  }
  return md
}

function _generateCodeSmellsMd(data: unknown): string {
  const cs = data as { summary?: { total_smells: number }; smells_by_severity?: Record<string, number> }
  let md = `## Summary\n\n- **Total Code Smells:** ${cs.summary?.total_smells || 0}\n\n`
  if (cs.smells_by_severity) {
    md += `## By Severity\n\n`
    Object.entries(cs.smells_by_severity).forEach(([severity, count]) => { md += `- **${severity}:** ${count}\n` })
  }
  return md
}

function _generateProblemsMd(data: unknown): string {
  const probs = data as Array<{ file_path: string; severity: string; message?: string; description?: string; line?: number; line_number?: number; problem_type?: string }>
  let md = `## Total Problems: ${probs.length}\n\n`
  if (probs.length > 0) {
    md += `| File | Severity | Line | Message |\n|------|----------|------|----------|\n`
    probs.forEach(p => {
      const lineNum = p.line || p.line_number || '-'
      const msg = p.message || p.description || ''
      md += `| ${p.file_path || 'unknown'} | ${p.severity || 'unknown'} | ${lineNum} | ${msg} |\n`
    })
  }
  return md
}

function _generateStatisticsMd(data: unknown): string {
  const stats = data as Record<string, unknown>
  const s = (stats as { stats?: Record<string, unknown> }).stats || stats
  const r = s as Record<string, number>
  let md = `## Codebase Statistics\n\n| Metric | Value |\n|--------|-------|\n`
  md += `| Total Files | ${r.total_files?.toLocaleString() || 0} |\n`
  md += `| Python Files | ${r.python_files?.toLocaleString() || 0} |\n`
  md += `| TypeScript Files | ${r.typescript_files?.toLocaleString() || 0} |\n`
  md += `| Vue Files | ${r.vue_files?.toLocaleString() || 0} |\n`
  md += `| Total Lines | ${r.total_lines?.toLocaleString() || 0} |\n`
  md += `| Total Functions | ${r.total_functions?.toLocaleString() || 0} |\n`
  md += `| Total Classes | ${r.total_classes?.toLocaleString() || 0} |\n`
  return md
}

function _generateDuplicatesMd(data: unknown): string {
  const dups = data as Array<{ file1: string; file2: string; similarity: number; lines: number }>
  let md = `## Duplicate Code Analysis\n\n**Total Duplicate Pairs Found:** ${dups.length}\n\n`
  if (dups.length > 0) {
    md += `| File 1 | File 2 | Similarity | Lines |\n|--------|--------|------------|-------|\n`
    dups.forEach(d => { md += `| ${d.file1} | ${d.file2} | ${(d.similarity * 100).toFixed(1)}% | ${d.lines} |\n` })
  }
  return md
}

function _generateDeclarationsMd(data: unknown): string {
  const decls = data as Array<{ file: string; name: string; type: string; line: number }>
  let md = `## Code Declarations\n\n**Total Declarations:** ${decls.length}\n\n`
  if (decls.length > 0) {
    md += `| File | Name | Type | Line |\n|------|------|------|------|\n`
    decls.forEach(d => { md += `| ${d.file} | ${d.name} | ${d.type} | ${d.line} |\n` })
  }
  return md
}

function _generateApiEndpointsMd(data: unknown): string {
  const api = data as { total_endpoints?: number; endpoints?: Array<{ path: string; method: string; file: string }> }
  let md = `## API Endpoint Analysis\n\n**Total Endpoints:** ${api.total_endpoints || api.endpoints?.length || 0}\n\n`
  if (api.endpoints && api.endpoints.length > 0) {
    md += `| Method | Path | File |\n|--------|------|------|\n`
    api.endpoints.forEach(e => { md += `| ${e.method} | ${e.path} | ${e.file} |\n` })
  }
  return md
}

function _generateCrossLanguageMd(data: unknown): string {
  const cl = data as { dto_mismatches?: unknown[]; api_mismatches?: unknown[]; validation_duplications?: unknown[] }
  let md = `## Cross-Language Pattern Analysis\n\n| Category | Count |\n|----------|-------|\n`
  md += `| DTO Mismatches | ${cl.dto_mismatches?.length || 0} |\n`
  md += `| API Mismatches | ${cl.api_mismatches?.length || 0} |\n`
  md += `| Validation Duplications | ${cl.validation_duplications?.length || 0} |\n\n`
  md += `### Details\n\n` + '```json\n' + JSON.stringify(data, null, 2) + '\n```\n'
  return md
}

function _generateConfigDuplicatesMd(data: unknown): string {
  const cfg = data as { duplicates?: Array<{ key: string; files: string[]; count: number }> }
  let md = `## Configuration Duplicates\n\n**Total Duplicates:** ${cfg.duplicates?.length || 0}\n\n`
  if (cfg.duplicates && cfg.duplicates.length > 0) {
    md += `| Config Key | Files | Occurrences |\n|------------|-------|-------------|\n`
    cfg.duplicates.forEach(d => { md += `| ${d.key} | ${d.files.join(', ')} | ${d.count} |\n` })
  }
  return md
}

function _generateEnvironmentMd(data: unknown): string {
  // Issue #631, #706: Handle export format with hardcoded_values
  const env = data as EnvExportData
  let md = `## Environment Analysis Report\n\n### Summary\n\n`
  const totalItems = env.total_in_export ?? env.total_hardcoded_values ?? 0
  const totalAnalysis = env.total_in_analysis ?? env.total_hardcoded_values ?? 0
  md += `- **Total Items Exported:** ${totalItems.toLocaleString()}\n`
  if (env.total_in_analysis && env.total_in_export !== env.total_in_analysis) {
    md += `- **Total in Analysis:** ${totalAnalysis.toLocaleString()}\n`
  }
  if (env.high_priority_count !== undefined) {
    md += `- **High Priority Items:** ${env.high_priority_count}\n`
  }
  md += `\n`
  md += _generateEnvCategories(env)
  md += _generateEnvHardcodedValues(env)
  md += _generateEnvRecommendations(env)
  return md
}

function _generateEnvCategories(env: EnvExportData): string {
  if (!env.categories || Object.keys(env.categories).length === 0) return ''
  let md = `### Categories\n\n| Category | Count |\n|----------|-------|\n`
  Object.entries(env.categories).forEach(([cat, count]) => { md += `| ${cat} | ${count} |\n` })
  return md + `\n`
}

function _generateEnvHardcodedValues(env: EnvExportData): string {
  if (!env.hardcoded_values || env.hardcoded_values.length === 0) return ''
  const byPriority = { high: [], medium: [], low: [] } as Record<string, typeof env.hardcoded_values>
  env.hardcoded_values.forEach(v => {
    const sev = (v.severity || 'low').toLowerCase()
    if (!byPriority[sev]) byPriority[sev] = []
    byPriority[sev].push(v)
  })
  let md = ''
  const levels = [
    { key: 'high', emoji: '🔴' },
    { key: 'medium', emoji: '🟡' },
    { key: 'low', emoji: '🟢' },
  ]
  for (const { key, emoji } of levels) {
    if (byPriority[key].length > 0) {
      md += `### ${emoji} ${key.charAt(0).toUpperCase() + key.slice(1)} Priority (${byPriority[key].length})\n\n`
      md += `| Type | Value | File | Line |\n|------|-------|------|------|\n`
      byPriority[key].forEach(v => {
        const val = String(v.value).substring(0, 50) + (String(v.value).length > 50 ? '...' : '')
        md += `| ${v.type} | \`${val}\` | ${v.file || '-'} | ${v.line || '-'} |\n`
      })
      md += `\n`
    }
  }
  return md
}

function _generateEnvRecommendations(env: EnvExportData): string {
  if (!env.recommendations || env.recommendations.length === 0) return ''
  let md = `### Recommendations\n\n`
  env.recommendations.forEach((rec, i) => {
    md += `${i + 1}. **[${rec.priority || 'medium'}]** ${rec.description || ''}`
    if (rec.env_var_name) md += ` → \`${rec.env_var_name}\``
    md += `\n`
  })
  return md
}

function _generateCodeIntelligenceMd(data: unknown): string {
  const ci = data as { security_score?: number; performance_score?: number; maintainability_score?: number }
  let md = `## Code Intelligence Scores\n\n| Metric | Score |\n|--------|-------|\n`
  md += `| Security | ${ci.security_score || 'N/A'} |\n`
  md += `| Performance | ${ci.performance_score || 'N/A'} |\n`
  md += `| Maintainability | ${ci.maintainability_score || 'N/A'} |\n`
  return md
}

function _generateOwnershipMd(data: unknown): string {
  const own = data as OwnershipExportData
  let md = `## Code Ownership & Expertise Map\n\n### Summary\n\n`
  md += `- **Total Files Analyzed:** ${own.summary.total_files}\n`
  md += `- **Total Contributors:** ${own.summary.total_contributors}\n`
  md += `- **Knowledge Gaps:** ${own.summary.knowledge_gaps_count}\n`
  md += `- **Critical Gaps:** ${own.summary.critical_gaps}\n\n`
  md += `### Metrics\n\n`
  md += `- **Bus Factor:** ${own.metrics.overall_bus_factor}\n`
  md += `- **Ownership Concentration:** ${own.metrics.ownership_concentration}%\n`
  md += `- **Team Coverage:** ${own.metrics.team_coverage}%\n\n`
  md += _generateOwnershipContributors(own)
  md += _generateOwnershipGaps(own)
  return md
}

function _generateOwnershipContributors(own: OwnershipExportData): string {
  if (own.expertise_scores.length === 0) return ''
  let md = `### Top Contributors\n\n| Rank | Name | Lines | Score |\n|------|------|-------|-------|\n`
  own.expertise_scores.slice(0, 10).forEach((e, i) => {
    md += `| ${i + 1} | ${e.author_name} | ${e.total_lines.toLocaleString()} | ${e.overall_score.toFixed(0)} |\n`
  })
  return md + `\n`
}

function _generateOwnershipGaps(own: OwnershipExportData): string {
  if (own.knowledge_gaps.length === 0) return ''
  let md = `### Knowledge Gaps\n\n`
  own.knowledge_gaps.slice(0, 10).forEach(g => {
    md += `- **[${g.risk_level.toUpperCase()}]** ${g.area}: ${g.description}\n`
  })
  return md
}

// Section markdown generator dispatch map
const sectionGenerators: Record<SectionType, (data: unknown) => string> = {
  'bug-prediction': _generateBugPredictionMd,
  'code-smells': _generateCodeSmellsMd,
  'problems': _generateProblemsMd,
  'statistics': _generateStatisticsMd,
  'duplicates': _generateDuplicatesMd,
  'declarations': _generateDeclarationsMd,
  'api-endpoints': _generateApiEndpointsMd,
  'cross-language': _generateCrossLanguageMd,
  'config-duplicates': _generateConfigDuplicatesMd,
  'environment': _generateEnvironmentMd,
  'code-intelligence': _generateCodeIntelligenceMd,
  'ownership': _generateOwnershipMd,
}

/**
 * Generate markdown report for a specific analysis section.
 * Dispatches to per-section generators (#1588: Extract Method).
 */
export function generateSectionMarkdown(section: SectionType, data: unknown): string {
  const generator = sectionGenerators[section]
  if (generator) {
    return _mdHeader(section) + generator(data)
  }
  // Generic JSON dump for unknown sections
  return _mdHeader(section) + '```json\n' + JSON.stringify(data, null, 2) + '\n```\n'
}

/**
 * Download content as a file via browser download.
 */
function _downloadFile(content: string, filename: string, mimeType: string): void {
  const blob = new Blob([content], { type: mimeType })
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

/**
 * Composable providing codebase export functionality.
 * @param deps - Reactive state and utilities from the parent component
 */
export function useCodebaseExport(deps: {
  sectionData: Record<SectionType, Ref<unknown>>
  exportingReport: Ref<boolean>
  progressStatus: Ref<string>
  fetchWithAuth: typeof fetch
  getBackendUrl: () => Promise<string>
  notify: (msg: string, type: 'info' | 'success' | 'warning' | 'error') => void
  t: (key: string, params?: Record<string, unknown>) => string
}) {
  /**
   * Export full codebase analysis report (quick or full).
   */
  const exportReport = async (quick: boolean = true): Promise<void> => {
    deps.exportingReport.value = true
    deps.progressStatus.value = quick
      ? deps.t('analytics.codebase.status.generatingQuickReport')
      : deps.t('analytics.codebase.status.generatingFullReport')

    try {
      const backendUrl = await deps.getBackendUrl()
      const url = `${backendUrl}/api/analytics/codebase/report?format=markdown&quick=${quick}`
      const response = await deps.fetchWithAuth(url, {
        method: 'GET',
        headers: { 'Accept': 'text/markdown' },
      })
      if (!response.ok) {
        throw new Error(`Status ${response.status}: ${await response.text()}`)
      }
      const reportContent = await response.text()
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
      const reportType = quick ? 'quick' : 'full'
      _downloadFile(reportContent, `code-analysis-report-${reportType}-${timestamp}.md`, 'text/markdown;charset=utf-8')
      deps.notify(deps.t('analytics.codebase.notify.reportExported'), 'success')
      deps.progressStatus.value = deps.t('analytics.codebase.status.reportExported')
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : String(error)
      logger.error('Report export failed:', error)
      deps.notify(deps.t('analytics.codebase.notify.reportExportFailed', { error: msg }), 'error')
      deps.progressStatus.value = deps.t('analytics.codebase.status.reportExportFailed')
    } finally {
      deps.exportingReport.value = false
    }
  }

  /**
   * Fetch environment export data with fallback to cached display data.
   * Issue #631: Uses dedicated export endpoint to avoid truncation.
   */
  const _fetchEnvironmentExportData = async (
    cachedData: unknown,
  ): Promise<unknown> => {
    try {
      const backendUrl = await deps.getBackendUrl()
      const response = await deps.fetchWithAuth(
        `${backendUrl}/api/analytics/codebase/env-analysis/export`,
        { method: 'GET', headers: { 'Content-Type': 'application/json' } },
      )
      if (response.ok) {
        const data = await response.json()
        logger.info('Environment export: fetched full data', {
          total_in_export: (data as { total_in_export?: number }).total_in_export,
          total_in_analysis: (data as { total_in_analysis?: number }).total_in_analysis,
        })
        return data
      }
      logger.warn('Environment export: endpoint failed, using display data')
      deps.notify(deps.t('analytics.codebase.notify.usingCachedData'), 'warning')
      return cachedData
    } catch (err) {
      logger.warn('Environment export: fetch failed, using display data', err)
      deps.notify(deps.t('analytics.codebase.notify.exportEndpointUnavailable'), 'warning')
      return cachedData
    }
  }

  /**
   * Export individual section data as MD or JSON. Issue #609.
   */
  const exportSection = async (
    section: SectionType,
    format: 'md' | 'json' = 'md',
  ): Promise<void> => {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)

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
