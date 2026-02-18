<template>
  <BasePanel v-if="show" variant="bordered" size="medium">
    <template #header>
      <h3><i class="fas fa-search"></i> Search Man Page Knowledge</h3>
    </template>

    <div class="search-input">
      <input
        :value="query"
        @input="$emit('update:query', ($event.target as HTMLInputElement).value)"
        @keyup.enter="$emit('search')"
        type="text"
        placeholder="Search for commands, patterns, network tools, etc..."
        class="form-input"
      >
      <BaseButton
        variant="primary"
        @click="$emit('search')"
        :disabled="!query.trim() || loading"
      >
        <i class="fas fa-search"></i>
        Search
      </BaseButton>
    </div>

    <div v-if="results" class="search-results">
      <h4>Search Results for "{{ lastQuery }}":</h4>

      <EmptyState
        v-if="results.length === 0"
        icon="fas fa-info-circle"
        message='No results found. Try different keywords like "network", "file", "process".'
      />

      <div v-else class="result-list">
        <div v-for="result in results" :key="result.command" class="result-item">
          <div class="result-header">
            <strong>{{ result.command }}</strong>
            <span class="relevance-score">Score: {{ result.relevance_score }}</span>
          </div>
          <div class="result-purpose">{{ result.purpose }}</div>
          <div class="result-meta">
            <span class="source">{{ result.source }}</span> •
            <span class="machine">{{ result.machine_id }}</span>
          </div>
        </div>
      </div>
    </div>
  </BasePanel>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Man Page Search Panel Component
 *
 * Provides search functionality for man page knowledge.
 * Extracted from ManPageManager.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import BasePanel from '@/components/base/BasePanel.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import EmptyState from '@/components/ui/EmptyState.vue'

interface SearchResult {
  command: string
  purpose: string
  relevance_score: number
  source: string
  machine_id: string
}

interface Props {
  show: boolean
  query: string
  lastQuery: string
  results: SearchResult[] | null
  loading?: boolean
}

interface Emits {
  (e: 'update:query', value: string): void
  (e: 'search'): void
}

withDefaults(defineProps<Props>(), {
  loading: false
})

defineEmits<Emits>()
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.search-input {
  display: flex;
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}

.form-input {
  flex: 1;
  padding: var(--spacing-3) var(--spacing-4);
  border: 2px solid var(--border-light, #ecf0f1);
  border-radius: var(--radius-md);
  font-size: var(--text-base);
  background: var(--bg-primary);
  color: var(--text-primary);
}

.form-input:focus {
  outline: none;
  border-color: var(--color-info);
}

.search-results h4 {
  margin-bottom: var(--spacing-5);
  color: var(--text-primary);
}

.result-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.result-item {
  background: var(--bg-surface, white);
  padding: var(--spacing-4);
  border-radius: var(--radius-lg);
  border-left: 4px solid var(--color-info);
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-2);
}

.result-header strong {
  color: var(--text-primary);
  font-family: var(--font-mono);
}

.relevance-score {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  background: var(--bg-tertiary);
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-full);
}

.result-purpose {
  color: var(--text-primary);
  margin-bottom: var(--spacing-2);
}

.result-meta {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.source {
  font-style: italic;
}

.machine {
  font-family: 'Courier New', monospace;
}

@media (max-width: 768px) {
  .search-input {
    flex-direction: column;
  }
}
</style>
