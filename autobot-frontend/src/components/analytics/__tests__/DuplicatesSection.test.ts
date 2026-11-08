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

interface Duplicate {
  similarity: number
  lines: number
  file1: string
  file2: string
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
          pairs: 'pairs',
          totalPairs: 'Total Pairs',
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
})
