// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Composable: useSystemArchitectureData
 *
 * Encapsulates the backend fetch for the SystemArchitectureDiagram component
 * (#6085).
 *
 * Responsibilities:
 *  - Fetch `/monitoring/services/health` via apiClient
 *  - Expose `fetchArchitectureHealth` so the component owns zero API logic
 *  - Fall back to an empty service map on error, logging the failure
 */

import apiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'

const logger = createLogger('useSystemArchitectureData')

export interface ServiceHealthMap {
  [key: string]: { status?: string } | undefined
}

interface HealthApiResponse {
  services?: ServiceHealthMap
}

export function useSystemArchitectureData() {
  async function fetchArchitectureHealth(): Promise<ServiceHealthMap> {
    try {
      const response = await apiClient.get<HealthApiResponse>(`${getApiBase()}/monitoring/services/health`)
      return response?.data?.services ?? (response?.services as ServiceHealthMap | undefined) ?? {}
    } catch (error) {
      logger.error('Failed to fetch architecture data:', error)
      return {}
    }
  }

  return { fetchArchitectureHealth }
}
