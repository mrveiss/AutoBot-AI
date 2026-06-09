// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useMachineKnowledge Composable
 *
 * Per-machine knowledge operations: machine profile fetch, initializing
 * machine-specific knowledge entries, and refreshing system knowledge.
 * Split from useKnowledgeBase (#5122). Dead try/catch wrappers removed (#5123):
 * ApiClient already logs retries + final failure and never returns null.
 *
 * Reactive refs layer (#5149): the composable now owns loading/error state
 * for `refreshProfiles`/`refreshProfile`. The bare imperative functions
 * remain exported at module scope for the `useKnowledgeBase` BC shim.
 */

import { ref, readonly, type Ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { useLoadingState } from '../useLoadingState'
import type {
  MachineKnowledgeResponse,
  SystemKnowledgeResponse,
} from '@/types/knowledgeBase'

export interface MachineProfile {
  machine_id?: string
  os_type?: string
  distro?: string
  package_manager?: string
  available_tools?: string[]
  architecture?: string
}

// ==================== Bare imperative API ====================

/**
 * Fetch all machine profiles.
 * Issue #552: Fixed path — backend uses singular /api/knowledge_base/machine_profile.
 * Returns [] on error so consumers can render an empty list without try/catch.
 */
export const fetchMachineProfiles = async (): Promise<MachineProfile[]> => {
  try {
    const data = await apiClient.get<MachineProfile[]>(`${getApiBase()}/knowledge_base/machine_profile`)
    return Array.isArray(data) ? data : []
  } catch {
    return []
  }
}

/**
 * Fetch machine profile for a specific machine.
 * Returns null on error so consumers can gate UI on presence.
 */
export const fetchMachineProfile = async (machineId: string): Promise<MachineProfile | null> => {
  try {
    return await apiClient.get<MachineProfile>(
      `${getApiBase()}/knowledge_base/machine_profile?machine_id=${encodeURIComponent(machineId)}`
    )
  } catch {
    return null
  }
}

/**
 * Initialize machine knowledge for a specific host.
 * POST /api/knowledge_base/machine_knowledge/initialize
 */
export const initializeMachineKnowledge = (machineId: string): Promise<MachineKnowledgeResponse> =>
  apiClient.post<MachineKnowledgeResponse>(
    `${getApiBase()}/knowledge_base/machine_knowledge/initialize`,
    { machine_id: machineId }
  )

/**
 * Refresh system knowledge (rescan and update all system information).
 * POST /api/knowledge_base/refresh_system_knowledge
 *
 * Returns immediately with task_id. Use useKnowledgeJobs().pollJobStatus
 * to check completion.
 */
export const refreshSystemKnowledge = (): Promise<SystemKnowledgeResponse> =>
  apiClient.post<SystemKnowledgeResponse>(
    `${getApiBase()}/knowledge_base/refresh_system_knowledge`,
    {}
  )

// ==================== Reactive composable ====================

export interface UseMachineKnowledgeReturn {
  /** Latest list of all machine profiles. */
  profiles: Readonly<Ref<MachineProfile[]>>
  /** Latest per-machine profile fetched via `refreshProfile`. */
  profile: Readonly<Ref<MachineProfile | null>>
  /** True while any refresh is in-flight. */
  isLoading: Readonly<Ref<boolean>>
  /** Last error raised; cleared on next call. */
  error: Readonly<Ref<Error | null>>
  /** Fetch all profiles, update `profiles`. */
  refreshProfiles: () => Promise<MachineProfile[]>
  /** Fetch one machine's profile, update `profile`. */
  refreshProfile: (machineId: string) => Promise<MachineProfile | null>
  // Imperative passthroughs — BC with pre-#5149 callers
  fetchMachineProfiles: typeof fetchMachineProfiles
  fetchMachineProfile: typeof fetchMachineProfile
  initializeMachineKnowledge: typeof initializeMachineKnowledge
  refreshSystemKnowledge: typeof refreshSystemKnowledge
}

export function useMachineKnowledge(): UseMachineKnowledgeReturn {
  const profiles = ref<MachineProfile[]>([])
  const profile = ref<MachineProfile | null>(null)
  const { isLoading, wrap } = useLoadingState()
  const error = ref<Error | null>(null)

  const refreshProfiles = async (): Promise<MachineProfile[]> => {
    error.value = null
    return wrap(async () => {
      const data = await fetchMachineProfiles()
      profiles.value = data
      return data
    })
  }

  const refreshProfile = async (machineId: string): Promise<MachineProfile | null> => {
    error.value = null
    return wrap(async () => {
      const data = await fetchMachineProfile(machineId)
      profile.value = data
      return data
    })
  }

  return {
    profiles: readonly(profiles) as Readonly<Ref<MachineProfile[]>>,
    profile: readonly(profile) as Readonly<Ref<MachineProfile | null>>,
    isLoading: readonly(isLoading),
    error: readonly(error),
    refreshProfiles,
    refreshProfile,
    fetchMachineProfiles,
    fetchMachineProfile,
    initializeMachineKnowledge,
    refreshSystemKnowledge,
  }
}
