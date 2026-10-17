// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Maps the served single-fact route onto KnowledgeDocument (#18730).
 *
 * The served route is GET /knowledge_base/fact/{fact_key} (api/knowledge.py
 * get_fact_by_key); fact keys are `fact:{id}` (knowledge/facts.py). The body is
 * bare: {key, content, metadata, created_at}.
 */
import { getApiBase } from '@/config/ssot-config'
import type { KnowledgeDocument } from '@/stores/useKnowledgeStore'

export interface FactByKeyBody {
  key: string
  content: string
  metadata?: Record<string, unknown>
  created_at?: string
}

export function factByKeyUrl(documentId: string): string {
  const factKey = documentId.startsWith('fact:') ? documentId : `fact:${documentId}`
  return `${getApiBase()}/knowledge_base/fact/${encodeURIComponent(factKey)}`
}

function metaString(meta: Record<string, unknown>, key: string): string {
  const value = meta[key]
  return typeof value === 'string' ? value : ''
}

export function factToDocument(documentId: string, fact: FactByKeyBody): KnowledgeDocument {
  const meta = fact.metadata ?? {}
  const created = fact.created_at ? new Date(fact.created_at) : new Date(0)
  return {
    id: documentId,
    title: metaString(meta, 'title'),
    content: fact.content,
    source: metaString(meta, 'source'),
    type: 'document',
    tags: Array.isArray(meta.tags) ? (meta.tags as string[]) : [],
    category: metaString(meta, 'category'),
    createdAt: created,
    updatedAt: created,
  }
}
