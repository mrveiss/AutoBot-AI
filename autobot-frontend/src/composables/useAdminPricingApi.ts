// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Admin Model Pricing Composable (#16825)
 *
 * Surfaces the live LLM pricing refresh backend (GH#6480, #16228, #16231),
 * which had no reachable GUI: per-provider refresh status (freshness
 * signal), an on-demand refresh trigger, and manual price override.
 *
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 */

import { useApiClient } from '@/plugins/api'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useAdminPricingApi')

export interface ProviderRefreshStatus {
  last_attempt_at: string | null
  last_refresh_at: string | null
  success: boolean
  model_count: number
}

export type PricingStatusResponse = Record<string, ProviderRefreshStatus>

export interface RefreshSourceResult {
  provider?: string
  model_count?: number
  success?: boolean
  error?: string
}

export interface RefreshSummary {
  sources: Record<string, RefreshSourceResult>
  written?: number
  indexed?: number
  crosscheck?: Record<string, unknown>
}

export interface PricingOverrideInput {
  input_per_1m: number
  output_per_1m: number
  cache_read_per_1m?: number | null
  cache_write_per_1m?: number | null
}

export interface UseAdminPricingApiReturn {
  fetchStatus: () => Promise<PricingStatusResponse>
  refreshNow: () => Promise<RefreshSummary>
  setOverride: (provider: string, model: string, body: PricingOverrideInput) => Promise<void>
  deleteOverride: (provider: string, model: string) => Promise<void>
}

export function useAdminPricingApi(): UseAdminPricingApiReturn {
  const api = useApiClient()

  async function fetchStatus(): Promise<PricingStatusResponse> {
    try {
      const data = await api.get<{ providers?: PricingStatusResponse }>(
        `${getApiBase()}/admin/pricing/status`,
      )
      return data?.providers ?? {}
    } catch (error: unknown) {
      logger.error('Failed to load pricing refresh status', error)
      return {}
    }
  }

  async function refreshNow(): Promise<RefreshSummary> {
    const data = await api.post<RefreshSummary>(`${getApiBase()}/admin/pricing/refresh`)
    return data ?? { sources: {} }
  }

  async function setOverride(
    provider: string,
    model: string,
    body: PricingOverrideInput,
  ): Promise<void> {
    await api.put(
      `${getApiBase()}/admin/pricing/${encodeURIComponent(provider)}/${encodeURIComponent(model)}`,
      body,
    )
  }

  async function deleteOverride(provider: string, model: string): Promise<void> {
    await api.delete(
      `${getApiBase()}/admin/pricing/${encodeURIComponent(provider)}/${encodeURIComponent(model)}`,
    )
  }

  return { fetchStatus, refreshNow, setOverride, deleteOverride }
}
