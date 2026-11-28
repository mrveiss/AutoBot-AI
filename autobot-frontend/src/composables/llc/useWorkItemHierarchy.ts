// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The work-item hierarchy rules and the violation report of one company (#20936, umbrella #18978).
 *
 *   - `GET /api/llc/work-items/hierarchy-rules`       the parent-type rule table (any member)
 *   - `GET /api/llc/work-items/hierarchy-violations`  rows that already break it (company owners/admins and
 *                                                     platform admins; a 403 means the caller is neither)
 * Both are typed from the generated contract (`paths`). The server owns the rules and the admin gate: this adds
 * no access of its own, it only hides the report from a caller the server refuses (as StuckFileCleanupPanel does).
 */
import { computed, ref, type Ref } from 'vue'
import { isHttpError } from '@autobot/ui'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import type { paths } from '@/types/generated/api'

type Body<P extends keyof paths> = paths[P] extends {
  get: { responses: { 200: { content: { 'application/json': infer J } } } }
}
  ? J
  : never

const RULES_PATH = '/api/llc/work-items/hierarchy-rules' as const
const VIOLATIONS_PATH = '/api/llc/work-items/hierarchy-violations' as const

export type HierarchyRulesResponse = Body<typeof RULES_PATH>
export type HierarchyRule = HierarchyRulesResponse['rules'][number]
export type HierarchyViolationsResponse = Body<typeof VIOLATIONS_PATH>
export type HierarchyViolationRow = HierarchyViolationsResponse['violations'][number]

const logger = createLogger('useWorkItemHierarchy')

/**
 * 403: the caller is not a company or platform admin, so there is no report to show. A 401 is an expired
 * session, not a role: the shared client's 401 policy re-authenticates, and the section stays visible.
 */
export function isNotAdmin(err: unknown): boolean {
  return isHttpError(err) && err.status === 403
}

export function useWorkItemHierarchy(companyId: Readonly<Ref<string>>) {
  const api = useApiClient()
  const rules = ref<HierarchyRule[]>([])
  const violations = ref<HierarchyViolationRow[]>([])
  const rulesFailed = ref(false)
  const violationsFailed = ref(false)
  const reportRefused = ref(false)
  const truncated = ref(false)
  const reportChecked = ref(false) // until the server has answered, the report stays hidden: no flash for a member
  let rulesSeq = 0
  let violationsSeq = 0

  /** The answers belong to one company: drop them before the next company's request, so no old row shows. */
  function reset(): void {
    rulesSeq++
    violationsSeq++
    rules.value = []
    violations.value = []
    truncated.value = false
    rulesFailed.value = false
    violationsFailed.value = false
    reportRefused.value = false
    reportChecked.value = false
  }

  const url = (path: string) => `${path}?${new URLSearchParams({ company_id: companyId.value })}`

  async function loadRules(): Promise<void> {
    const seq = ++rulesSeq
    rulesFailed.value = false
    try {
      const res = (await api.get(url(RULES_PATH))) as HierarchyRulesResponse
      if (seq === rulesSeq) rules.value = res.rules ?? []
    } catch (err) {
      logger.error('Failed to load hierarchy rules', err)
      if (seq === rulesSeq) {
        rules.value = []
        rulesFailed.value = true
      }
    }
  }

  async function loadViolations(): Promise<void> {
    const seq = ++violationsSeq
    violationsFailed.value = false
    try {
      const res = (await api.get(url(VIOLATIONS_PATH))) as HierarchyViolationsResponse
      if (seq !== violationsSeq) return
      violations.value = res.violations ?? []
      truncated.value = res.truncated ?? false
      reportRefused.value = false
      reportChecked.value = true
    } catch (err) {
      if (seq !== violationsSeq) return
      violations.value = []
      truncated.value = false
      reportChecked.value = true
      reportRefused.value = isNotAdmin(err)
      violationsFailed.value = !reportRefused.value
      if (violationsFailed.value) logger.error('Failed to load hierarchy violations', err)
    }
  }

  const canSeeViolations = computed(() => reportChecked.value && !reportRefused.value)
  return {
    rules,
    violations,
    truncated,
    rulesFailed,
    violationsFailed,
    canSeeViolations,
    loadRules,
    loadViolations,
    reset,
  }
}
