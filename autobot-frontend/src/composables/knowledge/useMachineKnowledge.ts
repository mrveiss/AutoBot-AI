/**
 * useMachineKnowledge Composable
 *
 * Per-machine knowledge operations: machine profile fetch, initializing
 * machine-specific knowledge entries, and refreshing system knowledge.
 * Split from useKnowledgeBase (#5122). Dead try/catch wrappers removed (#5123):
 * ApiClient already logs retries + final failure and never returns null.
 */

import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
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

export function useMachineKnowledge() {
  /**
   * Fetch all machine profiles.
   * Issue #552: Fixed path — backend uses singular /api/knowledge_base/machine_profile.
   * Returns [] on error so consumers can render an empty list without try/catch.
   */
  const fetchMachineProfiles = async (): Promise<MachineProfile[]> => {
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
  const fetchMachineProfile = async (machineId: string): Promise<MachineProfile | null> => {
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
  const initializeMachineKnowledge = (machineId: string): Promise<MachineKnowledgeResponse> =>
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
  const refreshSystemKnowledge = (): Promise<SystemKnowledgeResponse> =>
    apiClient.post<SystemKnowledgeResponse>(
      `${getApiBase()}/knowledge_base/refresh_system_knowledge`,
      {}
    )

  return {
    fetchMachineProfiles,
    fetchMachineProfile,
    initializeMachineKnowledge,
    refreshSystemKnowledge,
  }
}
