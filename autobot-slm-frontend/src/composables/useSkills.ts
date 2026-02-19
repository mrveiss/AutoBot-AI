// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Skills Management Composable (Issue #731)
 *
 * Provides reactive state and methods for managing the Skills system
 * via the AutoBot user backend API.
 */

import { ref, computed, readonly, onUnmounted } from 'vue'
import axios from 'axios'
import { useAuthStore } from '@/stores/auth'

// Skills API is on the main AutoBot backend, proxied via nginx
const API_BASE = '/autobot-api/skills/'

// =============================================================================
// Type Definitions
// =============================================================================

export interface SkillConfigField {
  type: string
  default: unknown
  description: string
  required: boolean
  choices: string[] | null
}

export interface SkillInfo {
  name: string
  version: string
  description: string
  author: string
  category: string
  status: string
  enabled: boolean
  tools: readonly string[]
  triggers: readonly string[]
  dependencies: readonly string[]
  tags: readonly string[]
}

export interface SkillDetail extends SkillInfo {
  config_schema: Record<string, SkillConfigField>
  current_config: Record<string, unknown>
  health: SkillHealth
}

export interface SkillHealth {
  name: string
  status: string
  version: string
  message: string | null
  last_checked: string
  config_valid: boolean
  dependencies_met: boolean
  details: Record<string, unknown>
}

export interface SkillListResponse {
  skills: SkillInfo[]
  total: number
  categories: string[]
}

export interface CategoryCounts {
  categories: Record<string, number>
}

// =============================================================================
// Composable
// =============================================================================

export function useSkills() {
  const authStore = useAuthStore()
  const skills = ref<SkillInfo[]>([])
  const categories = ref<string[]>([])
  const categoryCounts = ref<Record<string, number>>({})
  const selectedSkill = ref<SkillDetail | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const initialized = ref(false)

  const api = axios.create({
    baseURL: API_BASE,
    timeout: 15000,
  })

  api.interceptors.request.use((config) => {
    const token = authStore.token
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })

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
      const params: Record<string, string> = {}
      if (category) params.category = category
      if (search) params.search = search
      const { data } = await api.get<SkillListResponse>('/', { params })
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
      const { data } = await api.get<CategoryCounts>('/categories')
      categoryCounts.value = data.categories
    } catch (err: unknown) {
      error.value = _extractError(err)
    }
  }

  async function fetchSkillDetail(name: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const { data } = await api.get<SkillDetail>(`/${name}`)
      selectedSkill.value = data
    } catch (err: unknown) {
      error.value = _extractError(err)
    } finally {
      loading.value = false
    }
  }

  async function enableSkill(name: string): Promise<boolean> {
    try {
      await api.post(`/${name}/enable`)
      await fetchSkills()
      return true
    } catch (err: unknown) {
      error.value = _extractError(err)
      return false
    }
  }

  async function disableSkill(name: string): Promise<boolean> {
    try {
      await api.post(`/${name}/disable`)
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
      await api.put(`/${name}/config`, { config })
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
      await api.post('/initialize')
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

function _extractError(err: unknown): string {
  if (axios.isAxiosError(err)) {
    return err.response?.data?.detail || err.message
  }
  return String(err)
}

// =============================================================================
// Skill Governance Types
// =============================================================================

export interface SkillRepo {
  id: string
  name: string
  url: string
  repo_type: 'git' | 'local' | 'http' | 'mcp'
  skill_count: number
  status: string
  last_synced: string | null
}

export interface SkillApproval {
  id: string
  skill_id: string
  requested_by: string
  requested_at: string
  reason: string
  status: 'pending' | 'approved' | 'rejected'
  notes: string | null
}

export interface GovernanceConfig {
  mode: 'full_auto' | 'semi_auto' | 'locked'
  gap_detection_enabled: boolean
  default_trust_level: string
}

// Governance API base — hits main backend via SLM nginx proxy
const SKILLS_REPOS_BASE = '/autobot-api/skills/repos'
const SKILLS_GOV_BASE = '/autobot-api/skills/governance'

// =============================================================================
// useSkillGovernance Composable
// =============================================================================

export function useSkillGovernance() {
  const authStore = useAuthStore()
  const repos = ref<SkillRepo[]>([])
  const approvals = ref<SkillApproval[]>([])
  const drafts = ref<Record<string, unknown>[]>([])
  const governanceConfig = ref<GovernanceConfig | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const newDraftNotification = ref<string | null>(null)
  let _pollTimer: ReturnType<typeof setInterval> | null = null

  const api = axios.create({ timeout: 15000 })
  api.interceptors.request.use((config) => {
    const token = authStore.token
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })

  async function fetchRepos(): Promise<void> {
    loading.value = true
    try {
      const { data } = await api.get<SkillRepo[]>(SKILLS_REPOS_BASE)
      repos.value = data
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch repos'
    } finally {
      loading.value = false
    }
  }

  async function addRepo(
    payload: Omit<SkillRepo, 'id' | 'skill_count' | 'status' | 'last_synced'>,
  ): Promise<unknown> {
    try {
      const { data } = await api.post(SKILLS_REPOS_BASE, payload)
      await fetchRepos()
      return data
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to add repo'
      throw e
    }
  }

  async function syncRepo(repoId: string): Promise<unknown> {
    try {
      const { data } = await api.post(`${SKILLS_REPOS_BASE}/${repoId}/sync`)
      await fetchRepos()
      return data
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to sync repo'
      throw e
    }
  }

  async function fetchApprovals(): Promise<void> {
    try {
      const { data } = await api.get<SkillApproval[]>(`${SKILLS_GOV_BASE}/approvals`)
      approvals.value = data
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch approvals'
    }
  }

  async function decideApproval(
    approvalId: string,
    approved: boolean,
    trustLevel = 'monitored',
    notes = '',
  ): Promise<void> {
    try {
      await api.post(`${SKILLS_GOV_BASE}/approvals/${approvalId}`, {
        approved,
        notes,
        trust_level: trustLevel,
      })
      await fetchApprovals()
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to process approval'
    }
  }

  async function fetchDrafts(): Promise<void> {
    try {
      const { data } = await api.get<Record<string, unknown>[]>(`${SKILLS_GOV_BASE}/drafts`)
      drafts.value = Array.isArray(data) ? data : []
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch drafts'
    }
  }

  async function testDraft(skillId: string): Promise<unknown> {
    try {
      const { data } = await api.post(`${SKILLS_GOV_BASE}/drafts/${skillId}/test`)
      return data
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Test draft failed'
      throw e
    }
  }

  async function promoteDraft(skillId: string): Promise<unknown> {
    try {
      const { data } = await api.post(`${SKILLS_GOV_BASE}/drafts/${skillId}/promote`)
      await fetchDrafts()
      return data
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to promote draft'
      throw e
    }
  }

  async function fetchGovernance(): Promise<void> {
    try {
      const { data } = await api.get<GovernanceConfig>(`${SKILLS_GOV_BASE}/`)
      governanceConfig.value = data
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch governance config'
    }
  }

  async function setGovernanceMode(mode: GovernanceConfig['mode']): Promise<void> {
    try {
      await api.put(`${SKILLS_GOV_BASE}/`, { mode })
      await fetchGovernance()
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to update governance mode'
    }
  }

  /** Issue #951: Poll for new autonomous-generated approvals every 30s. */
  function startApprovalPolling(): void {
    if (_pollTimer !== null) return
    _pollTimer = setInterval(async () => {
      const prev = approvals.value.length
      await fetchApprovals()
      const curr = approvals.value.length
      if (curr > prev) {
        const newest = approvals.value[approvals.value.length - 1]
        newDraftNotification.value =
          `AutoBot generated a new skill: "${newest?.skill_id ?? 'unknown'}" — pending approval`
      }
    }, 30_000)
  }

  function stopApprovalPolling(): void {
    if (_pollTimer !== null) {
      clearInterval(_pollTimer)
      _pollTimer = null
    }
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
    startApprovalPolling,
    stopApprovalPolling,
    dismissDraftNotification,
  }
}
