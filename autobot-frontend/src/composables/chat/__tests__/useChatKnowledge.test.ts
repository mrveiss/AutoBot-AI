// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { describe, it, expect, afterEach } from 'vitest'
import { useChatKnowledge } from '../useChatKnowledge'

afterEach(() => {
  useChatKnowledge().enabled.value = true
})

describe('useChatKnowledge', () => {
  it('is on by default, as the composer toggle was', () => {
    expect(useChatKnowledge().enabled.value).toBe(true)
  })

  it('shares one state between every caller (composer and header)', () => {
    const composer = useChatKnowledge()
    const header = useChatKnowledge()
    composer.enabled.value = false
    expect(header.enabled.value).toBe(false)
  })
})
