// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { ref, onUnmounted } from 'vue'
import { getBackendUrl } from '@/config/ssot-config'

export type ProgressStatus = 'idle' | 'running' | 'complete' | 'error'

export function useSseProgress(recordingId: number) {
  const percent = ref(0)
  const step = ref('')
  const status = ref<ProgressStatus>('idle')
  let source: EventSource | null = null

  function connect() {
    const url = `${getBackendUrl()}/api/transcriber/recordings/${recordingId}/progress`
    source = new EventSource(url)
    status.value = 'running'

    source.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        percent.value = data.percent ?? percent.value
        step.value = data.step ?? step.value
        if (data.percent === 100) {
          status.value = 'complete'
          source?.close()
        }
        if (data.error) {
          status.value = 'error'
          source?.close()
        }
      } catch {
        // non-JSON heartbeat — ignore
      }
    }
    source.onerror = () => {
      status.value = 'error'
      source?.close()
    }
  }

  function disconnect() {
    source?.close()
    source = null
  }

  onUnmounted(disconnect)
  return { percent, step, status, connect, disconnect }
}
