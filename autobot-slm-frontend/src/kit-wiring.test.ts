// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Proof-of-wiring for the @autobot/ui shared kit into autobot-slm-frontend
// (#12019, #10860 Task D / PR-5). This is the ONLY consumer of @autobot/ui in
// SLM until PR-6 adopts the composables in views — its job is to prove the
// `file:` dependency + lockfile wiring resolves end-to-end (npm ci → import),
// so CI fails loudly if the kit link ever breaks. No view is touched here.

import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import {
  BaseButton,
  BaseBadge,
  BaseCard,
  BaseModal,
  EmptyState,
  usePagination,
  useFormValidation,
} from '@autobot/ui'
import CodeSourceModal from '@/components/CodeSourceModal.vue'

vi.mock('@/composables/useSlmApi', () => ({
  useSlmApi: () => ({ getNodes: vi.fn().mockResolvedValue([]) }),
}))
vi.mock('@/utils/ApiClient', () => ({ default: { post: vi.fn() } }))

describe('@autobot/ui kit wiring (#12019)', () => {
  it('resolves the file: dependency and exports the shared composables', () => {
    expect(typeof usePagination).toBe('function')
    expect(typeof useFormValidation).toBe('function')
  })

  it('resolves the shared Vue components from the kit', () => {
    expect(BaseButton).toBeDefined()
    expect(BaseBadge).toBeDefined()
    expect(BaseCard).toBeDefined()
    expect(BaseModal).toBeDefined()
    expect(EmptyState).toBeDefined()
  })

  it('renders a migrated SLM modal through the kit BaseModal (#14777)', async () => {
    const wrapper = mount(CodeSourceModal, {
      // BaseModal teleports to body; stub the teleport so the dialog renders inline
      global: { mocks: { $t: (key: string) => key }, stubs: { teleport: true } },
    })
    await flushPromises()
    const dialog = wrapper.find('[role="dialog"]')
    expect(dialog.exists()).toBe(true)
    expect(dialog.attributes('aria-modal')).toBe('true')
    expect(dialog.classes()).toContain('aui-dialog')
  })
})
