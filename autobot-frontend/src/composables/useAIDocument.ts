// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useAIDocument Composable
 *
 * State management and API calls for persistent, editable AI output documents.
 *
 * Issue #3245 — Knowledge Base: persistent editable AI output documents
 *
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 */

import { ref, computed } from 'vue'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'
import { useLoadingState } from './useLoadingState'

const logger = createLogger('useAIDocument')

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AIDocument {
  id: string
  title: string
  content: string
  source_facts: string[]
  source_session_id: string | null
  source_message_id: string | null
  user_id: string
  tags: string[]
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface CreateDocumentPayload {
  title: string
  content?: string
  source_facts?: string[]
  source_session_id?: string
  source_message_id?: string
  tags?: string[]
  metadata?: Record<string, unknown>
}

export interface UpdateDocumentPayload {
  title?: string
  content?: string
  tags?: string[]
  metadata?: Record<string, unknown>
}

export interface RefineDocumentPayload {
  instruction: string
  section?: string
}

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useAIDocument() {
  const documents = ref<AIDocument[]>([])
  const currentDocument = ref<AIDocument | null>(null)
  const { isLoading, wrap } = useLoadingState()
  const { isLoading: isSaving, wrap: wrapSaving } = useLoadingState()
  const { isLoading: isRefining, wrap: wrapRefining } = useLoadingState()
  const error = ref<string | null>(null)
  const total = ref(0)

  const hasDocuments = computed(() => documents.value.length > 0)

  // -------------------------------------------------------------------------
  // API helpers
  // -------------------------------------------------------------------------

  function _base(): string {
    return `${getApiBase()}/documents`
  }

  async function _handleError(label: string, err: unknown): Promise<never> {
    const msg = err instanceof Error ? err.message : String(err)
    logger.error(`${label}: ${msg}`)
    error.value = msg
    throw err
  }

  // -------------------------------------------------------------------------
  // Public actions
  // -------------------------------------------------------------------------

  /** Fetch the list of documents owned by the authenticated user. */
  async function fetchDocuments(limit = 50, offset = 0): Promise<void> {
    error.value = null
    return wrap(async () => {
      try {
        const response = await apiClient.get<{ documents: AIDocument[]; total: number }>(
          `${_base()}?limit=${limit}&offset=${offset}`
        )
        documents.value = response.documents
        total.value = response.total
      } catch (err) {
        await _handleError('fetchDocuments', err)
      }
    })
  }

  /** Load a single document into `currentDocument`. */
  async function fetchDocument(docId: string): Promise<AIDocument> {
    error.value = null
    return wrap(async () => {
      try {
        const response = await apiClient.get<AIDocument>(`${_base()}/${docId}`)
        currentDocument.value = response
        return response
      } catch (err) {
        return await _handleError('fetchDocument', err)
      }
    })
  }

  /** Create a new AI document and prepend it to the local list. */
  async function createDocument(payload: CreateDocumentPayload): Promise<AIDocument> {
    error.value = null
    return wrapSaving(async () => {
      try {
        const response = await apiClient.post<AIDocument>(_base(), payload)
        const created = response
        documents.value.unshift(created)
        total.value += 1
        logger.info(`Created document ${created.id}: ${created.title}`)
        return created
      } catch (err) {
        return await _handleError('createDocument', err)
      }
    })
  }

  /** Save edits to an existing document. */
  async function updateDocument(
    docId: string,
    payload: UpdateDocumentPayload
  ): Promise<AIDocument> {
    error.value = null
    return wrapSaving(async () => {
      try {
        const response = await apiClient.put<AIDocument>(`${_base()}/${docId}`, payload)
        const updated = response
        // Sync local list
        const idx = documents.value.findIndex((d) => d.id === docId)
        if (idx !== -1) {
          documents.value[idx] = updated
        }
        if (currentDocument.value?.id === docId) {
          currentDocument.value = updated
        }
        return updated
      } catch (err) {
        return await _handleError('updateDocument', err)
      }
    })
  }

  /** Delete a document and remove it from the local list. */
  async function deleteDocument(docId: string): Promise<void> {
    error.value = null
    try {
      await apiClient.delete<unknown>(`${_base()}/${docId}`)
      documents.value = documents.value.filter((d) => d.id !== docId)
      total.value = Math.max(0, total.value - 1)
      if (currentDocument.value?.id === docId) {
        currentDocument.value = null
      }
      logger.info(`Deleted document ${docId}`)
    } catch (err) {
      await _handleError('deleteDocument', err)
    }
  }

  /** Send a refinement instruction to the AI and update the document. */
  async function refineDocument(
    docId: string,
    payload: RefineDocumentPayload
  ): Promise<AIDocument> {
    error.value = null
    return wrapRefining(async () => {
      try {
        const response = await apiClient.post<AIDocument>(
          `${_base()}/${docId}/refine`,
          payload
        )
        const refined = response
        const idx = documents.value.findIndex((d) => d.id === docId)
        if (idx !== -1) {
          documents.value[idx] = refined
        }
        if (currentDocument.value?.id === docId) {
          currentDocument.value = refined
        }
        logger.info(`Refined document ${docId}`)
        return refined
      } catch (err) {
        return await _handleError('refineDocument', err)
      }
    })
  }

  /** Convenience: save an AI chat message as a new document. */
  async function saveMessageAsDocument(opts: {
    content: string
    title?: string
    sessionId?: string
    messageId?: string
    sourceFacts?: string[]
  }): Promise<AIDocument> {
    const title =
      opts.title ??
      (opts.content.length > 60
        ? opts.content.slice(0, 60).trimEnd() + '…'
        : opts.content)
    return createDocument({
      title,
      content: opts.content,
      source_session_id: opts.sessionId,
      source_message_id: opts.messageId,
      source_facts: opts.sourceFacts ?? [],
    })
  }

  return {
    // state
    documents,
    currentDocument,
    isLoading,
    isSaving,
    isRefining,
    error,
    total,
    hasDocuments,
    // actions
    fetchDocuments,
    fetchDocument,
    createDocument,
    updateDocument,
    deleteDocument,
    refineDocument,
    saveMessageAsDocument,
  }
}
