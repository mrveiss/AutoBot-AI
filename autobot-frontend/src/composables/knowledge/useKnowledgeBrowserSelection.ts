// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Selection and vectorize actions for the Knowledge Browser (#18244): one document,
 * a folder, the checked selection, retry of failures, and cancel.
 *
 * Moved out of KnowledgeBrowser.vue. A failed action is reported through `onError`
 * (a translated message) and by the action resolving `false`, never silently as success.
 */
import { computed, ref } from 'vue'
import i18n from '@/i18n'
import { createLogger } from '@/utils/debugUtils'
import { collectUnvectorizedFiles } from '@/composables/knowledge/knowledgeTreeUtils'
import type { TreeNode } from '@/components/knowledge/TreeNodeComponent.vue'
import type { useKnowledgeVectorization } from '@/composables/useKnowledgeVectorization'

const logger = createLogger('KnowledgeBrowserSelection')

type Vectorization = ReturnType<typeof useKnowledgeVectorization>

export function useKnowledgeBrowserSelection(vec: Vectorization, onError?: (message: string) => void) {
  const isVectorizing = ref(false)
  const showProgressModal = ref(false)

  /** Selected documents that still need vectorizing (the rule vectorizeSelected applies). */
  const eligibleCount = computed(
    () => vec.selectedDocumentsList.value.filter((id) => vec.documentStates.value.get(id)?.status !== 'vectorized').length,
  )

  // Identity of the latest run: a cancelled run can settle after a newer one started and must not clear its flag.
  let activeRun = 0
  const startRun = () => {
    isVectorizing.value = true
    return ++activeRun
  }
  const endRun = (runId: number) => {
    if (runId === activeRun) isVectorizing.value = false
  }
  // A superseded or cancelled run is abandoned work: log its failure, but do not show a banner for it.
  const reportFailure = (runId: number, label: string, err: unknown) => {
    logger.error(`${label} failed:`, err)
    if (runId !== activeRun) return
    onError?.(i18n.global.t('knowledge.browser.vectorizeFailed'))
  }

  /** Run a vectorize action with the busy flag held; resolves true on success, false on a reported failure. */
  const guarded = async (label: string, run: () => Promise<unknown>, openModal = false): Promise<boolean> => {
    const runId = startRun()
    if (openModal) showProgressModal.value = true
    try {
      logger.info(`${label} complete:`, await run())
      return true
    } catch (err) {
      reportFailure(runId, label, err)
      return false
    } finally {
      endRun(runId)
    }
  }

  const handleVectorizeDocument = (documentId: string) =>
    guarded(`Vectorizing ${documentId}`, () => vec.vectorizeDocument(documentId))

  const handleVectorizeFolder = async (folder: TreeNode) => {
    const statusOf = (id: string) => vec.documentStates.value.get(id)?.status || vec.getDocumentStatus(id)
    const ids = collectUnvectorizedFiles(folder, statusOf)
    if (ids.length === 0) {
      logger.info('No unvectorized documents found in this folder')
      return true
    }
    logger.info(`Starting batch vectorization for ${ids.length} documents in folder: ${folder.name}`)
    return guarded('Folder vectorization', () => vec.vectorizeBatch(ids), true)
  }

  /** Only the selected documents that are not vectorized yet (the set eligibleCount counts). */
  const vectorizeSelected = () => {
    const ids = vec.selectedDocumentsList.value.filter((id) => vec.documentStates.value.get(id)?.status !== 'vectorized')
    return guarded(
      'Batch vectorization',
      async () => {
        const result = ids.length ? await vec.vectorizeBatch(ids) : undefined
        vec.deselectAll()
        return result
      },
      ids.length > 0,
    )
  }

  const handleRetryFailed = async () => {
    const failed = Array.from(vec.documentStates.value.entries())
      .filter(([, state]) => state.status === 'failed')
      .map(([id]) => id)
    if (failed.length === 0) return true
    const runId = startRun()
    // In parallel: no N+1 sequential calls.
    const results = await Promise.allSettled(failed.map((id) => vec.vectorizeDocument(id)))
    const rejected = results.flatMap((result, i) => (result.status === 'rejected' ? [[failed[i], result.reason] as const] : []))
    rejected.forEach(([id, reason]) => logger.error(`Failed to retry vectorization for ${id}:`, reason))
    if (rejected.length && runId === activeRun) onError?.(i18n.global.t('knowledge.browser.vectorizeFailed'))
    endRun(runId)
    return rejected.length === 0
  }

  const handleCancelVectorization = () => {
    // Backend jobs cannot be cancelled yet; this only stops waiting for them.
    activeRun++
    isVectorizing.value = false
    showProgressModal.value = false
    logger.info('Vectorization cancelled by user')
  }

  return {
    isVectorizing, showProgressModal, eligibleCount, handleVectorizeDocument, handleVectorizeFolder,
    vectorizeSelected, handleRetryFailed, handleCancelVectorization,
  }
}
