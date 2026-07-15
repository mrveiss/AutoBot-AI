// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Component tests for the reasoning-effort control in ChatSettingsModal.
 *
 * Issue #9531: e2e/component coverage for the reasoning-effort settings UI
 * added in #9460 / #9471.
 *
 * Scenarios:
 *  1. The control renders with all four options (Auto / Low / Medium / High).
 *  2. Selecting a value persists it via the shared preferences setter.
 *  3. The persisted value is reflected when the modal is reopened.
 *
 * The preferences plumbing (usePreferences) is mocked so the test asserts the
 * modal's wiring to the shared store without touching localStorage / the API.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { mount, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

// ── Module-level mocks (hoisted) ─────────────────────────────────────────────

vi.mock('@/composables/usePreferences', () => ({
  usePreferences: vi.fn(),
}))

vi.mock('@/components/ui/Icon.vue', () => ({
  default: { name: 'Icon', template: '<i class="icon-stub" />', props: ['name'] },
}))

// ── Imports after mocks ──────────────────────────────────────────────────────

import { usePreferences } from '@/composables/usePreferences'
import ChatSettingsModal from '../ChatSettingsModal.vue'

// ── Mock state ───────────────────────────────────────────────────────────────

// vue-i18n 11 requires app.use(); ChatSettingsModal uses useI18n() in
// <script setup>, so a bare $t mock is insufficient. Install a real i18n
// instance with empty messages + warnings off so t('key') returns the key
// verbatim (matching the assertions on translation keys below).
const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages: { en: {} },
  missingWarn: false,
  fallbackWarn: false,
})

// Shared reactive prefs state, mimicking the singleton composable.
const reasoningEffort = ref<'auto' | 'low' | 'medium' | 'high'>('auto')
const contextOverflowMode = ref<'auto' | 'warn' | 'disabled'>('auto')
const setReasoningEffort = vi.fn((v: 'auto' | 'low' | 'medium' | 'high') => {
  reasoningEffort.value = v
})
const setContextOverflowMode = vi.fn((v: 'auto' | 'warn' | 'disabled') => {
  contextOverflowMode.value = v
})

function mountModal(show = true): VueWrapper {
  return mount(ChatSettingsModal, {
    props: { show },
    global: {
      plugins: [i18n],
    },
  })
}

beforeEach(() => {
  reasoningEffort.value = 'auto'
  contextOverflowMode.value = 'auto'
  setReasoningEffort.mockClear()
  setContextOverflowMode.mockClear()
  vi.mocked(usePreferences).mockReturnValue({
    reasoningEffort,
    setReasoningEffort,
    contextOverflowMode,
    setContextOverflowMode,
  } as unknown as ReturnType<typeof usePreferences>)
})

// ── Tests ────────────────────────────────────────────────────────────────────

describe('ChatSettingsModal reasoning-effort control', () => {
  it('renders the reasoning-effort select with all four options', () => {
    const wrapper = mountModal()
    const select = wrapper.find('#reasoning-effort-select')
    expect(select.exists()).toBe(true)

    const values = select.findAll('option').map((o) => o.attributes('value'))
    expect(values).toEqual(['auto', 'low', 'medium', 'high'])
  })

  it('exposes an accessible label tied to the select', () => {
    const wrapper = mountModal()
    const label = wrapper.find('label[for="reasoning-effort-select"]')
    expect(label.exists()).toBe(true)
    expect(label.text()).toBe('chat.settings.reasoningEffortLabel')
  })

  it('persists the selected value via setReasoningEffort', async () => {
    const wrapper = mountModal()
    const select = wrapper.find('#reasoning-effort-select')

    await select.setValue('high')

    expect(setReasoningEffort).toHaveBeenCalledTimes(1)
    expect(setReasoningEffort).toHaveBeenCalledWith('high')
    expect(reasoningEffort.value).toBe('high')
  })

  it('reflects the persisted value when the modal is reopened', async () => {
    // First open: select medium (persists into shared state).
    const first = mountModal(true)
    await first.find('#reasoning-effort-select').setValue('medium')
    expect(reasoningEffort.value).toBe('medium')

    // Reopen flow: a closed modal that is then shown should sync local state
    // from the persisted preference.
    const second = mountModal(false)
    await second.setProps({ show: true })

    const select = second.find('#reasoning-effort-select')
    expect((select.element as HTMLSelectElement).value).toBe('medium')
  })

  it('defaults to auto when no preference is stored', () => {
    const wrapper = mountModal()
    const select = wrapper.find('#reasoning-effort-select')
    expect((select.element as HTMLSelectElement).value).toBe('auto')
  })
})
