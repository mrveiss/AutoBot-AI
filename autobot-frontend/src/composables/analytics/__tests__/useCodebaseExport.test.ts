// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Issue #20492: every section's export must carry what its panel shows.
 *
 * Two walks, both over ALL sections so a new section cannot regress:
 *  1. behaviour: with data loaded, the MD and the JSON export of each section
 *     contain that data (a marker only the displayed rows carry), never
 *     "undefined", never the "No data available" refusal;
 *  2. wiring: in CodebaseAnalytics.vue the ref each section exports from is the
 *     ref its panel is bound to (or a documented projection of it).
 */
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, type Ref } from 'vue'

const saved = vi.hoisted(() => vi.fn())

vi.mock('@autobot/ui', () => ({
  saveTextFile: (...args: unknown[]) => saved(...args),
  isoTimestampStamp: () => 'TS',
}))
vi.mock('@/composables/api/useFetchEndpoint', () => ({
  // The environment export falls back to the cached display data (fallbackData).
  useFetchEndpoint: (cfg: { fallbackData?: unknown }) => ({
    load: vi.fn(async () => undefined),
    data: { value: cfg.fallbackData },
  }),
}))

import { useCodebaseExport, type SectionType } from '../useCodebaseExport'
import { buildSmellsExport } from '../codeSmellSummary'

const smellsPanelList = [
  {
    severity: 'high',
    description: 'mark smell description',
    file_path: 'src/mark-smell.py',
    line_number: 42,
    smell_type: 'long_function',
  },
]

/** The data each section's panel holds once loaded. */
const DATA: Record<SectionType, unknown> = {
  'bug-prediction': {
    timestamp: 'T', total_files: 3, analyzed_files: 3, high_risk_count: 1,
    files: [{ file_path: 'src/mark-bug.py', risk_score: 91, risk_level: 'high', factors: {} }],
  },
  'code-smells': buildSmellsExport(smellsPanelList, 'code'),
  'problems': [{ severity: 'high', type: 'x', message: 'm', file_path: 'src/mark-problem.py', line: 7 }],
  'duplicates': [{ file1: 'src/mark-dup-a.py', file2: 'src/mark-dup-b.py', similarity: 0.9, lines: 12 }],
  'declarations': [{ type: 'function', name: 'markDecl', file_path: 'src/mark-decl.py', line_number: 12 }],
  'api-endpoints': {
    coverage_percentage: 50, backend_endpoints: 2, frontend_calls: 1, used_endpoints: 1,
    orphaned_endpoints: 1, missing_endpoints: 0,
    orphaned: [{ path: '/api/mark-orphan', method: 'GET', file_path: 'api/mark.py' }],
    missing: [],
  },
  'cross-language': {
    dto_mismatches: [], validation_duplications: [],
    api_contract_mismatches: [{ mismatch_id: 'a', endpoint_path: '/api/mark-contract' }],
  },
  'config-duplicates': {
    duplicates_found: 1, report: '',
    duplicates: [{ value: 'MARK_CFG_VALUE', locations: [{ file: 'src/mark-cfg.py', line: 3 }] }],
  },
  'code-intelligence': {
    status: 'success', grade: 'B', health_score: 83, total_issues: 14, files_analyzed: 21,
    severity_breakdown: { high: 3, low: 11 },
  },
  'environment': {
    total_in_export: 1, total_in_analysis: 1, high_priority_count: 1,
    hardcoded_values: [{ type: 'url', value: 'markenvvalue', file: 'src/mark-env.py', line: 3, severity: 'high' }],
  },
  'statistics': { total_files: 7, python_files: 5 },
  'ownership': {
    summary: { total_files: 4, total_contributors: 1, knowledge_gaps_count: 1, critical_gaps: 0 },
    metrics: { overall_bus_factor: 1, ownership_concentration: 50, team_coverage: 80 },
    expertise_scores: [{ author_name: 'Mark Author', total_lines: 100, overall_score: 88 }],
    knowledge_gaps: [{ risk_level: 'high', area: 'src/mark-gap', description: 'd' }],
  },
  'hardcodes': [{ file: 'src/mark-hc.py', line: 5, value: 'v', type: 'url', severity: 'high' }],
}

/** A string only the displayed rows put into the markdown. */
const MARKER: Record<SectionType, string> = {
  'bug-prediction': 'src/mark-bug.py',
  'code-smells': 'src/mark-smell.py',
  'problems': 'src/mark-problem.py',
  'duplicates': 'src/mark-dup-a.py',
  'declarations': 'src/mark-decl.py',
  'api-endpoints': '/api/mark-orphan',
  'cross-language': '| API Contract Mismatches | 1 |',
  'config-duplicates': 'src/mark-cfg.py:3',
  'code-intelligence': '| Total Issues | 14 |',
  'environment': 'src/mark-env.py',
  'statistics': '| Total Files | 7 |',
  'ownership': 'Mark Author',
  'hardcodes': 'src/mark-hc.py',
}

const SECTIONS = Object.keys(DATA) as SectionType[]

function makeExport() {
  const notify = vi.fn()
  const sectionData = Object.fromEntries(
    SECTIONS.map((s) => [s, ref(DATA[s]) as Ref<unknown>]),
  ) as Record<SectionType, Ref<unknown>>
  const api = useCodebaseExport({
    sectionData,
    exportingReport: ref(false),
    progressStatus: ref(''),
    withSourceId: (u) => u,
    notify,
    t: (k) => k,
  })
  return { ...api, notify }
}

describe('section export carries the displayed data (#20492)', () => {
  beforeEach(() => saved.mockClear())

  it.each(SECTIONS)('%s: the JSON export is the loaded data', async (section) => {
    const { exportSection, notify } = makeExport()
    await exportSection(section, 'json')
    expect(notify).not.toHaveBeenCalledWith('analytics.codebase.notify.noDataAvailable', 'warning')
    expect(saved).toHaveBeenCalledTimes(1)
    expect(JSON.parse(saved.mock.calls[0][0] as string)).toEqual(DATA[section])
  })

  // Pre-fix, per section: declarations (printed `undefined` for file), api-endpoints
  // (no rows: read `endpoints`), config-duplicates (TypeError on `d.files.join`),
  // cross-language (counted `api_mismatches`), code-intelligence (read absent
  // `security_score`) and code-smells (counts only, no findings) fail here.
  it.each(SECTIONS)('%s: the MD export shows what the panel shows', async (section) => {
    const { exportSection } = makeExport()
    await exportSection(section, 'md')
    const md = saved.mock.calls[0][0] as string
    expect(md).toContain(MARKER[section])
    expect(md).not.toContain('undefined')
  })

  it('code smells: MD and JSON both return the findings on display', async () => {
    const { exportSection } = makeExport()
    await exportSection('code-smells', 'md')
    await exportSection('code-smells', 'json')
    const md = saved.mock.calls[0][0] as string
    const json = JSON.parse(saved.mock.calls[1][0] as string)
    expect(md).toContain('mark smell description')
    expect(json.smells).toEqual(smellsPanelList)
  })
})

describe('every exporting panel exports from the data it renders (#20492)', () => {
  const HERE = dirname(fileURLToPath(import.meta.url))
  const read = (rel: string) => readFileSync(resolve(HERE, rel), 'utf-8')
  const page = read('../../../components/analytics/CodebaseAnalytics.vue')
  const wiring = page.slice(page.indexOf('useCodebaseExport({'))

  /** section -> ref the export reads (the `sectionData` block of the page). */
  const exportedFrom = new Map(
    [...wiring.slice(0, wiring.indexOf('exportingReport')).matchAll(/'([\w-]+)':\s*(\w+) as Ref<unknown>/g)].map(
      (m) => [m[1], m[2]],
    ),
  )

  /**
   * The panel prop each exporting section renders its data from. A section
   * whose export is a derivation of what the panel binds names that source
   * here; the derivation itself is proven in `exportPanelDerivation.test.ts`.
   */
  const PANEL_PROP: Record<string, { prop: string; source: string }> = {
    'problems': { prop: 'problems', source: 'problemsReport' },
    'code-smells': { prop: 'smells', source: 'smellsForPanel' },
    'duplicates': { prop: 'duplicates', source: 'duplicateAnalysis' },
    'declarations': { prop: 'declarations', source: 'declarationsForPanel' },
    'hardcodes': { prop: 'hardcodes', source: 'hardcodeAnalysis' },
    'api-endpoints': { prop: 'analysis', source: 'apiEndpointAnalysis' },
    'cross-language': { prop: 'analysis', source: 'crossLanguageAnalysis' },
    'config-duplicates': { prop: 'analysis', source: 'configDuplicatesAnalysis' },
    'bug-prediction': { prop: 'analysis', source: 'bugPredictionAnalysis' },
    'environment': { prop: 'analysis', source: 'environmentAnalysis' },
    'ownership': { prop: 'analysis', source: 'ownershipAnalysis' },
  }

  it('the page exports every section this test covers, and no other', () => {
    expect([...exportedFrom.keys()].sort()).toEqual([...SECTIONS].sort())
  })

  it('no panel or page emits an export for a section outside the map', () => {
    const emitted = new Set<string>()
    for (const m of page.matchAll(/exportSection\('([\w-]+)'/g)) emitted.add(m[1])
    const charts = read('../../../components/analytics/panels/CodebaseChartsSection.vue')
    for (const m of charts.matchAll(/'export-section',\s*'([\w-]+)'/g)) emitted.add(m[1])
    expect(emitted.size).toBeGreaterThan(0)
    for (const section of emitted) expect(SECTIONS).toContain(section)
  })

  /** The component tag (opening `<Name` up to the export call) a call sits in. */
  const tagOf = (callIndex: number) => {
    const opens = [...page.matchAll(/<([A-Z]\w*)\b/g)].filter((o) => o.index! < callIndex)
    return page.slice(opens[opens.length - 1].index!, callIndex)
  }
  const bindingOf = (tag: string, prop: string) =>
    [...tag.matchAll(new RegExp(`(?:^|\\s):${prop}="([^"]*)"`, 'g'))].map((b) => b[1])

  it.each(Object.keys(PANEL_PROP))('%s: its panel prop is bound to exactly the source it exports', (section) => {
    const { prop, source } = PANEL_PROP[section]
    const call = page.indexOf(`exportSection('${section}'`)
    expect(call, `${section} has no export button on the page`).toBeGreaterThan(-1)
    expect(bindingOf(tagOf(call), prop)).toEqual([source])
    // the export reads that source, or (for a derived one) a value built from it
    const reads = exportedFrom.get(section)
    if (reads !== source) expect(['smellsExport', 'declarationAnalysis']).toContain(reads)
  })

  it('every section with a page export button has an entry above', () => {
    const buttons = new Set([...page.matchAll(/exportSection\('([\w-]+)'/g)].map((m) => m[1]))
    expect([...buttons].sort()).toEqual(Object.keys(PANEL_PROP).sort())
  })

  it('statistics: the charts section renders the ref the export reads', () => {
    const bound = [...page.matchAll(/:codebase-stats="(\w+)"/g)].map((m) => m[1])
    expect(bound).toEqual([exportedFrom.get('statistics')])
  })
})
