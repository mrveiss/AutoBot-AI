// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Knowledge-cleanup proposals on the main backend (#20992, umbrella #17038).
 *
 * Both surfaces report read-only and only ever PROPOSE a removal as an approval-gate request; the
 * decision is made in the existing Approvals inbox. Nothing here deletes or rewrites anything.
 * Admin only. The `/autobot-api` proxy strips its prefix, so these reach
 * `/api/knowledge_base/connector_credentials/*` and `/api/knowledge/chroma/empty-collections/*`.
 */

import { createAutobotBackendClient } from '@/composables/useAutobotApi'

/** One connector record holding clear-text values. `fields` are field NAMES, never values. */
export interface ConnectorCredentialFinding {
  connector_id: string
  connector_type: string
  fields: string[]
  has_secrets_store_copy: boolean
}

export interface ConnectorCredentialScan {
  scanned: number
  affected: number
  with_store_copy_count: number
  without_store_copy_count: number
  findings: ConnectorCredentialFinding[]
  /** Could not be checked: never read as clean. */
  unscannable_ids: string[]
}

export interface EmptyCollectionsReport {
  total: number
  empty: string[]
  /** Could not be counted: never read as empty. */
  unreadable: string[]
}

/** The PENDING approval a proposal created (or the one already open for the same target). */
export interface CleanupProposalResult {
  approval_id: string
  status: string
  action: string
}

const CONNECTOR_BASE = '/knowledge_base/connector_credentials'
const EMPTY_COLLECTIONS_BASE = '/knowledge/chroma/empty-collections'

export function useKnowledgeCleanupApi() {
  const client = createAutobotBackendClient()

  function scanConnectorCredentials(): Promise<ConnectorCredentialScan> {
    return client.get<ConnectorCredentialScan>(`${CONNECTOR_BASE}/scan`)
  }

  /** Only a record with a secrets-store copy can be proposed; the backend answers 409 otherwise. */
  function proposeConnectorCredentialStrip(connectorId: string): Promise<CleanupProposalResult> {
    return client.post<CleanupProposalResult>(`${CONNECTOR_BASE}/cleanup-requests`, { connector_id: connectorId })
  }

  function getEmptyCollections(): Promise<EmptyCollectionsReport> {
    return client.get<EmptyCollectionsReport>(EMPTY_COLLECTIONS_BASE)
  }

  function proposeEmptyCollectionDelete(collection: string): Promise<CleanupProposalResult> {
    return client.post<CleanupProposalResult>(`${EMPTY_COLLECTIONS_BASE}/cleanup-requests`, { collection })
  }

  return {
    scanConnectorCredentials,
    proposeConnectorCredentialStrip,
    getEmptyCollections,
    proposeEmptyCollectionDelete,
  }
}
