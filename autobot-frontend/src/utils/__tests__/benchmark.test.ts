// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/** Unit tests for benchmark helpers (Issue #9024). */

import { describe, it, expect } from 'vitest'
import {
  estimateCostUsd,
  toCsv,
  avgQuality,
  totalCost,
  type BenchmarkResultRow,
  type BenchmarkRun,
} from '@/utils/benchmark'

function row(over: Partial<BenchmarkResultRow> = {}): BenchmarkResultRow {
  return { model: 'openai/gpt-4o', content: 'hi', rating: 4, costUsd: 0.01, latencyMs: 0, ...over }
}

function run(over: Partial<BenchmarkRun> = {}): BenchmarkRun {
  return {
    id: 'r',
    prompt: 'p',
    promptType: 'code',
    promptSetId: null,
    results: [row()],
    models: ['openai/gpt-4o'],
    createdAt: '2025-01-01T00:00:00+00:00',
    ...over,
  }
}

describe('estimateCostUsd', () => {
  it('charges for paid providers', () => {
    const cost = estimateCostUsd('openai/gpt-4o', 'a'.repeat(4000), 'b'.repeat(4000))
    expect(cost).toBeGreaterThan(0)
  })

  it('is free for local providers', () => {
    expect(estimateCostUsd('ollama/llama3', 'x'.repeat(8000), 'y'.repeat(8000))).toBe(0)
  })

  it('falls back to a default price for unknown providers', () => {
    expect(estimateCostUsd('mystery/model', 'x'.repeat(4000), '')).toBeGreaterThan(0)
  })
})

describe('avgQuality', () => {
  it('averages only rated results', () => {
    const r = run({ results: [row({ rating: 2 }), row({ rating: 4 }), row({ rating: 0 })] })
    expect(avgQuality(r)).toBe(3)
  })

  it('returns 0 when nothing is rated', () => {
    expect(avgQuality(run({ results: [row({ rating: 0 })] }))).toBe(0)
  })
})

describe('totalCost', () => {
  it('sums result costs', () => {
    expect(totalCost(run({ results: [row({ costUsd: 0.02 }), row({ costUsd: 0.03 })] }))).toBeCloseTo(0.05)
  })
})

describe('toCsv', () => {
  it('emits a header and one row per result', () => {
    const csv = toCsv([row({ model: 'openai/gpt-4o' })], 'my prompt', 'code')
    const lines = csv.split('\n')
    expect(lines).toHaveLength(2)
    expect(lines[0]).toContain('model')
    expect(lines[1]).toContain('openai/gpt-4o')
  })

  it('escapes embedded quotes', () => {
    const csv = toCsv([row({ content: 'he said "hi"' })], 'p', 'code')
    expect(csv).toContain('"he said ""hi"""')
  })
})
