// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * FailureAnalysisDashboard renders each intervention's risk through the kit RiskBadge,
 * from the backend's risk_tier (#13422), and shows the raw risk_level when the backend
 * could not grade it.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { ref } from 'vue'
import en from '@/i18n/locales/en.json'
import type { CausalAnalysisData, InterventionItem } from '@/composables/useFailureAnalysis'

function intervention(risk_level: string, risk_tier: InterventionItem['risk_tier']): InterventionItem {
  return {
    name: `fix-${risk_level}`,
    description: '',
    mechanism: '',
    predicted_success_rate: 0.5,
    cost_level: 'low',
    risk_level,
    risk_tier,
    recommendation_type: 'immediate',
    impact_rank: 1,
    confidence: 0.5,
    evidence: [],
  }
}

const result = ref<CausalAnalysisData | null>(null)

vi.mock('@/composables/useFailureAnalysis', () => ({
  useFailureAnalysis: () => ({
    loading: ref(false),
    error: ref(null),
    result,
    analyzeFailure: vi.fn(),
    clearResult: vi.fn(),
  }),
}))

import FailureAnalysisDashboard from '../FailureAnalysisDashboard.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

function mountWith(interventions: InterventionItem[]) {
  result.value = {
    task_id: 't',
    error_description: '',
    severity: 'warning',
    root_cause: null,
    causal_chain: [],
    confounders: [],
    confounding_strength: 0,
    interventions,
    recommendations: [],
    confidence: 0.5,
    chain_depth: 0,
    timestamp: '',
    analysis_status: 'success',
    analysis_duration_ms: 0,
    error_message: null,
  }
  return mount(FailureAnalysisDashboard, { global: { plugins: [i18n] } })
}

describe('FailureAnalysisDashboard risk', () => {
  it('renders a graded intervention as the kit RiskBadge with the translated tier', () => {
    const w = mountWith([intervention('medium', 'medium')])
    const badge = w.find('[data-risk-tier="medium"]')
    expect(badge.exists()).toBe(true)
    expect(badge.text()).toBe(en.common.riskTier.medium)
  })

  it('shows the raw risk_level when the backend gave no tier', () => {
    const w = mountWith([intervention('unknown', null)])
    expect(w.find('[data-risk-tier]').exists()).toBe(false)
    expect(w.text()).toContain('unknown')
  })
})
