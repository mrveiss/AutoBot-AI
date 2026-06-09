// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useMachineKnowledge Composable Tests
 *
 * Split from useKnowledgeBase.test.ts (#5122).
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import type {
  MachineKnowledgeResponse,
  SystemKnowledgeResponse,
} from '@/types/knowledgeBase'
import { useMachineKnowledge, type MachineProfile } from '../knowledge/useMachineKnowledge'

vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/knowledge_base',
}))

import apiClient from '@/utils/ApiClient'

describe('useMachineKnowledge', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('fetchMachineProfiles', () => {
    it('should fetch all machine profiles', async () => {
      const mockProfiles: MachineProfile[] = [
        { machine_id: 'host1', os_type: 'linux', distro: 'Ubuntu' },
        { machine_id: 'host2', os_type: 'linux', distro: 'CentOS' },
      ]

      vi.mocked(apiClient.get).mockResolvedValue(mockProfiles)

      const { fetchMachineProfiles } = useMachineKnowledge()
      const result = await fetchMachineProfiles()

      expect(result).toEqual(mockProfiles)
      expect(Array.isArray(result)).toBe(true)
    })

    it('should return empty array when response is not an array', async () => {
      vi.mocked(apiClient.get).mockResolvedValue(null)

      const { fetchMachineProfiles } = useMachineKnowledge()
      const result = await fetchMachineProfiles()

      expect(result).toEqual([])
    })

    it('should return empty array on error', async () => {
      vi.mocked(apiClient.get).mockRejectedValue(new Error('HTTP 500'))

      const { fetchMachineProfiles } = useMachineKnowledge()
      const result = await fetchMachineProfiles()

      expect(result).toEqual([])
    })
  })

  describe('fetchMachineProfile', () => {
    it('should fetch profile for specific machine', async () => {
      const mockProfile: MachineProfile = {
        machine_id: 'host1',
        os_type: 'linux',
        distro: 'Ubuntu 20.04',
      }

      vi.mocked(apiClient.get).mockResolvedValue(mockProfile)

      const { fetchMachineProfile } = useMachineKnowledge()
      const result = await fetchMachineProfile('host1')

      expect(result).toEqual(mockProfile)
      expect(apiClient.get).toHaveBeenCalledWith(
        expect.stringContaining('machine_id=host1')
      )
    })

    it('should return null on error', async () => {
      vi.mocked(apiClient.get).mockRejectedValue(new Error('HTTP 500'))

      const { fetchMachineProfile } = useMachineKnowledge()
      const result = await fetchMachineProfile('host1')

      expect(result).toBe(null)
    })
  })

  describe('initializeMachineKnowledge', () => {
    it('should initialize machine knowledge', async () => {
      const mockResponse: MachineKnowledgeResponse = {
        status: 'success',
        message: 'Machine knowledge initialized',
        machine_id: 'host1',
        facts_added: 50,
      }

      vi.mocked(apiClient.post).mockResolvedValue(mockResponse)

      const { initializeMachineKnowledge } = useMachineKnowledge()
      const result = await initializeMachineKnowledge('host1')

      expect(result).toEqual(mockResponse)
      expect(apiClient.post).toHaveBeenCalledWith(
        '/knowledge_base/knowledge_base/machine_knowledge/initialize',
        { machine_id: 'host1' }
      )
    })
  })

  describe('refreshSystemKnowledge', () => {
    it('should trigger system knowledge refresh and return task_id', async () => {
      const mockResponse: SystemKnowledgeResponse = {
        status: 'queued',
        message: 'System knowledge refresh queued',
        total_machines: 3,
      }

      vi.mocked(apiClient.post).mockResolvedValue(mockResponse)

      const { refreshSystemKnowledge } = useMachineKnowledge()
      const result = await refreshSystemKnowledge()

      expect(result).toEqual(mockResponse)
      expect(result.status).toBe('queued')
    })
  })

  describe('reactive refs + refresh (#5149)', () => {
    it('refreshProfiles populates profiles ref + isLoading cycle', async () => {
      const mockProfiles: MachineProfile[] = [
        { machine_id: 'host1', os_type: 'linux' },
      ]
      vi.mocked(apiClient.get).mockResolvedValue(mockProfiles)

      const { profiles, isLoading, refreshProfiles } = useMachineKnowledge()
      expect(profiles.value).toEqual([])
      expect(isLoading.value).toBe(false)

      const promise = refreshProfiles()
      expect(isLoading.value).toBe(true)

      const data = await promise
      expect(data).toEqual(mockProfiles)
      expect(profiles.value).toEqual(mockProfiles)
      expect(isLoading.value).toBe(false)
    })

    it('refreshProfile populates profile ref', async () => {
      const mockProfile: MachineProfile = { machine_id: 'host1', os_type: 'linux' }
      vi.mocked(apiClient.get).mockResolvedValue(mockProfile)

      const { profile, refreshProfile } = useMachineKnowledge()
      const data = await refreshProfile('host1')

      expect(data).toEqual(mockProfile)
      expect(profile.value).toEqual(mockProfile)
    })
  })
})
