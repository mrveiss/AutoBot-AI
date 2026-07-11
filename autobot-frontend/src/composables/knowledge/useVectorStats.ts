// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { computed } from 'vue'
import type { ComputedRef } from 'vue'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'

export interface VectorStats {
  total_facts: number
  total_documents: number
  total_vectors: number
  indexed_documents: number
  db_size: number
  status: 'online' | 'offline' | 'unknown'
  rag_available: boolean
  initialized: boolean
  llama_index_configured: boolean
  index_available: boolean
  redis_db: string | number
  index_name: string
  embedding_model?: string
  embedding_dimensions?: number
  last_updated?: string
  categories?: string[]
}

export const EMBEDDING_MODEL = 'nomic-embed-text'
export const EMBEDDING_DIMENSIONS = 768

/**
 * Zeroed fallback for consumers whose UI must render a stats strip even when
 * the store has no facts yet or the backend is unreachable (KnowledgeHealth).
 * Mirrors the previous offline/error fallback in KnowledgeHealth.vue.
 */
export const EMPTY_VECTOR_STATS: Readonly<VectorStats> = Object.freeze({
  total_facts: 0,
  total_documents: 0,
  total_vectors: 0,
  indexed_documents: 0,
  db_size: 0,
  status: 'offline' as const,
  rag_available: false,
  initialized: false,
  llama_index_configured: false,
  index_available: false,
  redis_db: 0,
  index_name: 'unknown'
})

export interface UseVectorStatsReturn {
  vectorStats: ComputedRef<VectorStats | null>
  refresh: () => Promise<void>
}

export function useVectorStats(): UseVectorStatsReturn {
  const store = useKnowledgeStore()

  const vectorStats = computed<VectorStats | null>(() => {
    const storeStats = store.stats
    if (!storeStats || !storeStats.total_facts) return null
    return {
      total_facts: storeStats.total_facts || 0,
      total_documents: storeStats.total_documents || 0,
      total_vectors: storeStats.total_vectors || 0,
      indexed_documents: storeStats.total_documents || 0,
      db_size: storeStats.db_size || 0,
      status: (storeStats.status as 'online' | 'offline' | 'unknown') || 'offline',
      rag_available: storeStats.rag_available || false,
      initialized: storeStats.initialized || false,
      llama_index_configured: storeStats.initialized || false,
      index_available: storeStats.initialized || false,
      redis_db: storeStats.redis_db ? parseInt(storeStats.redis_db) : 0,
      index_name: storeStats.index_name || 'unknown',
      last_updated: storeStats.last_updated || undefined,
      categories: Array.isArray(storeStats.categories)
        ? (storeStats.categories as unknown as { name?: string }[]).map((c) => c.name || c) as string[]
        : [],
      embedding_model: EMBEDDING_MODEL,
      embedding_dimensions: EMBEDDING_DIMENSIONS,
    }
  })

  async function refresh(): Promise<void> {
    await store.refreshStats()
  }

  return { vectorStats, refresh }
}
