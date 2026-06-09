// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { ref, type Ref } from 'vue'
import { useTranscriberApi, type KbPushStatus } from './useTranscriberApi'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useKbStatus')

export interface UseKbStatusReturn {
  status: Ref<KbPushStatus | null>
  loading: Ref<boolean>
  error: Ref<string>
  refresh: () => Promise<void>
}

/**
 * Composable for managing KB push status with reactive state.
 *
 * Replaces manual onMounted + post-mutation polling pattern with
 * a dedicated reactive data loader (issue #9206).
 *
 * @param recordingId - The recording ID to fetch KB status for
 * @returns Reactive KB status, loading state, error, and refresh method
 */
export function useKbStatus(recordingId: number): UseKbStatusReturn {
  const api = useTranscriberApi()
  const status = ref<KbPushStatus | null>(null)
  const loading = ref(false)
  const error = ref('')

  async function refresh(): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      status.value = await api.kbStatus(recordingId)
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      logger.error('Failed to fetch KB status', err)
    } finally {
      loading.value = false
    }
  }

  return { status, loading, error, refresh }
}
