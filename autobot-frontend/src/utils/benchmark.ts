// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Benchmark helpers (Issue #9024).
 *
 * Pure functions shared by BenchmarkView.vue: rough cost estimation, CSV
 * serialization, and per-run aggregations. Kept out of the component so they
 * stay small and unit-testable.
 */

export interface BenchmarkResultRow {
  model: string
  content: string
  rating: number
  costUsd: number
  latencyMs: number
  error?: string
}

export interface BenchmarkRun {
  id: string
  prompt: string
  promptType: string
  promptSetId: string | null
  results: BenchmarkResultRow[]
  models: string[]
  createdAt: string
}

export interface PromptSet {
  id: string
  name: string
  promptType: string
  prompts: string[]
}

/**
 * Rough per-1k-token USD price by provider (input+output blended). Estimates
 * only — surfaced so the cost/quality scatter is meaningful; local providers
 * are effectively free.
 */
const PRICE_PER_1K: Record<string, number> = {
  openai: 0.005,
  anthropic: 0.006,
  google: 0.004,
  ollama: 0,
  vllm: 0,
}

/** Estimate cost from char counts (~4 chars/token) and a provider price table. */
export function estimateCostUsd(model: string, prompt: string, output: string): number {
  const provider = model.includes('/') ? model.split('/')[0].toLowerCase() : model.toLowerCase()
  const pricePer1k = PRICE_PER_1K[provider] ?? 0.003
  const tokens = (prompt.length + output.length) / 4
  return (tokens / 1000) * pricePer1k
}

/** Average non-zero star rating across a run's results (0 when none rated). */
export function avgQuality(run: BenchmarkRun): number {
  const rated = run.results.filter((r) => r.rating > 0)
  if (!rated.length) return 0
  return rated.reduce((sum, r) => sum + r.rating, 0) / rated.length
}

/** Sum of estimated cost across a run's results. */
export function totalCost(run: BenchmarkRun): number {
  return run.results.reduce((sum, r) => sum + (r.costUsd || 0), 0)
}

function csvCell(value: string | number): string {
  const s = String(value).replace(/"/g, '""')
  return `"${s}"`
}

/** Serialize the current result rows to CSV text. */
export function toCsv(rows: BenchmarkResultRow[], prompt: string, promptType: string): string {
  const header = ['prompt', 'prompt_type', 'model', 'rating', 'cost_usd', 'error', 'content']
  const lines = [header.map(csvCell).join(',')]
  for (const r of rows) {
    lines.push(
      [prompt, promptType, r.model, r.rating, r.costUsd.toFixed(6), r.error ?? '', r.content]
        .map(csvCell)
        .join(','),
    )
  }
  return lines.join('\n')
}
