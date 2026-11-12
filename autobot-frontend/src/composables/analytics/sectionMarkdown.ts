// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Markdown generators for the per-section analytics export (#609, #1588).
 *
 * Every generator is typed against the data type the panel for that section
 * renders (`SectionDataMap`), so an export that reads a field the panel's data
 * does not carry fails type-checking instead of printing "undefined" (#20492).
 *
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 */
import type { HardcodedValue, Problem, DuplicateCode, Declaration } from '@/composables/analytics/analyticsTypes'
import type {
  BugPredictionResult,
  ApiEndpointAnalysisResult,
  ConfigDuplicatesResult,
  CrossLanguageAnalysisResult,
  CodeHealthScoreData,
  ApiEndpointInfo,
} from '@/composables/analytics/codeIntelTypes'
import type { SmellsExport } from '@/composables/analytics/codeSmellSummary'

export type SectionType = keyof SectionDataMap

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
  hardcoded_values?: HardcodedValue[]
  recommendations?: Array<{
    priority?: string
    description?: string
    env_var_name?: string
  }>
}

/**
 * What each section's export reads: the same value the section's panel renders
 * (`CodebaseAnalytics.vue` wires each `sectionData` ref to the panel's source).
 */
export interface SectionDataMap {
  'bug-prediction': BugPredictionResult
  'code-smells': SmellsExport
  'problems': Problem[]
  'duplicates': DuplicateCode[]
  'declarations': Declaration[]
  'api-endpoints': ApiEndpointAnalysisResult
  'cross-language': CrossLanguageAnalysisResult
  'config-duplicates': ConfigDuplicatesResult
  'code-intelligence': CodeHealthScoreData
  'environment': EnvExportData
  'statistics': Record<string, unknown>
  'ownership': OwnershipExportData
  'hardcodes': HardcodedValue[]
}

// --- Per-section markdown generators (#1588: Extract Method) ---

function _mdHeader(section: SectionType): string {
  const title = section.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
  return `# ${title} Report\n\n**Generated:** ${new Date().toISOString()}\n\n`
}

function _generateBugPredictionMd(bp: SectionDataMap['bug-prediction']): string {
  let md = `## Summary\n\n`
  md += `- **Total Files Analyzed:** ${bp.total_files || 0}\n`
  md += `- **High Risk Files:** ${bp.high_risk_count || 0}\n\n`
  if (bp.files && bp.files.length > 0) {
    md += `## Files by Risk\n\n| File | Risk Score | Risk Level |\n|------|------------|------------|\n`
    bp.files.forEach(f => { md += `| ${f.file_path} | ${f.risk_score} | ${f.risk_level} |\n` })
  }
  return md
}

function _generateCodeSmellsMd(cs: SectionDataMap['code-smells']): string {
  let md = `## Summary\n\n- **Total Code Smells:** ${cs.summary?.total_smells || 0}\n\n`
  if (cs.smells_by_severity) {
    md += `## By Severity\n\n`
    Object.entries(cs.smells_by_severity).forEach(([severity, count]) => { md += `- **${severity}:** ${count}\n` })
    md += `\n`
  }
  const smells = cs.smells ?? []
  if (smells.length > 0) {
    md += `## Findings\n\n| File | Severity | Type | Line | Description |\n|------|----------|------|------|-------------|\n`
    smells.forEach(sm => {
      md += `| ${sm.file_path || 'unknown'} | ${sm.severity || 'low'} | ${sm.smell_type || 'unknown'} | ${sm.line_number ?? '-'} | ${sm.description || ''} |\n`
    })
  }
  return md
}

function _generateProblemsMd(probs: SectionDataMap['problems']): string {
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

function _generateStatisticsMd(stats: SectionDataMap['statistics']): string {
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

function _generateDuplicatesMd(dups: SectionDataMap['duplicates']): string {
  let md = `## Duplicate Code Analysis\n\n**Total Duplicate Pairs Found:** ${dups.length}\n\n`
  if (dups.length > 0) {
    md += `| File 1 | File 2 | Similarity | Lines |\n|--------|--------|------------|-------|\n`
    dups.forEach(d => { md += `| ${d.file1} | ${d.file2} | ${(d.similarity * 100).toFixed(1)}% | ${d.lines} |\n` })
  }
  return md
}

function _generateDeclarationsMd(decls: SectionDataMap['declarations']): string {
  let md = `## Code Declarations\n\n**Total Declarations:** ${decls.length}\n\n`
  if (decls.length > 0) {
    md += `| File | Name | Type | Line |\n|------|------|------|------|\n`
    decls.forEach(d => { md += `| ${d.file_path} | ${d.name} | ${d.type} | ${d.line_number ?? d.line ?? '-'} |\n` })
  }
  return md
}

function _generateHardcodesMd(hcs: SectionDataMap['hardcodes']): string {
  // #5277: dedicated markdown for the array form returned by
  // `/api/analytics/codebase/hardcodes` (distinct from env-analysis export).
  // #5311: use canonical `HardcodedValue` instead of inline shape.
  let md = `## Hardcoded Values\n\n**Total Values Found:** ${hcs.length}\n\n`
  if (hcs.length === 0) return md
  const groups: Record<string, typeof hcs> = { high: [], medium: [], low: [] }
  hcs.forEach(h => {
    const sev = (h.severity || 'low').toLowerCase()
    if (sev === 'high' || sev === 'critical') groups.high.push(h)
    else if (sev === 'medium') groups.medium.push(h)
    else groups.low.push(h)
  })
  const levels = [
    { key: 'high', emoji: '🔴' },
    { key: 'medium', emoji: '🟡' },
    { key: 'low', emoji: '🟢' },
  ]
  for (const { key, emoji } of levels) {
    if (groups[key].length === 0) continue
    md += `### ${emoji} ${key.charAt(0).toUpperCase() + key.slice(1)} Severity (${groups[key].length})\n\n`
    md += `| Type | File | Line | Variable | Value | Suggested Env Var |\n`
    md += `|------|------|------|----------|-------|-------------------|\n`
    groups[key].forEach(h => {
      const val = String(h.value).substring(0, 50) + (String(h.value).length > 50 ? '...' : '')
      md += `| ${h.type} | ${h.file} | ${h.line} | ${h.variable_name || '-'} | \`${val}\` | ${h.suggested_env_var ? '`' + h.suggested_env_var + '`' : '-'} |\n`
    })
    md += `\n`
  }
  return md
}

function _endpointRows(heading: string, eps: ApiEndpointInfo[] | undefined): string {
  if (!eps || eps.length === 0) return ''
  let md = `### ${heading} (${eps.length})\n\n| Method | Path | File |\n|--------|------|------|\n`
  eps.forEach(e => { md += `| ${e.method || '-'} | ${e.path} | ${e.file_path || '-'} |\n` })
  return md + `\n`
}

function _generateApiEndpointsMd(api: SectionDataMap['api-endpoints']): string {
  let md = `## API Endpoint Analysis\n\n| Metric | Value |\n|--------|-------|\n`
  md += `| Backend Endpoints | ${api.backend_endpoints || 0} |\n`
  md += `| Frontend Calls | ${api.frontend_calls || 0} |\n`
  md += `| Used Endpoints | ${api.used_endpoints || 0} |\n`
  md += `| Orphaned Endpoints | ${api.orphaned_endpoints || 0} |\n`
  md += `| Missing Endpoints | ${api.missing_endpoints || 0} |\n`
  md += `| Coverage | ${api.coverage_percentage || 0}% |\n\n`
  md += _endpointRows('Orphaned', api.orphaned)
  md += _endpointRows('Missing', api.missing)
  md += _endpointRows('Used', api.used?.flatMap(u => (u.endpoint ? [u.endpoint] : [])))
  return md
}

function _generateCrossLanguageMd(cl: SectionDataMap['cross-language']): string {
  let md = `## Cross-Language Pattern Analysis\n\n| Category | Count |\n|----------|-------|\n`
  md += `| DTO Mismatches | ${cl.dto_mismatches?.length || 0} |\n`
  md += `| API Contract Mismatches | ${cl.api_contract_mismatches?.length || 0} |\n`
  md += `| Validation Duplications | ${cl.validation_duplications?.length || 0} |\n\n`
  md += `### Details\n\n` + '```json\n' + JSON.stringify(cl, null, 2) + '\n```\n'
  return md
}

function _generateConfigDuplicatesMd(cfg: SectionDataMap['config-duplicates']): string {
  const dups = cfg.duplicates ?? []
  let md = `## Configuration Duplicates\n\n**Total Duplicates:** ${dups.length}\n\n`
  if (dups.length > 0) {
    md += `| Value | Locations | Occurrences |\n|-------|-----------|-------------|\n`
    dups.forEach(d => {
      const where = (d.locations ?? []).map(l => `${l.file}:${l.line}`).join(', ')
      md += `| ${d.value} | ${where} | ${d.locations?.length ?? 0} |\n`
    })
  }
  return md
}

function _generateEnvironmentMd(env: SectionDataMap['environment']): string {
  // Issue #631, #706: Handle export format with hardcoded_values
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

function _generateCodeIntelligenceMd(ci: SectionDataMap['code-intelligence']): string {
  // Fields of GET /api/code-intelligence/health-score (api/code_intelligence.py).
  let md = `## Code Intelligence Scores\n\n| Metric | Value |\n|--------|-------|\n`
  md += `| Health Score | ${ci.health_score ?? 'N/A'} |\n`
  md += `| Grade | ${ci.grade || 'N/A'} |\n`
  md += `| Total Issues | ${ci.total_issues ?? 'N/A'} |\n`
  md += `| Files Analyzed | ${ci.files_analyzed ?? 'N/A'} |\n`
  const severities = Object.entries(ci.severity_breakdown ?? {})
  if (severities.length > 0) {
    md += `\n### Severity Breakdown\n\n`
    severities.forEach(([severity, count]) => { md += `- **${severity}:** ${count}\n` })
  }
  return md
}

function _generateOwnershipMd(own: SectionDataMap['ownership']): string {
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
const sectionGenerators: { [S in SectionType]: (data: SectionDataMap[S]) => string } = {
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
  'hardcodes': _generateHardcodesMd,
}

/**
 * Generate markdown report for a specific analysis section.
 * Dispatches to per-section generators (#1588: Extract Method).
 */
export function generateSectionMarkdown(section: SectionType, data: unknown): string {
  // The one boundary cast: callers hold `Ref<unknown>`; each generator is typed to its section.
  const generator = sectionGenerators[section] as ((data: unknown) => string) | undefined
  if (generator) {
    return _mdHeader(section) + generator(data)
  }
  // Generic JSON dump for unknown sections
  return _mdHeader(section) + '```json\n' + JSON.stringify(data, null, 2) + '\n```\n'
}
