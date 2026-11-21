// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Answer of the collection delete routes (#21383): a proposal for approval, never a deletion.
 * `approval_id` is present only when a proposal was filed; a call without `confirm` is a read-only preview.
 */
/** The collection the knowledge entries belong to when none is named (the one the repository always assumed). */
export const DEFAULT_COLLECTION_ID = 'default'

export interface CollectionDeleteProposal {
  status: string
  collection_id: string
  facts_in_collection: number
  approval_id?: string | null
  approval_status?: string | null
  action?: string | null
  confirm_required?: boolean
  message?: string
}
