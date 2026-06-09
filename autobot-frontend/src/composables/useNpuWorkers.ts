// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
// GH#6738 / MVA-1138: NPU worker pair API + profile management

import { useApiClient } from '@/plugins/api'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useNpuWorkers')

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type NpuWorkerProfile = 'inference' | 'embedding' | 'mixed' | 'relay'

export interface NpuWorkerPairRequest {
  url: string
  name?: string
  enabled?: boolean
}

export interface NpuWorkerPairResult {
  success: boolean
  worker_id: string
  recommended_profile: NpuWorkerProfile | null
  recommended_models: Array<{ id: string; reason: string }> | null
  vram_gb: number | null
  compute_class: string | null
  capabilities_summary: string | null
  error_message?: string | null
}

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useNpuWorkers() {
  const api = useApiClient()

  async function pairWorker(payload: NpuWorkerPairRequest): Promise<NpuWorkerPairResult> {
    logger.info('Pairing NPU worker at', payload.url)
    return api.post<NpuWorkerPairResult>(`${getApiBase()}/npu/workers/pair`, payload)
  }

  return { pairWorker }
}
