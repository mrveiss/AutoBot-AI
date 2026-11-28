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
import type { components } from '@/types/generated/api'
import { getApiBase } from '@/config/ssot-config'
import type { KnowledgeDocument } from '@/stores/useKnowledgeStore'

/** GET /api/knowledge_base/fact/{fact_key} body, from the generated contract. */
export type FactByKeyBody = components['schemas']['FactByKeyResponse']

export function factByKeyUrl(documentId: string): string {
  const factKey = documentId.startsWith('fact:') ? documentId : `fact:${documentId}`
  return `${getApiBase()}/knowledge_base/fact/${encodeURIComponent(factKey)}`
}

/**
 * The ONE default fact category the knowledge UI shows and submits when none is set (#21921).
 * The display form of the backend's `CategoryDefaults.GENERAL` (`autobot_shared/category_defaults.py`,
 * `'general'`); `repo_tests/knowledge_default_category_mirror_21921_test.py` fails if the two drift apart.
 */
export const DEFAULT_FACT_CATEGORY = 'General'
/** The UI document class a fact shows as when the backend sent no `type`. */
export const DEFAULT_FACT_TYPE = 'document'
const DOCUMENT_TYPES: readonly KnowledgeDocument['type'][] = ['document', 'webpage', 'api', 'upload']

/** The backend `type` when it is a UI document class, else the default (an unknown fact type such as `man_page`). */
function documentType(factType: string): KnowledgeDocument['type'] {
  return DOCUMENT_TYPES.find((t) => t === factType) ?? DEFAULT_FACT_TYPE
}

function metaString(meta: Record<string, unknown>, key: string): string {
  const value = meta[key]
  return typeof value === 'string' ? value : ''
}

export function factToDocument(documentId: string, fact: FactByKeyBody): KnowledgeDocument {
  const meta = fact.metadata ?? {}
  const parsed = fact.created_at ? new Date(fact.created_at) : null
  const created = parsed && !Number.isNaN(parsed.getTime()) ? parsed : new Date(0)
  const factType = metaString(meta, 'type')
  return {
    id: documentId,
    title: metaString(meta, 'title'),
    content: typeof fact.content === 'string' ? fact.content : '',
    source: metaString(meta, 'source'),
    type: documentType(factType),
    tags: Array.isArray(meta.tags) ? meta.tags.filter((tag): tag is string => typeof tag === 'string') : [],
    category: metaString(meta, 'category') || DEFAULT_FACT_CATEGORY,
    createdAt: created,
    updatedAt: created,
    metadata: { factType: factType || undefined },
  }
}
