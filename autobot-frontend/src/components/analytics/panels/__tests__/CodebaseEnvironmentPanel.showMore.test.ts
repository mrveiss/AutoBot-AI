// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #12741: the environment route caps its sample list on the SERVER (50 hardcoded values, 20
 * recommendations) and reports the real totals. Pressing "show more" cannot reach rows that are
 * not in the payload, so past the cap the panel says so honestly and offers no button.
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import CodebaseEnvironmentPanel from '../CodebaseEnvironmentPanel.vue'
import en from '@/i18n/locales/en.json'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

const hv = (n: number) =>
  Array.from({ length: n }, (_, i) => ({
    file: `f${i}.py`, line: i, value: `v${i}`, type: 'url', severity: 'high', suggested_env_var: `V${i}`,
  }))

function mountPanel(held: number, total: number) {
  return mount(CodebaseEnvironmentPanel, {
    props: {
      analysis: {
        total_hardcoded_values: total,
        high_priority_count: 0,
        recommendations_count: 0,
        categories: {},
        analysis_time_seconds: 1,
        hardcoded_values: hv(held),
        recommendations: [],
      },
      loading: false,
      error: null,
      useAiFiltering: false,
      aiFilteringModelState: { model: null, unavailable: false },
      aiFilteringPriority: 'high',
      llmFilteringResult: null,
    },
    global: { plugins: [i18n], stubs: { Icon: true, EmptyState: true } },
  })
}

describe('CodebaseEnvironmentPanel sample list: client expansion, then the server cap (#12741)', () => {
  it('expands what the panel holds, then states the server limit with no button', async () => {
    const w = mountPanel(20, 1947)
    const rows = () => w.findAll('.hardcoded-item')
    expect(rows()).toHaveLength(8)

    await w.get('[data-testid="truncation-show-more"]').trigger('click')
    expect(rows()).toHaveLength(16)
    await w.get('[data-testid="truncation-show-more"]').trigger('click')
    expect(rows()).toHaveLength(20)

    // Everything held is visible; the remaining 1,927 are not in the payload.
    expect(w.find('[data-testid="truncation-show-more"]').exists()).toBe(false)
    const note = w.get('[data-testid="truncation-server-limited"]')
    expect(note.text()).toBe('Showing the top 20 of 1,947. The server limits this list, so the rest cannot be loaded here.')
  })

  it('shows no server-limit note when the server returned everything', () => {
    const w = mountPanel(5, 5)
    expect(w.find('[data-testid="truncation-server-limited"]').exists()).toBe(false)
  })
})
