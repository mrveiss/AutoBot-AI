// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// ESLint test fixture for the #10025 `no-restricted-syntax` rule guarding
// ApiClient envelope misuse. Every line below MUST NOT trigger the rule.
//
// Covers the legitimate cases the rule must never false-positive on:
//   * the correct ApiClient usage (`const data = await ApiClient.get<T>(...)`)
//   * a real fetch/rawRequest Response `.json()` (those ARE Response objects)
//   * `.data` on non-ApiClient objects (Pinia state, refs, chart configs,
//     event payloads) and on the two-statement `payload.data` form
//
// To verify locally:
//   cd autobot-frontend
//   npx eslint --no-ignore eslint-tests/no-apiclient-envelope-misuse-allow.test.ts
//   # Expected: 0 errors

/* eslint-disable */

declare const ApiClient: any
declare const api: any
declare const apiClient: any
declare function fetch(url: string): Promise<{ json(): Promise<unknown> }>
declare function rawRequest(url: string): Promise<{ json(): Promise<unknown> }>

async function good() {
  // Correct usage: the awaited value IS the parsed payload.
  const data = await ApiClient.get<{ items: unknown[] }>('/x')
  const created = await api.post<unknown>('/x', {})
  await apiClient.delete('/x')

  // Real Response objects — these genuinely have .json().
  const fromFetch = (await fetch('/x')).json()
  const fromRaw = (await rawRequest('/x')).json()

  // .data on non-ApiClient objects is legitimate.
  const store = { data: { value: 1 } }
  const piniaData = store.data
  const chartRef = { value: { data: [] } }
  const chartData = chartRef.value.data
  const evt = { data: 'payload' }
  const eventData = evt.data

  // Two-statement form: the awaited value is bound first, then .data read.
  // The payload may itself legitimately have a `.data` field. Out of scope
  // for this syntactic rule (see eslint.config.ts comment), must stay allowed.
  const payload = await api.get<{ data: unknown }>('/x')
  const inner = payload.data

  // Named (non-verb) method on a *piClient-named object — not an HTTP verb,
  // so the rule must not fire.
  const visionMultimodalApiClient = { getVisionHealth: async () => ({ ok: true }) }
  const health = (await visionMultimodalApiClient.getVisionHealth()).ok

  return { data, created, fromFetch, fromRaw, piniaData, chartData, eventData, inner, health }
}

export { good }
