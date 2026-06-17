// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// ESLint test fixture for the #10025 `no-restricted-syntax` rule guarding
// ApiClient envelope misuse. Every `// EXPECT-ERROR` line below SHOULD trigger
// the rule: ApiClient returns PARSED JSON directly, so calling `.json()` on the
// awaited result, or reading `.data` off it, is always a bug.
//
// Wire-in: this fixture is excluded from the production lint step (see
// eslint.config.ts ignore list); it exists only for manual verification.
//
// To verify locally:
//   cd autobot-frontend
//   npx eslint --no-ignore eslint-tests/no-apiclient-envelope-misuse-deny.test.ts
//   # Expected: 10 errors (one per `// EXPECT-ERROR` line)

/* eslint-disable */

declare const ApiClient: any
declare const api: any
declare const apiClient: any

async function bad() {
  // EXPECT-ERROR: .json() on ApiClient.get result
  const a = (await ApiClient.get<unknown>('/x')).json()

  // EXPECT-ERROR: .json() on api.post result (useApiClient() local named `api`)
  const b = (await api.post('/x', {})).json()

  // EXPECT-ERROR: .json() on apiClient.put result
  const c = (await apiClient.put('/x', {})).json()

  // EXPECT-ERROR: .data on ApiClient.get result (axios-envelope pattern)
  const d = (await ApiClient.get<{ data: unknown }>('/x')).data

  // EXPECT-ERROR: .data on api.post result
  const e = (await api.post('/x', {})).data

  // EXPECT-ERROR: .data on apiClient.delete result
  const f = (await apiClient.delete('/x')).data

  // EXPECT-ERROR: .data on api.patch result
  const g = (await api.patch('/x', {})).data

  // EXPECT-ERROR: .json() on api.delete result
  const h = (await api.delete('/x')).json()

  // EXPECT-ERROR: .data on ApiClient.put result
  const i = (await ApiClient.put('/x', {})).data

  // EXPECT-ERROR: .json() on apiClient.get result
  const j = (await apiClient.get('/x')).json()

  return { a, b, c, d, e, f, g, h, i, j }
}

export { bad }
