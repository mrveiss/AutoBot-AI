// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * DeclarationsSection component tests (#5369)
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import DeclarationsSection from '../DeclarationsSection.vue'

interface Declaration {
  name: string
  file_path: string
  line_number: number
  is_exported: boolean
  declaration_type?: string
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
        declarations: {
          title: 'Declarations',
          total: 'Total',
          exported: 'exported',
          emptyMessage: 'No declarations detected',
          types: {
            function: 'Functions',
            class: 'Classes',
            method: 'Methods',
            variable: 'Variables',
            constant: 'Constants',
            interface: 'Interfaces',
            type: 'Types',
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

const mountSection = (declarations: Declaration[] = [], loading = false) =>
  mount(DeclarationsSection, {
    props: { declarations, loading },
    global: {
      plugins: [i18n],
      stubs: { EmptyState: { template: '<div class="empty-state" />' } },
    },
  })

const makeDecl = (overrides: Partial<Declaration> = {}): Declaration => ({
  name: 'myFunc',
  file_path: 'src/x.ts',
  line_number: 10,
  is_exported: false,
  declaration_type: 'function',
  ...overrides,
})

describe('DeclarationsSection (#5369)', () => {
  describe('rendering branches', () => {
    it('renders empty state when no declarations', () => {
      const w = mountSection([])
      expect(w.find('.empty-state').exists()).toBe(true)
      expect(w.find('.section-content').exists()).toBe(false)
    })

    it('renders spinner when loading=true', () => {
      const w = mountSection([], true)
      expect(w.find('.section-loading').exists()).toBe(true)
      expect(w.find('.empty-state').exists()).toBe(false)
      // Icon.vue renders an SVG with `icon-spin` (no FontAwesome classes)
      expect(w.find('.icon-spin').exists()).toBe(true)
    })

    it('renders spinner (not empty-state) with declarations when loading=true', () => {
      const w = mountSection([makeDecl()], true)
      expect(w.find('.section-loading').exists()).toBe(true)
      expect(w.find('.section-content').exists()).toBe(false)
    })

    it('renders summary cards + accordion when populated', () => {
      const w = mountSection([makeDecl()])
      expect(w.find('.section-content').exists()).toBe(true)
      expect(w.find('.summary-cards').exists()).toBe(true)
    })
  })

  describe('type grouping', () => {
    it('creates one summary card per distinct declaration_type', () => {
      const items = [
        makeDecl({ declaration_type: 'function', name: 'f1' }),
        makeDecl({ declaration_type: 'function', name: 'f2' }),
        makeDecl({ declaration_type: 'class', name: 'C1' }),
        makeDecl({ declaration_type: 'variable', name: 'v1' }),
      ]
      const w = mountSection(items)
      // Total card + 3 type cards = 4
      expect(w.findAll('.summary-card').length).toBe(4)
    })

    it('totals to the full declaration count', () => {
      const items = [
        makeDecl({ declaration_type: 'function', name: 'f1' }),
        makeDecl({ declaration_type: 'class', name: 'C1' }),
      ]
      const w = mountSection(items)
      expect(w.find('.summary-card.total .summary-value').text()).toBe('2')
    })

    it('shows exported badge when group has exported declarations', () => {
      const items = [makeDecl({ is_exported: true, declaration_type: 'function' })]
      const w = mountSection(items)
      // Header badge should be rendered
      expect(w.find('.export-badge').exists()).toBe(true)
    })
  })

  describe('export events', () => {
    it('emits export("md") on MD click', async () => {
      const w = mountSection([makeDecl()])
      const mdButton = w.findAll('.export-btn').find(b => b.text().includes('MD'))
      await mdButton!.trigger('click')
      expect(w.emitted('export')![0]).toEqual(['md'])
    })

    it('emits export("json") on JSON click', async () => {
      const w = mountSection([makeDecl()])
      const jsonButton = w.findAll('.export-btn').find(b => b.text().includes('JSON'))
      await jsonButton!.trigger('click')
      expect(w.emitted('export')![0]).toEqual(['json'])
    })
  })

  describe('show more (#12741)', () => {
    it('is a button that reveals the next rows and keeps the count accurate', async () => {
      const items = Array.from({ length: 35 }, (_, i) =>
        makeDecl({ declaration_type: 'function', name: `f${i}`, line_number: i }),
      )
      const w = mountSection(items)
      const header = w.find('.accordion-header')
      await header.trigger('click')
      const rows = () => w.findAll('.list-item')
      expect(rows()).toHaveLength(30)
      expect(w.find('[data-testid="truncation-count"]').text()).toBe('Showing 30 of 35')

      const button = w.find('[data-testid="truncation-show-more"]')
      expect(button.element.tagName).toBe('BUTTON')
      await button.trigger('click')

      expect(rows()).toHaveLength(35)
      // Everything is visible now, so the notice (and its button) is gone.
      expect(w.find('[data-testid="truncation-show-more"]').exists()).toBe(false)
    })
  })
})
