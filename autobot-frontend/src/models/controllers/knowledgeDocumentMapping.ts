// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Server entry -> store document (#17530). The Manage list is a projection of what the server
 * holds, so the id is the server's (an entry without one is dropped, never given a made-up id)
 * and `contentComplete` is set only here, where the full content was read.
 */
import { DEFAULT_FACT_CATEGORY, DEFAULT_FACT_TYPE, type KnowledgeEntryRecord } from '@/models/repositories/knowledgeFactMapping'
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

const asDate = (value: unknown): Date => (value ? new Date(value as string) : new Date())

/** Null when the server entry carries no id: it cannot be updated or deleted, so it is not listed. */
export function entryToDocument(entry: KnowledgeEntryRecord): KnowledgeDocument | null {
  const id = entry.id || entry.fact_id
  if (!id) return null
  const metadata = entry.metadata || {}
  return {
    id,
    title: (metadata.title as string) || entry.fact || 'Untitled',
    content: entry.fact || entry.content || '',
    contentComplete: true,
    source: (metadata.source as string) || (metadata.url as string) || 'Unknown',
    type: determineDocumentType(metadata),
    tags: (metadata.tags as string[]) || [],
    category: (metadata.category as string) || DEFAULT_FACT_CATEGORY,
    createdAt: asDate(metadata.created_at || entry.created_at),
    updatedAt: asDate(metadata.updated_at || entry.updated_at),
    metadata: {
      wordCount: metadata.word_count as number | undefined,
      fileSize: metadata.file_size as number | undefined,
      language: metadata.language as string | undefined,
      author: metadata.author as string | undefined,
      factType: typeof metadata.type === 'string' ? metadata.type : undefined,
    },
  }
}
