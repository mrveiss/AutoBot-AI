// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * ValidationDashboard (#18278): the report is shown from /status + /report, and each state is
 * said apart -- reading, not available (503), failed, and read-but-empty. A phase with no score
 * reads "Not scored", never 0%. The one action, /generate, reports both its start and its failure.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { HttpError } from '@autobot/ui'
import ValidationDashboard from './ValidationDashboard.vue'
import en from '@/locales/en.json'

const client = { get: vi.fn(), post: vi.fn() }
vi.mock('@/composables/useAutobotApi', () => ({ createAutobotBackendClient: () => client }))

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })
const L = en.monitoring.validationDashboard

const status = { status: 'healthy', service: 'validation_dashboard', output_directory: '/x', refresh_interval: 30, data_retention_days: 7, timestamp: '2026-11-01T10:00:00+00:00' }

function phase(name: string, completion: number | null, gates: string[] = []) {
  return {
    name, display_name: name.replace('_', ' '), completion_percentage: completion, scored: completion !== null,
    authoritative_gates: gates, status: completion === null ? 'deferred' : 'mostly_complete',
    missing_count: 2, requirements_met: 8, total_requirements: 10,
  }
}

const report = {
  generated_at: '2026-11-01T10:00:00',
  system_overview: { overall_maturity: 72.5, measures: 'completion', total_phases: 2, completed_phases: 1, system_health: 'good', active_capabilities: 41 },
  phase_details: [phase('phase_one', 91.25), phase('phase_two', null, ['ci-gate'])],
  progression_status: { can_progress: true, next_available: ['phase_two'], blocked_phases: [] },
  metrics: {
    completion_statistics: { average_completion: 80, min_completion: 70, max_completion: 91.25, phases_above_50: 2, phases_above_90: 1 },
    system_maturity: { overall_score: 72.5, development_stage: 'integration', capability_ratio: 0.41 },
    progression_metrics: { eligible_for_progression: true, progression_velocity: 3, blocks_count: 0, available_count: 1 },
    quality_indicators: { validation_score: 88, error_rate: 0, recent_changes: 5 },
  },
  trends: {
    maturity_trend: [{ timestamp: 't1', value: 50 }, { timestamp: 't2', value: 60 }],
    phase_completion_trend: [],
    capability_growth: [{ timestamp: 't1', capabilities: 20 }],
  },
  recommendations: [{ type: 'priority', title: 'Focus on Phase One', description: 'Only 20% complete.', action: 'Review missing items', urgency: 'high' }],
  alerts: [{ level: 'warning', title: 'Multiple Stalled Phases', message: '4 phases are stalled', timestamp: '2026-11-01T10:00:00' }],
}

let wrapper: VueWrapper | undefined

function serve(overrides: { status?: unknown; report?: unknown } = {}): void {
  client.get.mockImplementation(async (url: string) => {
    if (url === '/validation-dashboard/status') return overrides.status ?? status
    if (url === '/validation-dashboard/report') return { status: 'success', report: 'report' in overrides ? overrides.report : report, timestamp: 't' }
    throw new Error(`unrouted ${url}`)
  })
}

async function mountView(): Promise<VueWrapper> {
  wrapper = mount(ValidationDashboard, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

const byId = (w: VueWrapper, id: string) => w.find(`[data-testid="${id}"]`)

beforeEach(() => {
  client.get.mockReset()
  client.post.mockReset()
  serve()
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
})

describe('ValidationDashboard', () => {
  it('reads /status and /report once and shows the overview, phases, alerts, recommendations and trends', async () => {
    const w = await mountView()
    expect(client.get).toHaveBeenCalledWith('/validation-dashboard/status', { maxRetries: 1 })
    expect(client.get).toHaveBeenCalledWith('/validation-dashboard/report', { maxRetries: 1 })
    expect(client.get).toHaveBeenCalledTimes(2)
    expect(byId(w, 'slm-validation-stat-maturity').text()).toContain('72.5%')
    expect(byId(w, 'slm-validation-stat-phases').text()).toContain('1 of 2')
    expect(byId(w, 'slm-validation-stat-refreshInterval').text()).toContain('30 s')
    expect(byId(w, 'slm-validation-measures').text()).toBe('completion')
    expect(w.text()).toContain('phase one')
    expect(w.text()).toContain('91.3%')
    expect(w.findAll('[data-testid="slm-validation-alert"]').map((a) => a.text()).join(' ')).toContain('Multiple Stalled Phases')
    expect(w.findAll('[data-testid="slm-validation-recommendation"]')).toHaveLength(1)
    expect(byId(w, 'slm-validation-trends-note').text()).toContain(L.trends.note)
    expect(byId(w, 'slm-validation-trends').text()).toContain(L.trends.series.maturity_trend)
    expect(byId(w, 'slm-validation-trends').text()).not.toContain(L.trends.series.phase_completion_trend)
  })

  it('says a phase with no score is not scored, never 0%', async () => {
    const w = await mountView()
    const rows = byId(w, 'slm-validation-phases').findAll('tbody tr')
    const unscored = rows.find((r) => r.text().includes('phase two'))
    expect(unscored?.text()).toContain(L.phases.notScored)
    expect(unscored?.text()).toContain('ci-gate')
    expect(unscored?.text()).not.toContain('0.0%')
  })

  it('says an alert-free, recommendation-free report has none', async () => {
    serve({ report: { ...report, alerts: [], recommendations: [] } })
    const w = await mountView()
    expect(byId(w, 'slm-validation-alerts-empty').text()).toBe(L.alerts.empty)
    expect(byId(w, 'slm-validation-recommendations-empty').text()).toBe(L.recommendations.empty)
  })

  it('shows a reading state until the report answers', async () => {
    client.get.mockImplementation(() => new Promise(() => {}))
    wrapper = mount(ValidationDashboard, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(byId(wrapper, 'slm-validation-loading').text()).toContain(L.loading)
    expect(byId(wrapper, 'slm-validation-overview').exists()).toBe(false)
  })

  it('says the read is empty when the report lists no phases, not that it failed', async () => {
    serve({ report: { ...report, phase_details: [] } })
    const w = await mountView()
    expect(byId(w, 'slm-validation-empty').text()).toContain(L.emptyTitle)
    expect(byId(w, 'slm-validation-error').exists()).toBe(false)
    expect(byId(w, 'slm-validation-overview').exists()).toBe(false)
  })

  it('says the report is empty when the route sent no report at all', async () => {
    serve({ report: null })
    const w = await mountView()
    expect(byId(w, 'slm-validation-empty').exists()).toBe(true)
  })

  it('says validation is not available on a 503, and offers no rebuild', async () => {
    client.get.mockRejectedValue(new HttpError(503, 'Service Unavailable'))
    const w = await mountView()
    expect(byId(w, 'slm-validation-unavailable').text()).toContain(L.unavailableTitle)
    expect(byId(w, 'slm-validation-error').exists()).toBe(false)
    expect(byId(w, 'slm-validation-generate').attributes('disabled')).toBeDefined()
  })

  it('says the read failed on any other error, and a refresh recovers', async () => {
    client.get.mockRejectedValueOnce(new HttpError(500, 'Internal Server Error'))
    const w = await mountView()
    expect(byId(w, 'slm-validation-error').text()).toContain(L.errorTitle)
    expect(byId(w, 'slm-validation-unavailable').exists()).toBe(false)
    serve()
    await byId(w, 'slm-validation-refresh').trigger('click')
    await flushPromises()
    expect(byId(w, 'slm-validation-error').exists()).toBe(false)
    expect(byId(w, 'slm-validation-overview').exists()).toBe(true)
  })

  it('POSTs /generate with the route defaults and says the rebuild started', async () => {
    client.post.mockResolvedValue({ status: 'initiated', message: 'Dashboard generation started in background', settings: {}, timestamp: 't' })
    const w = await mountView()
    await byId(w, 'slm-validation-generate').trigger('click')
    await flushPromises()
    expect(client.post).toHaveBeenCalledWith('/validation-dashboard/generate', {})
    expect(byId(w, 'slm-validation-generate-started').text()).toContain(L.generateStarted)
  })

  it('says the rebuild did not start when /generate fails, with the backend reason', async () => {
    client.post.mockRejectedValue(new HttpError(403, 'Forbidden', { detail: 'Admin permission required' }))
    const w = await mountView()
    await byId(w, 'slm-validation-generate').trigger('click')
    await flushPromises()
    expect(byId(w, 'slm-validation-generate-failed').exists()).toBe(true)
    expect(byId(w, 'slm-validation-generate-started').exists()).toBe(false)
  })
})
