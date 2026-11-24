// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * DuplicatesSection component tests (#5369)
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import DuplicatesSection from '../DuplicatesSection.vue'
import { duplicateSummary } from '@/composables/analytics/duplicatePayload'

interface Duplicate {
  similarity: number
  lines: number
  file1: string
  file2: string
  kind?: string
  locations?: { file: string; start_line: number; end_line: number }[]
}

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      analytics: {
        truncation: {
          showingOf: 'Showing {shown} of {total}',
          showMore: 'Show {count} more',
          serverLimited: 'Showing the top {shown} of {total}. The server limits this list.',
        },
        duplicates: {
          title: 'Duplicate Code',
          clusters: 'clusters',
          totalClusters: 'Total Clusters',
          truncated: 'Showing {shown} of {total} clusters',
          exactClusters: '{count} exact',
          structuralClusters: '{count} structural',
          totalLocations: '{count} locations',
          excluded: 'Excluded: {dirs}',
          kind: { exact: 'exact', structural: 'structural', similar: 'similar' },
          highLabel: 'High',
          mediumLabel: 'Medium',
          lowLabel: 'Low',
          totalLines: 'Total Lines',
          similar: 'similar',
          lines: 'lines',
          emptyMessage: 'No duplicate code detected',
          similarityGroups: {
            high: 'High Similarity',
            medium: 'Medium Similarity',
            low: 'Low Similarity',
          },
        },
        codebase: {
          actions: {
            exportMarkdown: 'Export Markdown',
            exportJson: 'Export JSON',
            loading: 'Loading...',
          },
        },
      },
    },
  },
})

const mountSection = (duplicates: Duplicate[] = [], loading = false) =>
  mount(DuplicatesSection, {
    props: { duplicates, loading },
    global: {
      plugins: [i18n],
      stubs: { EmptyState: { template: '<div class="empty-state" />' } },
    },
  })

const makeDup = (overrides: Partial<Duplicate> = {}): Duplicate => ({
  similarity: 95,
  lines: 30,
  file1: 'src/a.ts',
  file2: 'src/b.ts',
  ...overrides,
})

describe('DuplicatesSection (#5369)', () => {
  describe('rendering branches', () => {
    it('renders empty state when no duplicates', () => {
      const w = mountSection([])
      expect(w.find('.empty-state').exists()).toBe(true)
      expect(w.find('.section-content').exists()).toBe(false)
    })

    it('renders spinner when loading=true', () => {
      const w = mountSection([], true)
      expect(w.find('.section-loading').exists()).toBe(true)
      expect(w.find('.empty-state').exists()).toBe(false)
      expect(w.find('.animate-spin').exists()).toBe(true)
    })

    it('renders spinner (not empty-state) with duplicates when loading=true', () => {
      const w = mountSection([makeDup()], true)
      expect(w.find('.section-loading').exists()).toBe(true)
      expect(w.find('.section-content').exists()).toBe(false)
    })

    it('renders summary cards + accordion when populated', () => {
      const w = mountSection([makeDup()])
      expect(w.find('.section-content').exists()).toBe(true)
      expect(w.find('.summary-cards').exists()).toBe(true)
    })
  })

  describe('similarity grouping', () => {
    it('buckets similarity >= 90 into high, 70-89 into medium, <70 into low', () => {
      const items = [
        makeDup({ similarity: 95, lines: 10 }),
        makeDup({ similarity: 90, lines: 10 }),
        makeDup({ similarity: 80, lines: 10 }),
        makeDup({ similarity: 70, lines: 10 }),
        makeDup({ similarity: 60, lines: 10 }),
      ]
      const w = mountSection(items)
      const summaryValues = w.findAll('.summary-card .summary-value').map(n => n.text())
      // Order: total, high, medium, low, totalLines(info)
      expect(summaryValues[0]).toBe('5') // total
      expect(summaryValues[1]).toBe('2') // high (95, 90)
      expect(summaryValues[2]).toBe('2') // medium (80, 70)
      expect(summaryValues[3]).toBe('1') // low (60)
      expect(summaryValues[4]).toBe('50') // totalLines = 5 * 10
    })
  })

  describe('export events', () => {
    it('emits export("md") on MD click', async () => {
      const w = mountSection([makeDup()])
      const mdButton = w.findAll('.export-btn').find(b => b.text().includes('MD'))
      await mdButton!.trigger('click')
      expect(w.emitted('export')![0]).toEqual(['md'])
    })

    it('emits export("json") on JSON click', async () => {
      const w = mountSection([makeDup()])
      const jsonButton = w.findAll('.export-btn').find(b => b.text().includes('JSON'))
      await jsonButton!.trigger('click')
      expect(w.emitted('export')![0]).toEqual(['json'])
    })
  })

  describe('show more (#12741)', () => {
    it('is a button that reveals the next rows and keeps the count accurate', async () => {
      const items = Array.from({ length: 25 }, (_, i) =>
        makeDup({ similarity: 95, file1: `a${i}.ts`, file2: `b${i}.ts` }),
      )
      const w = mountSection(items)
      const header = w.find('.accordion-header')
      await header.trigger('click')
      const rows = () => w.findAll('.list-item')
      expect(rows()).toHaveLength(20)
      expect(w.find('[data-testid="truncation-count"]').text()).toBe('Showing 20 of 25')

      const button = w.find('[data-testid="truncation-show-more"]')
      expect(button.element.tagName).toBe('BUTTON')
      await button.trigger('click')

      expect(rows()).toHaveLength(25)
      // Everything is visible now, so the notice (and its button) is gone.
      expect(w.find('[data-testid="truncation-show-more"]').exists()).toBe(false)
    })
  })

  describe('true total (#22157)', () => {
    it('shows the scan total and truncated, never the number of returned rows', () => {
      duplicateSummary.value = {
        totalCount: 12345,
        truncated: true,
        totalLocations: 30000,
        exactCount: 12000,
        structuralCount: 345,
        excludedDirs: ['external'],
      }
      try {
        const w = mountSection([makeDup(), makeDup()])
        expect(w.find('.summary-card.total .summary-value').text()).toBe((12345).toLocaleString())
        expect(w.find('h3 .total-count').text()).toContain((12345).toLocaleString())
        expect(w.find('.duplicate-truncated').text()).toBe('Showing 2 of 12345 clusters')
        expect(w.find('.duplicate-breakdown').text()).toContain('Excluded: external')
      } finally {
        duplicateSummary.value = null
      }
    })

    it('lists every location of a cluster', async () => {
      const locations = [1, 2, 3].map(n => ({ file: `src/f${n}.ts`, start_line: n, end_line: n + 9 }))
      const w = mountSection([makeDup({ kind: 'exact', locations } as Partial<Duplicate>)])
      await w.find('.accordion-header').trigger('click')
      expect(w.findAll('.item-file').map(n => n.text())).toEqual(['src/f1.ts:1-10', 'src/f2.ts:2-11', 'src/f3.ts:3-12'])
    })
  })
})
