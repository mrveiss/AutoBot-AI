<!-- AutoBot - Knowledge Graph Pipeline (Issue #759) -->
<template>
  <div class="summary-search">
    <div class="search-header">
      <h4><i class="fas fa-search"></i> Summary Search</h4>
      <p class="header-description">
        Search across all generated summaries by content and level
      </p>
    </div>

    <!-- Search Controls -->
    <div class="search-controls">
      <div class="search-bar">
        <i class="fas fa-search search-icon"></i>
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Search summaries..."
          class="search-input"
          @keydown.enter="handleSearch"
        />
      </div>

      <div class="filter-row">
        <select v-model="levelFilter" class="level-select">
          <option value="">All Levels</option>
          <option value="chunk">Chunk</option>
          <option value="section">Section</option>
          <option value="document">Document</option>
        </select>

        <button
          class="search-btn"
          :disabled="loading || !searchQuery.trim()"
          @click="handleSearch"
        >
          <i :class="loading ? 'fas fa-spinner fa-spin' : 'fas fa-search'"></i>
          Search
        </button>
      </div>
    </div>

    <!-- Error -->
    <div v-if="error" class="error-banner">
      <i class="fas fa-exclamation-triangle"></i>
      <span>{{ error }}</span>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      <span>Searching summaries...</span>
    </div>

    <!-- Empty -->
    <div
      v-else-if="hasSearched && summaries.length === 0"
      class="empty-state"
    >
      <i class="fas fa-search"></i>
      <p>No summaries found matching your search</p>
    </div>

    <!-- Results -->
    <div v-else-if="summaries.length > 0" class="results-list">
      <div
        v-for="summary in summaries"
        :key="summary.id"
        class="result-card"
        :class="{ expanded: expandedId === summary.id }"
      >
        <div
          class="result-header"
          @click="toggleExpand(summary.id)"
        >
          <div class="result-left">
            <span :class="['level-badge', summary.level]">
              {{ summary.level }}
            </span>
            <span v-if="summary.score" class="score-badge">
              {{ (summary.score * 100).toFixed(0) }}% match
            </span>
          </div>
          <i
            :class="[
              'fas',
              expandedId === summary.id
                ? 'fa-chevron-up'
                : 'fa-chevron-down',
            ]"
            class="expand-icon"
          />
        </div>

        <!-- Preview -->
        <p class="result-preview">
          {{ expandedId === summary.id
            ? summary.content
            : truncate(summary.content, 200)
          }}
        </p>

        <!-- Topics -->
        <div
          v-if="summary.key_topics.length > 0"
          class="result-topics"
        >
          <span
            v-for="topic in summary.key_topics"
            :key="topic"
            class="topic-badge"
          >
            {{ topic }}
          </span>
        </div>

        <!-- Expanded Actions -->
        <div
          v-if="expandedId === summary.id"
          class="result-actions"
        >
          <button
            class="action-btn"
            @click="$emit('drill-down', summary.id)"
          >
            <i class="fas fa-search-plus"></i>
            Drill Down
          </button>
          <span class="result-meta">
            Doc: {{ summary.document_id }}
          </span>
        </div>
      </div>

      <!-- Result Count -->
      <div class="result-count">
        {{ summaries.length }} results found
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref } from 'vue'
import { useKnowledgeGraph } from '@/composables/useKnowledgeGraph'

defineEmits<{
  (e: 'drill-down', summaryId: string): void
}>()

const {
  summaries,
  searchSummaries,
  loading,
  error,
} = useKnowledgeGraph()

const searchQuery = ref('')
const levelFilter = ref('')
const expandedId = ref<string | null>(null)
const hasSearched = ref(false)

function truncate(text: string, maxLen: number): string {
  if (!text || text.length <= maxLen) return text
  return text.slice(0, maxLen) + '...'
}

function toggleExpand(id: string): void {
  expandedId.value = expandedId.value === id ? null : id
}

async function handleSearch(): Promise<void> {
  if (!searchQuery.value.trim()) return
  hasSearched.value = true
  expandedId.value = null
  await searchSummaries({
    query: searchQuery.value,
    level: (levelFilter.value as 'chunk' | 'section' | 'document' | '') || undefined,
    top_k: 20,
  })
}
</script>

<style scoped>
.summary-search {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
  padding: var(--spacing-lg);
}

.search-header h4 {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin: 0;
}

.search-header h4 i {
  color: var(--color-primary);
}

.header-description {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  margin-top: var(--spacing-xs);
}

/* Search Controls */
.search-controls {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.search-bar {
  display: flex;
  align-items: center;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-xs) var(--spacing-sm);
  gap: var(--spacing-sm);
}

.search-icon {
  color: var(--text-tertiary);
}

.search-input {
  flex: 1;
  border: none;
  background: transparent;
  color: var(--text-primary);
  font-size: var(--text-sm);
  outline: none;
}

.search-input::placeholder {
  color: var(--text-tertiary);
}

.filter-row {
  display: flex;
  gap: var(--spacing-sm);
}

.level-select {
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.search-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-lg);
  background: var(--color-primary);
  border: none;
  border-radius: var(--radius-md);
  color: white;
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  cursor: pointer;
}

.search-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* States */
.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--spacing-2xl);
  color: var(--text-tertiary);
  gap: var(--spacing-md);
}

.loading-state i,
.empty-state i {
  font-size: var(--text-2xl);
}

.error-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-error-bg);
  border: 1px solid var(--color-error);
  border-radius: var(--radius-md);
  color: var(--color-error);
  font-size: var(--text-sm);
}

/* Results */
.results-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.result-card {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--spacing-md);
  transition: border-color var(--duration-200);
}

.result-card.expanded {
  border-color: var(--color-primary);
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
}

.result-left {
  display: flex;
  gap: var(--spacing-sm);
  align-items: center;
}

.level-badge {
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  padding: 2px var(--spacing-sm);
  border-radius: var(--radius-full);
  text-transform: capitalize;
}

.level-badge.chunk {
  background: rgba(34, 197, 94, 0.1);
  color: rgba(34, 197, 94, 0.9);
}

.level-badge.section {
  background: rgba(168, 85, 247, 0.1);
  color: rgba(168, 85, 247, 0.9);
}

.level-badge.document {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.score-badge {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.expand-icon {
  color: var(--text-tertiary);
  font-size: var(--text-sm);
}

.result-preview {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: 1.6;
  margin: var(--spacing-sm) 0 0 0;
}

.result-topics {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
  margin-top: var(--spacing-sm);
}

.topic-badge {
  font-size: var(--text-xs);
  padding: 1px var(--spacing-sm);
  background: var(--bg-secondary);
  border-radius: var(--radius-full);
  color: var(--text-secondary);
}

.result-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: var(--spacing-sm);
  padding-top: var(--spacing-sm);
  border-top: 1px solid var(--border-subtle);
}

.action-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-xs) var(--spacing-md);
  background: transparent;
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-md);
  color: var(--color-primary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--duration-200);
}

.action-btn:hover {
  background: var(--color-primary-bg);
}

.result-meta {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  font-family: 'Fira Code', monospace;
}

.result-count {
  text-align: center;
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

@media (max-width: 768px) {
  .filter-row {
    flex-direction: column;
  }

  .search-btn {
    justify-content: center;
  }
}
</style>
