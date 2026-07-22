// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Proof-of-wiring for the @autobot/ui shared kit into autobot-slm-frontend
// (#12019, #10860 Task D / PR-5). This is the ONLY consumer of @autobot/ui in
// SLM until PR-6 adopts the composables in views — its job is to prove the
// `file:` dependency + lockfile wiring resolves end-to-end (npm ci → import),
// so CI fails loudly if the kit link ever breaks. No view is touched here.

import { describe, it, expect } from 'vitest'
import {
  BaseButton,
  BaseBadge,
  BaseCard,
  BaseModal,
  EmptyState,
  usePagination,
  useFormValidation,
} from '@autobot/ui'

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
})
