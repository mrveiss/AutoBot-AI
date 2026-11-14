// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The AI filter model hint never sits on "loading…" forever (#15502): once the
 * default-model fetch has failed, it names the server default instead.
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import CodebaseEnvironmentPanel from '../CodebaseEnvironmentPanel.vue'
import en from '@/i18n/locales/en.json'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const env = en.analytics.codebase.environment

function hint(aiFilteringModel: string | null, aiFilteringModelUnavailable: boolean) {
  const wrapper = mount(CodebaseEnvironmentPanel, {
    props: {
      analysis: null,
      loading: false,
      error: null,
      useAiFiltering: true,
      aiFilteringModelState: { model: aiFilteringModel, unavailable: aiFilteringModelUnavailable },
      aiFilteringPriority: 'high',
      llmFilteringResult: null,
    },
    global: { plugins: [i18n], stubs: { Icon: true, EmptyState: true } },
  })
  return wrapper.find('.ai-filter-model-hint').text()
}

describe('CodebaseEnvironmentPanel model hint (#15502)', () => {
  it('says loading while the model is pending', () => {
    expect(hint(null, false)).toContain(env.modelLoading)
  })

  it('names the server default once the fetch failed', () => {
    const text = hint(null, true)
    expect(text).toContain(env.modelServerDefault)
    expect(text).not.toContain(env.modelLoading)
  })

  it('names the served model when it is known', () => {
    expect(hint('served-by-the-backend:1b', false)).toContain('served-by-the-backend:1b')
  })
})
