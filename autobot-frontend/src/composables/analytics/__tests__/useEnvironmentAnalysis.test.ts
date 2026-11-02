// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The env-analysis AI filter model comes from the backend, never from a frontend
 * literal (#15502): null until fetched, and not sent while it is null.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, computed } from 'vue'
import { useEnvironmentAnalysis } from '../useEnvironmentAnalysis'
import type { UseCodeIntelAnalysisDeps } from '../codeIntelTypes'

const fetchWithAuth = vi.fn()
vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth: (...a: unknown[]) => fetchWithAuth(...a) }))
vi.mock('@/config/AppConfig.js', () => ({ default: { getServiceUrl: async () => 'http://backend' } }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() }),
}))

const SERVED = 'served-by-the-backend:1b'
const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body })
const DEFAULT_MODEL_PATH = '/env-analysis/default-model'

function deps(): UseCodeIntelAnalysisDeps {
  return {
    rootPath: ref('/src'),
    sourceIdParam: computed(() => ''),
    sourceIdQuery: computed(() => ({})),
    withSourceId: (u: string) => u,
  } as unknown as UseCodeIntelAnalysisDeps
}

function answer(modelResponse: () => unknown) {
  fetchWithAuth.mockImplementation(async (url: string) => {
    return String(url).includes(DEFAULT_MODEL_PATH) ? modelResponse() : ok({ status: 'no_data' })
  })
}

const analysisUrl = () =>
  String(fetchWithAuth.mock.calls.map((c) => c[0]).find((u: string) => !u.includes(DEFAULT_MODEL_PATH)))

describe('useEnvironmentAnalysis AI filter model (#15502)', () => {
  beforeEach(() => fetchWithAuth.mockReset())

  it('holds null until the backend names the model, then the served value', async () => {
    answer(() => ok({ model: SERVED }))
    const { aiFilteringModel } = useEnvironmentAnalysis(deps())
    expect(aiFilteringModel.value).toBeNull()
    await vi.waitFor(() => expect(aiFilteringModel.value).toBe(SERVED))
  })

  it('sends the served model as llm_model once it is known', async () => {
    answer(() => ok({ model: SERVED }))
    const a = useEnvironmentAnalysis(deps())
    await vi.waitFor(() => expect(a.aiFilteringModel.value).toBe(SERVED))
    a.useAiFiltering.value = true
    await a.loadEnvironmentAnalysis()
    expect(analysisUrl()).toContain(`llm_model=${encodeURIComponent(SERVED)}`)
  })

  it('omits llm_model while the model is still null (the backend applies its own default)', async () => {
    answer(() => ({ ok: false, status: 500, json: async () => ({}) }))
    const a = useEnvironmentAnalysis(deps())
    a.useAiFiltering.value = true
    await a.loadEnvironmentAnalysis()
    expect(a.aiFilteringModel.value).toBeNull()
    expect(analysisUrl()).toContain('use_llm_filter=true')
    expect(analysisUrl()).not.toContain('llm_model')
  })
  it('marks the model unavailable when the default-model fetch fails, instead of loading forever', async () => {
    answer(() => ({ ok: false, status: 500, json: async () => ({}) }))
    const a = useEnvironmentAnalysis(deps())
    expect(a.aiFilteringModelUnavailable.value).toBe(false)
    await vi.waitFor(() => expect(a.aiFilteringModelUnavailable.value).toBe(true))
    expect(a.aiFilteringModel.value).toBeNull()
  })

  it('marks the model unavailable when the backend answers with no model', async () => {
    answer(() => ok({ model: '' }))
    const a = useEnvironmentAnalysis(deps())
    await vi.waitFor(() => expect(a.aiFilteringModelUnavailable.value).toBe(true))
    expect(a.aiFilteringModel.value).toBeNull()
  })

  it('stays available once the backend names the model', async () => {
    answer(() => ok({ model: SERVED }))
    const a = useEnvironmentAnalysis(deps())
    await vi.waitFor(() => expect(a.aiFilteringModel.value).toBe(SERVED))
    expect(a.aiFilteringModelUnavailable.value).toBe(false)
  })
})
