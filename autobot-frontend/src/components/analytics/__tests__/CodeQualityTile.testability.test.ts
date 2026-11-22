// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The overview's Code Quality tile names the testability figure for what it is (#21395).
 *
 * The figure is the health score's 0-100 `testability` factor; no test-coverage source is wired.
 * Both cards that render it label it "Testability" and show it without a % sign.
 */
import { describe, it, expect } from 'vitest'
import type { Component } from 'vue'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import CodebaseOverviewPanel from '../CodebaseOverviewPanel.vue'
import AnalyticsGrid from '../AnalyticsGrid.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const props = (testability: number | null) => ({
  systemOverview: null,
  communicationPatterns: null,
  codeQuality: { overall_score: 72, testability, code_duplicates: 7, technical_debt: 12 },
  performanceMetrics: null,
  realTimeEnabled: false,
})
const qualityText = (component: Component, testability: number | null) =>
  mount(component, { props: props(testability), global: { plugins: [i18n] } }).find('.quality-details').text()

describe.each([
  ['CodebaseOverviewPanel', CodebaseOverviewPanel, en.analytics.codebase.quality],
  ['AnalyticsGrid', AnalyticsGrid, en.analytics.grid],
])('%s Code Quality tile (#21395)', (_name, component, msg) => {
  it('labels the figure "Testability" and shows it without a % sign', () => {
    const text = qualityText(component, 61)
    expect(msg.testability).toBe('Testability')
    expect(text).toContain(msg.testability)
    expect(text).toContain('61')
    expect(text).not.toContain('61%')
    expect(text).not.toContain('Test Coverage')
  })

  it('a missing figure reads "not available", not a number', () => {
    expect(qualityText(component, null)).toContain(msg.notAvailable)
  })
})
