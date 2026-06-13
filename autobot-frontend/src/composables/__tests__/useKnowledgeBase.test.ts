// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useKnowledgeBase BC Shim Smoke Tests
 *
 * The composable was split into 6 domain-focused composables under
 * `../knowledge/*` (#5122). This file only verifies the backward-compat
 * aggregator still exposes every function it did before the split, so
 * unmigrated consumers keep working.
 *
 * Per-function behavior is covered by the focused test files:
 * - useKnowledgeStats.test.ts
 * - useKnowledgeCategories.test.ts
 * - useKnowledgeFacts.test.ts
 * - useKnowledgeFiles.test.ts
 * - useMachineKnowledge.test.ts
 * - useManPages.test.ts
 * - useKnowledgeJobs.test.ts
 */

import { describe, it, expect, vi } from 'vitest'
import { useKnowledgeBase } from '../useKnowledgeBase'

vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

vi.mock('@/utils/formatHelpers', () => ({
  formatDate: (date: unknown) => new Date(date as string).toLocaleDateString(),
  formatFileSize: (bytes: number) => `${(bytes / 1024).toFixed(2)} KB`,
  formatCategoryName: (name: string) => name.replace(/_/g, ' ').toUpperCase(),
}))

vi.mock('@/utils/iconMappings', () => ({
  getFileIcon: () => 'fas fa-file',
}))

vi.mock('@/config/AppConfig.js', () => ({
  default: {
    getApiUrl: vi.fn((url) => Promise.resolve(`/api${url}`)),
    getTimeout: vi.fn(() => 300000),
  },
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({
    debug: vi.fn(),
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
  }),
}))

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/knowledge_base',
}))

describe('useKnowledgeBase (BC shim)', () => {
  it('should export all API call methods from the aggregator', () => {
    const composable = useKnowledgeBase()

    // Stats
    expect(typeof composable.fetchStats).toBe('function')
    expect(typeof composable.fetchBasicStats).toBe('function')
    // Categories
    expect(typeof composable.fetchCategories).toBe('function')
    expect(typeof composable.fetchCategory).toBe('function')
    expect(typeof composable.getCategorizedFacts).toBe('function')
    expect(typeof composable.buildCategoryFilterOptions).toBe('function')
    // Facts / search
    expect(typeof composable.searchKnowledge).toBe('function')
    expect(typeof composable.advancedSearch).toBe('function')
    expect(typeof composable.addFact).toBe('function')
    // Files
    expect(typeof composable.uploadKnowledgeFile).toBe('function')
    // Machine
    expect(typeof composable.fetchMachineProfiles).toBe('function')
    expect(typeof composable.fetchMachineProfile).toBe('function')
    expect(typeof composable.initializeMachineKnowledge).toBe('function')
    expect(typeof composable.refreshSystemKnowledge).toBe('function')
    // Man pages
    expect(typeof composable.fetchManPagesSummary).toBe('function')
    expect(typeof composable.integrateManPages).toBe('function')
    expect(typeof composable.populateManPages).toBe('function')
    expect(typeof composable.populateAutoBotDocs).toBe('function')
    // Jobs / vectorization
    expect(typeof composable.getVectorizationStatus).toBe('function')
    expect(typeof composable.vectorizeFacts).toBe('function')
    expect(typeof composable.pollJobStatus).toBe('function')
  })

  it('should export all helper/icon functions', () => {
    const composable = useKnowledgeBase()

    expect(typeof composable.getCategoryIcon).toBe('function')
    expect(typeof composable.getTypeIcon).toBe('function')
    expect(typeof composable.getFileIcon).toBe('function')
    expect(typeof composable.getOSBadgeClass).toBe('function')
    expect(typeof composable.getMessageIcon).toBe('function')
    expect(typeof composable.formatTime).toBe('function')
  })

  it('should export formatting functions from shared utilities', () => {
    const composable = useKnowledgeBase()

    expect(typeof composable.formatDate).toBe('function')
    expect(typeof composable.formatCategory).toBe('function')
    expect(typeof composable.formatCategoryName).toBe('function')
    expect(typeof composable.formatFileSize).toBe('function')
    expect(typeof composable.formatDateOnly).toBe('function')
  })

  it('should keep behavior for key icon helpers', () => {
    const { getCategoryIcon, getOSBadgeClass, getMessageIcon } = useKnowledgeBase()

    expect(getCategoryIcon('security')).toBe('shield-alt')
    expect(getCategoryIcon('unknown')).toBe('folder')
    expect(getOSBadgeClass('linux')).toBe('badge-success')
    expect(getOSBadgeClass('macos')).toBe('badge-warning')
    expect(getMessageIcon('error')).toBe('times-circle')
  })
})
