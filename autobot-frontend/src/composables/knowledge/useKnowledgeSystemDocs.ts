// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * useKnowledgeSystemDocs Composable
 *
 * Fetching layer extracted from KnowledgeSystemDocs.vue (#6045).
 * Provides bare imperative API functions for all system-docs endpoints:
 * - document categories listing
 * - docs within a category (by path)
 * - single document content (by id)
 *
 * All calls delegate to ApiClient so auth, retries, and error logging
 * are handled centrally. No fetchWithAuth in this file.
 */

import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'

// ==================== Types ====================

export interface SystemDoc {
  id: string
  title: string
  path: string
  content: string
  type: string
  category: string
  metadata?: {
    wordCount?: number
    lastModified?: string
    author?: string
  }
}

export interface DocCategory {
  id: string
  name: string
  path: string
  icon: string
  children: DocCategory[]
  docs: SystemDoc[]
  docCount: number
}

export interface DocCategoriesResponse {
  categories: DocCategory[]
}

export interface CategoryDocsResponse {
  docs: SystemDoc[]
}

export interface DocContentResponse {
  doc: SystemDoc
}

// ==================== Bare imperative API ====================

/**
 * Fetch the top-level documentation category tree.
 */
export const fetchDocCategories = (): Promise<DocCategoriesResponse> =>
  apiClient.get<DocCategoriesResponse>(`${getApiBase()}/knowledge_base/system-docs/categories`)

/**
 * Fetch documents belonging to a specific category by its path.
 */
export const fetchCategoryDocs = (categoryPath: string): Promise<CategoryDocsResponse> =>
  apiClient.get<CategoryDocsResponse>(
    `${getApiBase()}/knowledge_base/system-docs/category/${encodeURIComponent(categoryPath)}`
  )

/**
 * Fetch the full content of a single system document by its id.
 */
export const fetchDocContent = (docId: string): Promise<DocContentResponse> =>
  apiClient.get<DocContentResponse>(
    `${getApiBase()}/knowledge_base/system-docs/${encodeURIComponent(docId)}`
  )
