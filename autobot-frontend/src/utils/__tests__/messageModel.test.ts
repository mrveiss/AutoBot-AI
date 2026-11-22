// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest'
import { shownModel } from '../internalMessage'

describe('shownModel (#21881)', () => {
  it('shows a real model', () => expect(shownModel({ model: 'llama3' })).toBe('llama3'))
  it.each([[{ model: 'unknown' }], [{ model: '' }], [{}], [null], [undefined], [{ model: 5 }]])(
    'shows no badge for %j',
    (metadata) => expect(shownModel(metadata as Record<string, unknown> | null | undefined)).toBe('')
  )
})
