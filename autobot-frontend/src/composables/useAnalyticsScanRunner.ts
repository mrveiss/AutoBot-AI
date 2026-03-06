/**
 * Sequential scan runner with per-scan status tracking (#1418).
 *
 * Executes an array of scan definitions one-by-one, tracking status,
 * timing, and errors for each. Provides reactive progress computed
 * properties for UI consumption.
 *
 * Usage:
 *   const runner = useAnalyticsScanRunner()
 *   await runner.runAll([
 *     { id: 'deps', label: 'Dependencies', run: () => loadDeps() },
 *     { id: 'sec',  label: 'Security',     run: () => loadSec() },
 *   ])
 *   // runner.results.value — per-scan status
 *   // runner.progress.value — 0-100
 *
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 */

import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useAnalyticsScanRunner')

export type ScanStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped'

export interface ScanDefinition {
  id: string
  label: string
  run: () => Promise<void>
  skip?: () => boolean
}

export interface ScanResult {
  id: string
  label: string
  status: ScanStatus
  error?: string
  durationMs?: number
}

export interface ScanRunnerReturn {
  running: Ref<boolean>
  results: Ref<ScanResult[]>
  completedCount: ComputedRef<number>
  failedCount: ComputedRef<number>
  skippedCount: ComputedRef<number>
  totalCount: ComputedRef<number>
  progress: ComputedRef<number>
  runAll: (scans: ScanDefinition[]) => Promise<void>
  reset: () => void
}

/** Execute a single scan, updating the result entry in-place. */
async function executeScan(
  scan: ScanDefinition,
  results: Ref<ScanResult[]>,
  index: number,
): Promise<void> {
  const entry = results.value[index]

  if (scan.skip?.()) {
    entry.status = 'skipped'
    entry.durationMs = 0
    logger.info(`[${scan.id}] skipped: ${scan.label}`)
    return
  }

  entry.status = 'running'
  const start = performance.now()
  logger.info(`[${scan.id}] started: ${scan.label}`)

  try {
    await scan.run()
    const elapsed = Math.round(performance.now() - start)
    entry.status = 'completed'
    entry.durationMs = elapsed
    logger.info(`[${scan.id}] completed in ${elapsed}ms`)
  } catch (e: unknown) {
    const elapsed = Math.round(performance.now() - start)
    const msg = e instanceof Error ? e.message : String(e)
    entry.status = 'failed'
    entry.error = msg
    entry.durationMs = elapsed
    logger.error(`[${scan.id}] failed after ${elapsed}ms: ${msg}`)
  }
}

/**
 * Composable for sequential analytics scan execution with
 * per-scan status tracking and reactive progress.
 */
export function useAnalyticsScanRunner(): ScanRunnerReturn {
  const running: Ref<boolean> = ref(false)
  const results: Ref<ScanResult[]> = ref([])

  const completedCount = computed(
    () => results.value.filter((r) => r.status === 'completed').length,
  )
  const failedCount = computed(
    () => results.value.filter((r) => r.status === 'failed').length,
  )
  const skippedCount = computed(
    () => results.value.filter((r) => r.status === 'skipped').length,
  )
  const totalCount = computed(() => results.value.length)

  const progress = computed(() => {
    const total = totalCount.value
    if (total === 0) return 0
    const done = completedCount.value + failedCount.value + skippedCount.value
    return Math.round((done / total) * 100)
  })

  /**
   * Run all scans sequentially, updating results as each completes.
   *
   * @param scans  Array of scan definitions to execute in order.
   */
  const runAll = async (scans: ScanDefinition[]): Promise<void> => {
    running.value = true
    results.value = scans.map((s) => ({
      id: s.id,
      label: s.label,
      status: 'pending' as ScanStatus,
    }))

    logger.info(`Starting ${scans.length} scans sequentially`)

    for (let i = 0; i < scans.length; i++) {
      await executeScan(scans[i], results, i)
    }

    const summary = [
      `completed=${completedCount.value}`,
      `failed=${failedCount.value}`,
      `skipped=${skippedCount.value}`,
    ].join(', ')
    logger.info(`All scans finished: ${summary}`)

    running.value = false
  }

  /** Reset all state to initial values. */
  const reset = (): void => {
    running.value = false
    results.value = []
  }

  return {
    running,
    results,
    completedCount,
    failedCount,
    skippedCount,
    totalCount,
    progress,
    runAll,
    reset,
  }
}

export default useAnalyticsScanRunner
