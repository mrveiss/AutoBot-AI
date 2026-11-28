// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// useImageAnalysisHistory (#20644): the last 10 analyses, newest first, with every dropped or cleared
// preview URL revoked.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { effectScope } from 'vue'
import { IMAGE_ANALYSIS_HISTORY_LIMIT, useImageAnalysisHistory } from '../useImageAnalysisHistory'

const result = { success: true, result_id: 'r', modality: 'image', processing_time: 0, confidence: 1, result_data: {} }
const analysis = (name: string) => ({ file: new File(['x'], name), intent: 'analysis' as const, result })

describe('useImageAnalysisHistory (#20644)', () => {
  let n = 0
  beforeEach(() => {
    n = 0
    URL.createObjectURL = vi.fn(() => `blob:${++n}`)
    URL.revokeObjectURL = vi.fn()
  })

  it('keeps the newest first and no more than the limit, revoking what falls off', () => {
    const scope = effectScope()
    const history = scope.run(() => useImageAnalysisHistory())!
    for (let i = 1; i <= IMAGE_ANALYSIS_HISTORY_LIMIT + 2; i++) history.add(analysis(`f${i}.png`))
    expect(IMAGE_ANALYSIS_HISTORY_LIMIT).toBe(10)
    expect(history.entries.value).toHaveLength(10)
    expect(history.entries.value[0].file.name).toBe('f12.png')
    expect(history.entries.value[9].file.name).toBe('f3.png')
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(2)
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:1')
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:2')
    scope.stop()
  })

  it('revokes every preview when the screen goes away', () => {
    const scope = effectScope()
    const history = scope.run(() => useImageAnalysisHistory())!
    history.add(analysis('a.png'))
    history.add(analysis('b.png'))
    scope.stop()
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(2)
    expect(history.entries.value).toEqual([])
  })
})
