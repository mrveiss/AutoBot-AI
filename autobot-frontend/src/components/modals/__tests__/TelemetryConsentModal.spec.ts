// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Component tests for the first-run telemetry consent modal.
 *
 * Issue #12334: the modal was mounted unconditionally in App.vue, so it rendered
 * over the login form on the unauthenticated route — intercepting pointer events
 * (Sign In unclickable) and 401'ing its persistence calls, which re-nagged
 * forever. The fix gates the mount behind `userStore.isAuthenticated`
 * (`<TelemetryConsentModal v-if="userStore.isAuthenticated" />`), deferring the
 * prompt until after successful login where its authenticated endpoints work.
 *
 * These tests reproduce that gating contract with a tiny wrapper that mirrors
 * App.vue's `v-if`, asserting:
 *   1. Unauthenticated → the modal is never mounted, so no telemetry status
 *      call fires and nothing can overlay the login form.
 *   2. Authenticated + server reports "not yet shown" → the consent prompt
 *      appears at the correct time (the flow still fires, no feature loss).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

// ── Module-level mocks (hoisted) ─────────────────────────────────────────────

const apiGet = vi.fn()
const apiPost = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get: apiGet, post: apiPost }),
}))

vi.mock('@/components/ui/Icon.vue', () => ({
  default: { name: 'Icon', template: '<i class="icon-stub" />', props: ['name'] },
}))

// Stub BaseModal so its visibility is observable from the DOM: it renders its
// body slot only when `modelValue` (the modal's `isVisible`) is true.
vi.mock('@autobot/ui', () => ({
  BaseModal: {
    name: 'BaseModal',
    props: ['modelValue', 'title'],
    template: '<div v-if="modelValue" class="telemetry-modal-stub"><slot /></div>',
  },
}))

// ── Imports after mocks ──────────────────────────────────────────────────────

import TelemetryConsentModal from '../TelemetryConsentModal.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages: { en: {} },
  missingWarn: false,
  fallbackWarn: false,
})

// Wrapper mirroring App.vue's gate: `<TelemetryConsentModal v-if="isAuthenticated" />`.
function mountGated(isAuthenticated: boolean) {
  const authed = ref(isAuthenticated)
  const Wrapper = defineComponent({
    setup() {
      return () => (authed.value ? h(TelemetryConsentModal) : null)
    },
  })
  const wrapper = mount(Wrapper, { global: { plugins: [i18n] } })
  return { wrapper, authed }
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  apiPost.mockResolvedValue({})
})

describe('TelemetryConsentModal gating (#12334)', () => {
  it('is not mounted while unauthenticated and never calls the telemetry status endpoint', async () => {
    const { wrapper } = mountGated(false)
    await nextTick()
    await nextTick()

    expect(wrapper.find('.telemetry-modal-stub').exists()).toBe(false)
    // The pre-auth 401 storm came from this call — it must not fire on login.
    expect(apiGet).not.toHaveBeenCalled()
  })

  it('shows the consent prompt once authenticated when the server reports it has not been shown', async () => {
    apiGet.mockResolvedValue({
      enabled: false,
      anonymous_usage_stats: false,
      first_run_prompt_shown: false,
    })

    const { wrapper } = mountGated(true)
    await nextTick()
    await nextTick()

    expect(apiGet).toHaveBeenCalledWith('/api/settings/telemetry')
    expect(wrapper.find('.telemetry-modal-stub').exists()).toBe(true)
  })

  it('stays hidden once authenticated when the server reports the prompt was already shown', async () => {
    apiGet.mockResolvedValue({
      enabled: true,
      anonymous_usage_stats: true,
      first_run_prompt_shown: true,
    })

    const { wrapper } = mountGated(true)
    await nextTick()
    await nextTick()

    expect(wrapper.find('.telemetry-modal-stub').exists()).toBe(false)
  })
})
