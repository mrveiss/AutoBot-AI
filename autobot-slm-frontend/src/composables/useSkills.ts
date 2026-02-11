// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Skills Management Composable (Issue #731)
 *
 * Provides reactive state and methods for managing the Skills system
 * via the AutoBot user backend API.
 */

import { ref, computed, readonly } from 'vue'
import axios from 'axios'
import { useAuthStore } from '@/stores/auth'

// Skills API is on the main AutoBot backend, proxied via nginx
const API_BASE = '/autobot-api/skills'

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
  tools: string[]
  triggers: string[]
  dependencies: string[]
  tags: string[]
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
