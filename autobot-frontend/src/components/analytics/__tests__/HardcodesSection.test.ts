// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * HardcodesSection component tests (#5369)
 *
 * Covers the regression surface most likely to break silently:
 * - empty/loading/populated rendering branches
 * - severity grouping (high/medium/low/critical)
 * - summary card counts
 * - export event emission
 * - overflow \"Showing N of M\" footer
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import HardcodesSection from '../HardcodesSection.vue'
import type { HardcodedValue } from '@/composables/analytics/analyticsTypes'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      analytics: {
        hardcodes: {
          title: 'Hardcoded Values',
          values: 'values',
          totalValues: 'Total Values',
          highLabel: 'High',
          mediumLabel: 'Medium',
          lowLabel: 'Low',
          uniqueTypes: 'Unique Types',
          variable: 'Variable',
          value: 'Value',
          suggestedEnvVar: 'Suggested Env Var',
          showingOf: 'Showing {shown} of {total}',
          emptyMessage: 'No hardcoded values detected',
          severityGroups: {
            high: 'High Severity',
            medium: 'Medium Severity',
            low: 'Low Severity',
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

const mountSection = (
  hardcodes: HardcodedValue[] = [],
  loading = false,
) =>
  mount(HardcodesSection, {
    props: { hardcodes, loading },
    global: {
      plugins: [i18n],
      stubs: { EmptyState: { template: '<div class="empty-state" />' } },
    },
  })

const makeHardcode = (overrides: Partial<HardcodedValue> = {}): HardcodedValue => ({
  file: 'src/config.py',
  line: 42,
  type: 'ip',
  value: '127.0.0.1',
  severity: 'high',
  ...overrides,
})

describe('HardcodesSection (#5369)', () => {
  describe('rendering branches', () => {
    it('renders empty state when no hardcodes', () => {
      const w = mountSection([])
      expect(w.find('.empty-state').exists()).toBe(true)
      expect(w.find('.section-content').exists()).toBe(false)
    })

    it('renders spinner when loading=true', () => {
      const w = mountSection([], true)
      expect(w.find('.section-loading').exists()).toBe(true)
      expect(w.find('.empty-state').exists()).toBe(false)
      expect(w.find('.icon-spin').exists()).toBe(true)
    })

    it('renders spinner (not empty-state) even with hardcodes when loading=true', () => {
      const w = mountSection([makeHardcode()], true)
      expect(w.find('.section-loading').exists()).toBe(true)
      expect(w.find('.section-content').exists()).toBe(false)
    })

    it('renders summary cards + accordion when populated', () => {
      const w = mountSection([makeHardcode()])
      expect(w.find('.section-content').exists()).toBe(true)
      expect(w.find('.summary-cards').exists()).toBe(true)
      expect(w.find('.accordion-groups').exists()).toBe(true)
    })
  })

  describe('severity grouping', () => {
    it('buckets critical + high into the high group', () => {
      const items = [
        makeHardcode({ severity: 'critical', value: 'c1' }),
        makeHardcode({ severity: 'high', value: 'h1' }),
        makeHardcode({ severity: 'medium', value: 'm1' }),
        makeHardcode({ severity: 'low', value: 'l1' }),
      ]
      const w = mountSection(items)
      const summaryValues = w.findAll('.summary-card .summary-value').map(n => n.text())
      // Order: total, high, medium, low, uniqueTypes
      expect(summaryValues[0]).toBe('4') // total
      expect(summaryValues[1]).toBe('2') // high (critical + high)
      expect(summaryValues[2]).toBe('1') // medium
      expect(summaryValues[3]).toBe('1') // low
    })

    it('buckets unknown severity into low', () => {
      const items = [makeHardcode({ severity: '', value: 'x' })]
      const w = mountSection(items)
      const summaryValues = w.findAll('.summary-card .summary-value').map(n => n.text())
      expect(summaryValues[3]).toBe('1') // low
      expect(summaryValues[1]).toBe('0') // high
      expect(summaryValues[2]).toBe('0') // medium
    })

    it('uniqueTypes counts distinct type values', () => {
      const items = [
        makeHardcode({ type: 'ip', value: 'a' }),
        makeHardcode({ type: 'ip', value: 'b' }),
        makeHardcode({ type: 'url', value: 'c' }),
      ]
      const w = mountSection(items)
      const summaryValues = w.findAll('.summary-card .summary-value').map(n => n.text())
      expect(summaryValues[4]).toBe('2')
    })
  })

  describe('export events', () => {
    it('emits export("md") when MD button clicked', async () => {
      const w = mountSection([makeHardcode()])
      const mdButton = w.findAll('.export-btn').find(b => b.text().includes('MD'))
      await mdButton!.trigger('click')
      expect(w.emitted('export')).toBeTruthy()
      expect(w.emitted('export')![0]).toEqual(['md'])
    })

    it('emits export("json") when JSON button clicked', async () => {
      const w = mountSection([makeHardcode()])
      const jsonButton = w.findAll('.export-btn').find(b => b.text().includes('JSON'))
      await jsonButton!.trigger('click')
      expect(w.emitted('export')).toBeTruthy()
      expect(w.emitted('export')![0]).toEqual(['json'])
    })
  })

  describe('overflow footer', () => {
    it('shows "Showing 20 of N" when a group has more than 20 items', async () => {
      const items = Array.from({ length: 25 }, (_, i) =>
        makeHardcode({ value: `v${i}`, line: i }),
      )
      const w = mountSection(items)
      // Expand the 'high' group first
      const header = w.find('.accordion-header')
      await header.trigger('click')
      expect(w.find('.show-more').exists()).toBe(true)
      expect(w.find('.show-more').text()).toContain('25')
    })
  })
})
