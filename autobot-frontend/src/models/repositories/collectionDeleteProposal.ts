// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Answer of the selected-facts delete route (#21886, #21383): a proposal for approval, never a deletion.
 * `approval_id` is the reference the Approvals inbox shows; `facts_selected` counts the selected facts that exist.
 */
export interface SelectedFactsDeleteProposal {
  status: string
  facts_selected: number
  approval_id: string
  approval_status?: string | null
  action: string
  message: string
}
