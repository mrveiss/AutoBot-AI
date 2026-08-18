// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * describeApiError (#14549)
 *
 * Extracted out of `RolesView.vue`'s local `describeError` so `OrgChart.vue`
 * can surface the same server reason on a failed mutation instead of
 * reinventing the extraction (repo rule 2: reuse, never fork).
 *
 * `ApiClient` throws a plain `Error` whose message is already
 * `HTTP <status>: <detail>` — it extracts `detail` itself
 * (`utils/ApiClient.ts` `_extractErrorInfo`). It is NOT axios-shaped, so
 * reading `error.response.data.detail` would silently always miss and this
 * function would return the fallback every time while looking like it
 * worked.
 */
export function describeApiError(error: unknown, fallback: string): string {
  const message = error instanceof Error ? error.message : ''
  return message.length > 0 ? message : fallback
}
