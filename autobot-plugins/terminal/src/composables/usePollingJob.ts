// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss

import { ref, onScopeDispose } from 'vue'

export interface UsePollingJobOptions {
  intervalMs?: number
  maxAttempts?: number
}

export function usePollingJob(
  fn: (arg: string) => Promise<void> | void,
  options: UsePollingJobOptions = {}
) {
  const { intervalMs = 2000, maxAttempts = Number.MAX_SAFE_INTEGER } = options
  const isPolling = ref(false)
  let timer: ReturnType<typeof setInterval> | null = null
  let attempts = 0

  const start = (arg = '') => {
    if (isPolling.value) return
    isPolling.value = true
    attempts = 0
    timer = setInterval(async () => {
      if (attempts >= maxAttempts) { stop(); return }
      attempts++
      await fn(arg)
    }, intervalMs)
  }

  const stop = () => {
    if (timer) { clearInterval(timer); timer = null }
    isPolling.value = false
  }

  onScopeDispose(stop)

  return { start, stop, isPolling }
}
