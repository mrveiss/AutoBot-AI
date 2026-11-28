// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Server entry -> store document (#17530). The Manage list is a projection of what the server
 * holds, so the id is the server's (an entry without one is dropped, never given a made-up id)
 * and `contentComplete` is set only here, where the full content was read.
 */
import { DEFAULT_FACT_CATEGORY, DEFAULT_FACT_TYPE } from '@/models/repositories/knowledgeFactMapping'
import type { KnowledgeEntry } from '@/types/api-contract'
import type { KnowledgeDocument } from '@/stores/useKnowledgeStore'

type DocumentType = KnowledgeDocument['type']

/** The UI document class of a fact, from its metadata. */
export function determineDocumentType(metadata: Record<string, unknown>): DocumentType {
  if (metadata.content_type === 'url' || metadata.type === 'url_reference') return 'webpage'
  if (metadata.filename || (typeof metadata.content_type === 'string' && metadata.content_type.includes('multipart'))) {
    return 'upload'
  }
  if (typeof metadata.source === 'string' && metadata.source.toLowerCase().includes('api')) return 'api'
  return DEFAULT_FACT_TYPE
}

/** A missing or unparseable date is the epoch, never "now" (a made-up date sorts as the newest entry). */
const asDate = (value: unknown): Date => {
  const parsed = typeof value === 'string' && value ? new Date(value) : null
  return parsed && !Number.isNaN(parsed.getTime()) ? parsed : new Date(0)
}

/** Null when the server entry carries no id: it cannot be updated or deleted, so it is not listed. */
export function entryToDocument(entry: KnowledgeEntry): KnowledgeDocument | null {
  if (!entry.id) return null
  const metadata = entry.metadata || {}
  const created = asDate(entry.created_at || metadata.created_at)
  return {
    id: entry.id,
    title: entry.title || (metadata.title as string) || 'Untitled',
    content: entry.content || '',
    contentComplete: true,
    source: entry.source || (metadata.url as string) || 'Unknown',
    type: determineDocumentType(metadata),
    tags: (metadata.tags as string[]) || [],
    category: entry.category || DEFAULT_FACT_CATEGORY,
    createdAt: created,
    updatedAt: metadata.updated_at ? asDate(metadata.updated_at) : created,
    metadata: {
      wordCount: metadata.word_count as number | undefined,
      fileSize: metadata.file_size as number | undefined,
      language: metadata.language as string | undefined,
      author: metadata.author as string | undefined,
      factType: typeof metadata.type === 'string' ? metadata.type : undefined,
    },
  }
}
