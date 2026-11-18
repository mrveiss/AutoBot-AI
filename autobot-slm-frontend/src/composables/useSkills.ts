// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Skills Management Composable (Issue #731)
 *
 * Provides reactive state and methods for managing the Skills system
 * via the AutoBot user backend API.
 */

import { ref, computed, readonly, onUnmounted } from 'vue'
import { useAutobotApi, autobotApiErrorMessage } from '@/composables/useAutobotApi'
import { useDashboardPoller } from '@/composables/useDashboardPoller'
import i18n from '@/i18n'
import { SKILL_APPROVAL_POLL_TIMEOUT_MS } from '@/constants/api-timeouts'

// =============================================================================
// Type Definitions
// =============================================================================
//
// The shapes below now live beside the canonical autobot-backend client
// (`useAutobotApi.ts`) per ADR-008 decision rule 3, together with the
// `/skills/...` paths that produce them. They are re-exported here unchanged so
// every existing consumer (`SkillsView.vue`, `ReposTab.vue`, `ApprovalsTab.vue`)
// keeps importing them from this module.
// =============================================================================

import type {
  SkillConfigField,
  SkillInfo,
  SkillDetail,
  SkillHealth,
  SkillListResponse,
  CategoryCounts,
  SkillRepo,
  SkillApproval,
  GovernanceConfig,
} from '@/composables/useAutobotApi'

export type {
  SkillConfigField,
  SkillInfo,
  SkillDetail,
  SkillHealth,
  SkillListResponse,
  CategoryCounts,
  SkillRepo,
  SkillApproval,
  GovernanceConfig,
}

// =============================================================================
// Composable
// =============================================================================

export function useSkills() {
  // Transport: the canonical autobot-backend client (#13079). This composable
  // used to own `axios.create({ baseURL: getBackendUrl() + '/skills/', timeout:
  // 15000 })` with an interceptor that attached only `Bearer
  // ${authStore.token}` — so with an autobot-issued token and no SLM token it
  // 401'd where every tool on `useAutobotApi` worked. The client supplies the
  // `autobot_access_token` fallback (useAutobotApi.ts:418), the 401 cleanup
  // (:429-432), a 30s timeout (:412) and shared base-URL resolution (:408).
  const api = useAutobotApi()
  const skills = ref<SkillInfo[]>([])
  const categories = ref<string[]>([])
  const categoryCounts = ref<Record<string, number>>({})
  const selectedSkill = ref<SkillDetail | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const initialized = ref(false)

  // --- Computed ---

  const enabledSkills = computed(() =>
    skills.value.filter((s) => s.enabled)
  )

  const disabledSkills = computed(() =>
    skills.value.filter((s) => !s.enabled)
  )

  const skillsByCategory = computed(() => {
    const grouped: Record<string, SkillInfo[]> = {}
    for (const skill of skills.value) {
      const cat = skill.category
      if (!grouped[cat]) grouped[cat] = []
      grouped[cat].push(skill)
    }
    return grouped
  })

  // --- Actions ---

  async function fetchSkills(
    category?: string,
    search?: string
  ): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const data = await api.getSkills({ category, search })
      skills.value = data.skills
      categories.value = data.categories
    } catch (err: unknown) {
      error.value = _extractError(err)
    } finally {
      loading.value = false
    }
  }

  async function fetchCategories(): Promise<void> {
    try {
      const data = await api.getSkillCategories()
      categoryCounts.value = data.categories
    } catch (err: unknown) {
      error.value = _extractError(err)
    }
  }

  async function fetchSkillDetail(name: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      selectedSkill.value = await api.getSkillDetail(name)
    } catch (err: unknown) {
      error.value = _extractError(err)
    } finally {
      loading.value = false
    }
  }

  async function enableSkill(name: string): Promise<boolean> {
    try {
      await api.enableSkill(name)
      await fetchSkills()
      return true
    } catch (err: unknown) {
      error.value = _extractError(err)
      return false
    }
  }

  async function disableSkill(name: string): Promise<boolean> {
    try {
      await api.disableSkill(name)
      await fetchSkills()
      return true
    } catch (err: unknown) {
      error.value = _extractError(err)
      return false
    }
  }

  async function updateConfig(
    name: string,
    config: Record<string, unknown>
  ): Promise<boolean> {
    try {
      await api.updateSkillConfig(name, config)
      if (selectedSkill.value?.name === name) {
        await fetchSkillDetail(name)
      }
      return true
    } catch (err: unknown) {
      error.value = _extractError(err)
      return false
    }
  }

  async function initializeSkills(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      await api.initializeSkills()
      initialized.value = true
      await fetchSkills()
      await fetchCategories()
    } catch (err: unknown) {
      error.value = _extractError(err)
    } finally {
      loading.value = false
    }
  }

  return {
    // State
    skills: readonly(skills),
    categories: readonly(categories),
    categoryCounts: readonly(categoryCounts),
    selectedSkill: readonly(selectedSkill),
    loading: readonly(loading),
    error: readonly(error),
    initialized: readonly(initialized),

    // Computed
    enabledSkills,
    disabledSkills,
    skillsByCategory,

    // Actions
    fetchSkills,
    fetchCategories,
    fetchSkillDetail,
    enableSkill,
    disableSkill,
    updateConfig,
    initializeSkills,
  }
}


// =============================================================================
// Helpers
// =============================================================================

const t = i18n.global.t.bind(i18n.global)

/** How often the approval poll runs (Issue #951). */
const APPROVAL_POLL_INTERVAL_MS = 30_000

function _extractError(err: unknown): string {
  // `autobotApiErrorMessage` is the one implementation of the FastAPI
  // `{ detail }` unwrap this used to hand-roll via `axios.isAxiosError`. Its
  // fallback chain is the `HttpError` detail, then `err.message`.
  return autobotApiErrorMessage(err, t('skills.errors.generic'))
}

// =============================================================================
// useSkillGovernance Composable
// =============================================================================

export function useSkillGovernance() {
  // Transport: the canonical autobot-backend client (#13079). This composable
  // used to own a second, bare `axios.create({ timeout: 15000 })` — no baseURL
  // (every call site pasted `getBackendUrl()` in), an `authStore.token`-only
  // interceptor and no 401 cleanup.
  const api = useAutobotApi()
  const repos = ref<SkillRepo[]>([])
  const approvals = ref<SkillApproval[]>([])
  const drafts = ref<Record<string, unknown>[]>([])
  const governanceConfig = ref<GovernanceConfig | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const newDraftNotification = ref<string | null>(null)

  async function fetchRepos(): Promise<void> {
    loading.value = true
    try {
      repos.value = await api.getSkillRepos()
    } catch (e: unknown) {
      error.value = autobotApiErrorMessage(e, t('skills.errors.fetchReposFailed'))
    } finally {
      loading.value = false
    }
  }

  async function addRepo(
    payload: Omit<SkillRepo, 'id' | 'skill_count' | 'status' | 'last_synced'>,
  ): Promise<unknown> {
    try {
      const data = await api.addSkillRepo(payload)
      await fetchRepos()
      return data
    } catch (e: unknown) {
      error.value = autobotApiErrorMessage(e, t('skills.errors.addRepoFailed'))
      throw e
    }
  }

  async function syncRepo(repoId: string): Promise<unknown> {
    try {
      const data = await api.syncSkillRepo(repoId)
      await fetchRepos()
      return data
    } catch (e: unknown) {
      error.value = autobotApiErrorMessage(e, t('skills.errors.syncRepoFailed'))
      throw e
    }
  }

  /** GET /skills/governance/approvals (interactive read, client default budget). */
  async function fetchApprovals(): Promise<void> {
    try {
      approvals.value = await api.getSkillApprovals()
    } catch (e: unknown) {
      error.value = autobotApiErrorMessage(e, t('skills.errors.fetchApprovalsFailed'))
    }
  }

  async function decideApproval(
    approvalId: string,
    approved: boolean,
    trustLevel = 'monitored',
    notes = '',
  ): Promise<void> {
    try {
      await api.decideSkillApproval(approvalId, {
        approved,
        notes,
        trust_level: trustLevel,
      })
      await fetchApprovals()
    } catch (e: unknown) {
      error.value = autobotApiErrorMessage(e, t('skills.errors.processApprovalFailed'))
    }
  }

  async function fetchDrafts(): Promise<void> {
    try {
      const data = await api.getSkillDrafts()
      drafts.value = Array.isArray(data) ? data : []
    } catch (e: unknown) {
      error.value = autobotApiErrorMessage(e, t('skills.errors.fetchDraftsFailed'))
    }
  }

  async function testDraft(skillId: string): Promise<unknown> {
    try {
      return await api.testSkillDraft(skillId)
    } catch (e: unknown) {
      error.value = autobotApiErrorMessage(e, t('skills.errors.testDraftFailed'))
      throw e
    }
  }

  async function promoteDraft(skillId: string): Promise<unknown> {
    try {
      const data = await api.promoteSkillDraft(skillId)
      await fetchDrafts()
      return data
    } catch (e: unknown) {
      error.value = autobotApiErrorMessage(e, t('skills.errors.promoteDraftFailed'))
      throw e
    }
  }

  async function fetchGovernance(): Promise<void> {
    try {
      governanceConfig.value = await api.getSkillGovernance()
    } catch (e: unknown) {
      error.value = autobotApiErrorMessage(e, t('skills.errors.fetchGovernanceFailed'))
    }
  }

  async function setGovernanceMode(mode: GovernanceConfig['mode']): Promise<void> {
    try {
      await api.updateSkillGovernanceMode(mode)
      await fetchGovernance()
    } catch (e: unknown) {
      error.value = autobotApiErrorMessage(e, t('skills.errors.updateGovernanceModeFailed'))
    }
  }

  /**
   * Issue #951: one approval read per tick. A failure is recorded in `error` and rethrown, so
   * the shared dashboard poller (#19482) counts it and pauses after the consecutive-error limit.
   */
  async function pollApprovals(): Promise<void> {
    const prev = approvals.value.length
    try {
      approvals.value = await api.getSkillApprovals(SKILL_APPROVAL_POLL_TIMEOUT_MS)
    } catch (e: unknown) {
      error.value = autobotApiErrorMessage(e, t('skills.errors.fetchApprovalsFailed'))
      throw e
    }
    const curr = approvals.value.length
    if (curr > prev) {
      const newest = approvals.value[approvals.value.length - 1]
      newDraftNotification.value = t('skills.newDraftNotification', {
        skillId: newest?.skill_id ?? t('skills.unknownSkill'),
      })
    }
  }

  /** Poll for new autonomous-generated approvals every 30s; pauses after repeated failures. */
  const approvalPoller = useDashboardPoller(pollApprovals, APPROVAL_POLL_INTERVAL_MS)

  function startApprovalPolling(): void {
    if (approvalPoller.isPolling.value) return
    approvalPoller.start('')
  }

  function stopApprovalPolling(): void {
    approvalPoller.stop()
  }

  function dismissDraftNotification(): void {
    newDraftNotification.value = null
  }

  onUnmounted(stopApprovalPolling)

  return {
    repos: readonly(repos),
    approvals: readonly(approvals),
    drafts: readonly(drafts),
    governanceConfig: readonly(governanceConfig),
    loading: readonly(loading),
    error: readonly(error),
    newDraftNotification: readonly(newDraftNotification),
    fetchRepos,
    addRepo,
    syncRepo,
    fetchApprovals,
    decideApproval,
    fetchDrafts,
    testDraft,
    promoteDraft,
    fetchGovernance,
    setGovernanceMode,
    approvalPoller,
    startApprovalPolling,
    stopApprovalPolling,
    dismissDraftNotification,
  }
}
