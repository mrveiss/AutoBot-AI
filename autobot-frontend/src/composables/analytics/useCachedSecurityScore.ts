// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The one reader of `GET /api/code-intelligence/security/score/cached` (#18907, #20999).
 *
 * The route requires `source_id`, so the read is always source-scoped. Both
 * `useCodeIntelScores` (the page) and `useCodeIntelligence` delegate here; no other
 * composable may name the path (guarded by `useCachedSecurityScore.oneHome.test.ts`).
 */
import { ref, type Ref } from 'vue'
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import type {
  CachedSecurityScoreRaw,
  SecurityScoreResult,
} from '@/composables/analytics/codeIntelTypes'

export const CACHED_SECURITY_SCORE_PATH = '/api/code-intelligence/security/score/cached'

export interface UseCachedSecurityScoreOptions {
  withSourceId?: (url: string) => string
  /** Fired with the picked score and the full raw payload after a successful read. */
  onSuccess?: (score: SecurityScoreResult, raw: CachedSecurityScoreRaw) => void
}

/** Maps the raw payload; `null` for `no_data` so a prior result stays visible. */
export function pickCachedSecurityScore(r: CachedSecurityScoreRaw): SecurityScoreResult | null {
  if (r.status !== 'success' || r.security_score === undefined) return null
  return {
    security_score: r.security_score ?? 0,
    grade: r.grade ?? 'N/A',
    risk_level: r.risk_level ?? 'unknown',
    status_message: r.status_message ?? '',
    total_findings: r.total_findings ?? 0,
    critical_issues: r.critical_issues ?? 0,
    high_issues: r.high_issues ?? 0,
    files_analyzed: r.files_analyzed ?? 0,
    severity_breakdown: r.severity_breakdown ?? {},
    owasp_breakdown: r.owasp_breakdown ?? {},
  }
}

export function useCachedSecurityScore(options: UseCachedSecurityScoreOptions = {}) {
  /** The last answered payload, including `from_cache` and `completed_at`. */
  const raw: Ref<CachedSecurityScoreRaw | null> = ref(null)
  const endpoint = useFetchEndpoint<CachedSecurityScoreRaw, SecurityScoreResult>(
    {
      path: CACHED_SECURITY_SCORE_PATH,
      scopeToSource: true,
      label: 'Cached security score',
      // Recorded before the pick so a `no_data` answer is kept too, as callers saw it before.
      pickData: (payload) => {
        raw.value = payload
        return pickCachedSecurityScore(payload)
      },
      onSuccess: (picked, payload) => options.onSuccess?.(picked, payload),
    },
    { withSourceId: options.withSourceId },
  )
  return { ...endpoint, raw }
}
