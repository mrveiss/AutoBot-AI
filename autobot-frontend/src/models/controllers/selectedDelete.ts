// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * "Delete selected" in the knowledge list (#21886, #21383): propose the deletion of exactly the selected documents.
 *
 * The backend only files a proposal for approval; the rows stay until a human approves it, then the list drops them
 * (see `approvedDeleteWatch`). Split out of `KnowledgeController`, a grandfathered file that may not grow.
 */
import i18n from '@/i18n'
import { knowledgeRepository } from '@/models/repositories/KnowledgeRepository'
import { watchApprovedDelete } from './approvedDeleteWatch'

/** The most facts one proposal may name (`CollectionFactsRequest.fact_ids`, `max_items=500`). */
export const MAX_SELECTED_DELETE = 500

export interface SelectedDeleteHooks {
  notify: (message: string) => void
  fail: (message: string) => void
  dropRows: (documentIds: string[]) => void
  resync: () => Promise<void>
  stillListed: (documentIds: string[]) => boolean
}

export async function proposeSelectedDelete(documentIds: string[], hooks: SelectedDeleteHooks): Promise<void> {
  if (documentIds.length === 0) {
    hooks.notify(i18n.global.t('knowledge.entries.deleteNothingSelected'))
    return
  }
  if (documentIds.length > MAX_SELECTED_DELETE) {
    hooks.notify(i18n.global.t('knowledge.entries.deleteTooMany', { max: MAX_SELECTED_DELETE }))
    return
  }
  try {
    const reply = await knowledgeRepository.bulkDeleteDocuments(documentIds)
    const settled = async () => {
      await hooks.resync()
      return !hooks.stillListed(documentIds)
    }
    watchApprovedDelete(reply.approval_id, () => hooks.dropRows(documentIds), settled)
    hooks.notify(i18n.global.t('knowledge.entries.deleteProposed'))
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : i18n.global.t('knowledge.entries.deleteUnknownError')
    hooks.fail(i18n.global.t('knowledge.entries.deleteProposeFailed', { message }))
    throw error
  }
}
