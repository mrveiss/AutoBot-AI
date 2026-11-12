// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Issue #20492: where a section's export is a derivation of what its panel
 * shows, the derivation itself is proven here -- through the real composable,
 * not a hand-built fixture -- so a refactor that breaks the link fails.
 *
 *  - code smells: the real `useCodeSmellProblems` (fetch layer mocked) loads
 *    findings; `smellsForPanel` is what the cards show, `smellsExport` is what
 *    the export carries.
 *  - declarations: `useAnalyticsDataFetchers` pulls in the app config and the
 *    background-task stack, so it is not drivable with the fetch layer alone.
 *    The panel rows come from the pure `toDeclarationPanelRows`, driven here,
 *    plus a source assertion that the fetcher derives `declarationsForPanel`
 *    from `declarationAnalysis` through it.
 */
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, type Ref } from 'vue'

const saved = vi.hoisted(() => vi.fn())
const fetched = vi.hoisted(() => ({ onSuccess: undefined as undefined | ((d: unknown[]) => void) }))

vi.mock('@autobot/ui', () => ({
  saveTextFile: (...args: unknown[]) => saved(...args),
  isoTimestampStamp: () => 'TS',
}))
vi.mock('@/composables/api/useFetchEndpoint', () => ({
  useFetchEndpoint: (cfg: { path?: string; fallbackData?: unknown; onSuccess?: (d: unknown[]) => void }) => {
    // The smells composable's endpoint: capture its success hook to deliver findings.
    if (cfg.path === '/api/analytics/codebase/problems') fetched.onSuccess = cfg.onSuccess
    return { load: vi.fn(async () => undefined), error: ref(''), loading: ref(false), data: ref(cfg.fallbackData ?? null) }
  },
}))

import { useCodeSmellProblems } from '../useCodeSmellProblems'
import { useCodebaseExport } from '../useCodebaseExport'
import { toDeclarationPanelRows } from '../declarationPanelRows'

const FINDINGS = [
  { type: 'long_function', severity: 'high', message: 'first smell message', file_path: 'src/first-smell.py', line: 10 },
  { type: 'god_class', severity: 'medium', description: 'second smell description', file_path: 'src/second-smell.py', line_number: 20 },
]

function exporterFor(smellsExport: Ref<unknown>) {
  return useCodebaseExport({
    sectionData: { 'code-smells': smellsExport } as never,
    exportingReport: ref(false),
    progressStatus: ref(''),
    withSourceId: (u) => u,
    notify: vi.fn(),
    t: (k) => k,
  })
}

describe('code smells: the export is built from the findings the panel shows (#20492)', () => {
  beforeEach(() => saved.mockClear())

  // Pre-fix (smellsExport reading a separate store): the JSON would not equal the
  // panel list, and the MD would lack the findings.
  it('MD and JSON of smellsExport return the findings smellsForPanel displays', async () => {
    const s = useCodeSmellProblems((u) => u)
    await s.loadSmellProblems()
    fetched.onSuccess?.(FINDINGS)
    const shown = s.smellsForPanel.value
    expect(shown).toHaveLength(2)

    const { exportSection } = exporterFor(s.smellsExport as Ref<unknown>)
    await exportSection('code-smells', 'json')
    await exportSection('code-smells', 'md')
    const json = JSON.parse(saved.mock.calls[0][0] as string)
    const md = saved.mock.calls[1][0] as string

    expect(json.smells).toEqual(shown)
    expect(json.summary.total_smells).toBe(shown.length)
    for (const f of shown) {
      expect(md).toContain(f.file_path)
      expect(md).toContain(f.description as string)
    }
  })

  it('a reload that replaces the findings replaces the export with them', async () => {
    const s = useCodeSmellProblems((u) => u)
    fetched.onSuccess?.(FINDINGS)
    fetched.onSuccess?.([FINDINGS[0]])
    expect(s.smellsForPanel.value).toHaveLength(1)
    expect(s.smellsExport.value.smells).toEqual(s.smellsForPanel.value)
  })
})

describe('declarations: the panel rows are derived from the loaded declarations (#20492)', () => {
  const loaded = [
    { type: 'function', name: 'alpha', file_path: 'src/a.py', line: 3 },
    { type: 'class', name: 'Beta', file_path: 'src/b.py', line_number: 9, is_exported: true },
  ]

  it('every loaded declaration appears in the panel rows with its own file and line', () => {
    const rows = toDeclarationPanelRows(loaded)
    expect(rows.map((r) => [r.name, r.file_path, r.line_number])).toEqual([
      ['alpha', 'src/a.py', 3],
      ['Beta', 'src/b.py', 9],
    ])
  })

  it('the fetcher derives declarationsForPanel from declarationAnalysis through it', () => {
    const here = dirname(fileURLToPath(import.meta.url))
    const src = readFileSync(resolve(here, '../useAnalyticsDataFetchers.ts'), 'utf-8')
    expect(src).toMatch(
      /const declarationsForPanel = computed\(\(\) => toDeclarationPanelRows\(declarationAnalysis\.value\)\)/,
    )
  })
})
