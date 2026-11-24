// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The duplicates markdown export counts clusters and lists every location (#22157),
 * not the first two files of a pair.
 */
import { describe, it, expect, afterEach } from 'vitest'
import { duplicateSummary } from '../duplicatePayload'
import { generateSectionMarkdown } from '../sectionMarkdown'

const cluster = {
  kind: 'exact',
  similarity: 100,
  lines: 30,
  file1: 'a.py',
  file2: 'b.py',
  locations: ['a.py', 'b.py', 'c.py'].map((file, i) => ({ file, start_line: i + 1, end_line: i + 30 })),
}

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
})
