// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Selection and vectorize actions for the Knowledge Browser (#18244): one document,
 * a folder, the checked selection, retry of failures, and cancel.
 *
 * Moved out of KnowledgeBrowser.vue with its behaviour unchanged.
 */
import { computed, ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { collectUnvectorizedFiles } from '@/composables/knowledge/knowledgeTreeUtils'
import type { TreeNode } from '@/components/knowledge/TreeNodeComponent.vue'
import type { useKnowledgeVectorization } from '@/composables/useKnowledgeVectorization'

const logger = createLogger('KnowledgeBrowserSelection')

type Vectorization = ReturnType<typeof useKnowledgeVectorization>

export function useKnowledgeBrowserSelection(vec: Vectorization) {
  const isVectorizing = ref(false)
  const showProgressModal = ref(false)

  /** Selected documents that still need vectorizing (the rule vectorizeSelected applies). */
  const eligibleCount = computed(
    () => vec.selectedDocumentsList.value.filter((id) => vec.documentStates.value.get(id)?.status !== 'vectorized').length,
  )

  /** Run a vectorize action with the busy flag held, logging a failure instead of throwing. */
  const guarded = async (label: string, run: () => Promise<unknown>, openModal = false) => {
    isVectorizing.value = true
    if (openModal) showProgressModal.value = true
    try {
      logger.info(`${label} complete:`, await run())
    } catch (err) {
      logger.error(`${label} failed:`, err)
    } finally {
      isVectorizing.value = false
    }
  }

  const handleVectorizeDocument = (documentId: string) =>
    guarded(`Vectorizing ${documentId}`, () => vec.vectorizeDocument(documentId))

  const handleVectorizeFolder = async (folder: TreeNode) => {
    const statusOf = (id: string) => vec.documentStates.value.get(id)?.status || vec.getDocumentStatus(id)
    const ids = collectUnvectorizedFiles(folder, statusOf)
    if (ids.length === 0) {
      logger.info('No unvectorized documents found in this folder')
      return
    }
    logger.info(`Starting batch vectorization for ${ids.length} documents in folder: ${folder.name}`)
    await guarded('Folder vectorization', () => vec.vectorizeBatch(ids), true)
  }

  const vectorizeSelected = () => guarded('Batch vectorization', () => vec.vectorizeSelected(), true)

  const handleRetryFailed = async () => {
    const failed = Array.from(vec.documentStates.value.entries())
      .filter(([, state]) => state.status === 'failed')
      .map(([id]) => id)
    if (failed.length === 0) return
    isVectorizing.value = true
    // In parallel: no N+1 sequential calls.
    const results = await Promise.allSettled(failed.map((id) => vec.vectorizeDocument(id)))
    results.forEach((result, i) => {
      if (result.status === 'rejected') logger.error(`Failed to retry vectorization for ${failed[i]}:`, result.reason)
    })
    isVectorizing.value = false
  }

  const handleCancelVectorization = () => {
    // Backend jobs cannot be cancelled yet; this only stops waiting for them.
    isVectorizing.value = false
    showProgressModal.value = false
    logger.info('Vectorization cancelled by user')
  }

  return {
    isVectorizing, showProgressModal, eligibleCount, handleVectorizeDocument, handleVectorizeFolder,
    vectorizeSelected, handleRetryFailed, handleCancelVectorization,
  }
}
