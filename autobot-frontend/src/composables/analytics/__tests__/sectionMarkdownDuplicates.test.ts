// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The duplicates markdown export counts clusters and lists every location (#22157),
 * not the first two files of a pair.
 */
import { describe, it, expect, afterEach, beforeAll } from 'vitest'
import i18n from '@/i18n'
import en from '@/i18n/locales/en.json'
import { duplicateSummary, readDuplicatePayload } from '../duplicatePayload'
import { generateSectionMarkdown } from '../sectionMarkdown'

const cluster = {
  kind: 'exact',
  similarity: 100,
  lines: 30,
  file1: 'a.py',
  file2: 'b.py',
  locations: ['a.py', 'b.py', 'c.py'].map((file, i) => ({ file, start_line: i + 1, end_line: i + 30 })),
}

// The app's i18n starts with no messages (#12342) and initI18n() loads them before mount; a unit
// test has no bootstrap, so load the real English bundle into the same global instance.
beforeAll(() => {
  i18n.global.setLocaleMessage('en', en as never)
  i18n.global.locale.value = 'en'
})

describe('duplicates markdown export (#22157)', () => {
  afterEach(() => { duplicateSummary.value = null })

  it('lists every location of a cluster and counts clusters, not pairs', () => {
    const md = generateSectionMarkdown('duplicates', [cluster])
    expect(md).toContain('**Total Duplicate Clusters Found:** 1 (3 locations)')
    expect(md).toContain('a.py:1-30<br>b.py:2-31<br>c.py:3-32')
    expect(md).toContain('| exact | 100.0% | 30 |')
    expect(md).not.toContain('Pairs')
  })

  it('reports the scan total, not the number of rows returned, when truncated', () => {
    duplicateSummary.value = {
      totalCount: 9000, truncated: true, totalLocations: 20000, exactCount: 8000, structuralCount: 1000, excludedDirs: [],
    }
    const md = generateSectionMarkdown('duplicates', [cluster])
    expect(md).toContain('**Total Duplicate Clusters Found:** 9000 (20000 locations)')
    expect(md).toContain('Showing 1 of 9000 clusters.')
  })

  it('falls back to file1/file2 for a row whose locations list is empty', () => {
    const md = generateSectionMarkdown('duplicates', [{ ...cluster, locations: [] }])
    expect(md).toContain('| a.py<br>b.py | exact |')
    expect(md).toContain('(2 locations)')
  })

  it('routes every export label through i18n (en)', () => {
    const md = generateSectionMarkdown('duplicates', [cluster])
    expect(md).toContain('## Duplicate Code Analysis')
    expect(md).toContain('| Locations | Kind | Similarity | Lines |')
    expect(md).not.toContain('analytics.duplicates.')
  })

  it('omits the location count when the payload cannot establish it', () => {
    duplicateSummary.value = {
      totalCount: 4, truncated: true, totalLocations: null, exactCount: 4, structuralCount: 0, excludedDirs: [],
    }
    const md = generateSectionMarkdown('duplicates', [cluster])
    expect(md).toContain('**Total Duplicate Clusters Found:** 4\n')
    expect(md).not.toContain('locations)')
  })
})

describe('the location total of a payload without total_locations (#22157)', () => {
  const legacyRow = {
    kind: 'exact', similarity: 100, lines: 30, file1: 'a.py', file2: 'b.py',
    start_line1: 1, end_line1: 30, start_line2: 1, end_line2: 30,
  }
  const noPositions = { kind: 'exact', similarity: 100, lines: 30, file1: 'a.py', file2: 'b.py' }

  it('counts the distinct places of a complete legacy result, never the cluster count', () => {
    const reading = readDuplicatePayload({ status: 'success', total_count: 1, duplicates: [legacyRow] })
    expect(reading.summary?.totalLocations).toBe(2)
  })

  it('keeps legacy rows at different positions apart and names their ranges', () => {
    const at = (s1: number, s2: number) => ({ ...legacyRow, start_line1: s1, end_line1: s1 + 29, start_line2: s2, end_line2: s2 + 29 })
    const reading = readDuplicatePayload({ status: 'success', total_count: 2, duplicates: [at(1, 1), at(50, 50)] })
    expect(reading.summary?.totalLocations).toBe(4)
    expect(generateSectionMarkdown('duplicates', [at(1, 50)])).toContain('a.py:1-30<br>b.py:50-79')
  })

  it('leaves the total unknown when a legacy row carries no positions (ChromaDB fallback)', () => {
    const reading = readDuplicatePayload({ status: 'success', total_count: 2, duplicates: [legacyRow, noPositions] })
    expect(reading.summary?.totalLocations).toBeNull()
    expect(generateSectionMarkdown('duplicates', [noPositions])).toContain('a.py<br>b.py')
  })

  it('translates a recognised kind and keeps an unknown one and the dash', () => {
    const md = generateSectionMarkdown('duplicates', [cluster, { ...cluster, kind: 'novel' }, { ...cluster, kind: undefined }])
    expect(md).toContain('| exact | 100.0% |')
    expect(md).toContain('| novel | 100.0% |')
    expect(md).toContain('| - | 100.0% |')
  })

  it('keeps an explicit total_locations and leaves a cut list unknown', () => {
    const explicit = readDuplicatePayload({ status: 'success', total_count: 1, total_locations: 7, duplicates: [legacyRow] })
    expect(explicit.summary?.totalLocations).toBe(7)
    const cut = readDuplicatePayload({ status: 'success', total_count: 5, truncated: true, duplicates: [legacyRow] })
    expect(cut.summary?.totalLocations).toBeNull()
  })
})
