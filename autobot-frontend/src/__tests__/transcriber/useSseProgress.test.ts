// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
import { describe, it, expect } from 'vitest'
import { useSseProgress } from '@/composables/transcriber/useSseProgress'

describe('useSseProgress', () => {
  it('initialises with 0 progress and idle status', () => {
    const { percent, step, status } = useSseProgress(1)
    expect(percent.value).toBe(0)
    expect(step.value).toBe('')
    expect(status.value).toBe('idle')
  })
})
