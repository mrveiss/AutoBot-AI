<!-- AutoBot - Knowledge Graph Pipeline (Issue #759) -->
<template>
  <div class="graph-explorer">
    <div class="explorer-header">
      <h4><i class="fas fa-project-diagram"></i> Entity Explorer</h4>
      <p class="header-description">
        Search and browse entities in the knowledge graph
      </p>
    </div>

    <!-- Search Bar -->
    <div class="search-section">
      <div class="search-bar">
        <i class="fas fa-search search-icon"></i>
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Search entities by name or description..."
          class="search-input"
          @keydown.enter="handleSearch"
        />
        <button
          class="search-btn"
          aria-label="Search entities"
          :disabled="loading || !searchQuery.trim()"
          @click="handleSearch"
        >
          <i :class="loading ? 'fas fa-spinner fa-spin' : 'fas fa-search'"></i>
        </button>
      </div>

      <!-- Type Filters -->
      <div class="type-filters">
        <span class="filter-label">Types:</span>
        <label
          v-for="entityType in entityTypes"
          :key="entityType"
          class="type-checkbox"
        >
          <input
            v-model="selectedTypes"
            :value="entityType"
            type="checkbox"
          />
          <span
            class="type-badge"
            :style="{ backgroundColor: getTypeColor(entityType) }"
          >
            {{ entityType }}
          </span>
        </label>
      </div>
    </div>

    <!-- Error State -->
    <div v-if="error" class="error-banner">
      <i class="fas fa-exclamation-triangle"></i>
      <span>{{ error }}</span>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      <span>Searching entities...</span>
    </div>

    <!-- Empty State -->
    <div
      v-else-if="hasSearched && entities.length === 0"
      class="empty-state"
    >
      <i class="fas fa-search"></i>
      <p>No entities found matching your search</p>
    </div>

    <!-- Results Grid -->
    <div v-else-if="entities.length > 0" class="entity-grid">
      <div
        v-for="entity in entities"
        :key="entity.id"
        class="entity-card"
        :class="{ selected: selectedEntity?.id === entity.id }"
        @click="selectEntity(entity)"
      >
        <div class="entity-card-header">
          <span
            class="entity-type-indicator"
            :style="{ backgroundColor: getTypeColor(entity.type) }"
          />
          <span class="entity-name">{{ entity.name }}</span>
        </div>
        <span
          class="entity-type-badge"
          :style="{ color: getTypeColor(entity.type) }"
        >
          {{ entity.type }}
        </span>
        <p class="entity-description">
          {{ truncateText(entity.description, 120) }}
        </p>
        <div class="entity-meta">
          <span class="confidence-score">
            <i class="fas fa-bullseye"></i>
            {{ (entity.confidence * 100).toFixed(0) }}%
          </span>
          <span class="source-count">
            <i class="fas fa-file-alt"></i>
            {{ entity.source_document_ids.length }} sources
          </span>
        </div>
      </div>
    </div>

    <!-- Detail Panel -->
    <EntityDetail
      v-if="selectedEntity"
      :entity="selectedEntity"
      @close="selectedEntity = null"
      @view-timeline="handleViewTimeline"
    />
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  useKnowledgeGraph,
  type Entity,
} from '@/composables/useKnowledgeGraph'
import EntityDetail from './EntityDetail.vue'
import { getEntityTypeColor as getTypeColor } from '../constants'

const router = useRouter()
const {
  entities,
  searchEntities,
  loading,
  error,
} = useKnowledgeGraph()

const searchQuery = ref('')
const selectedTypes = ref<string[]>([])
const selectedEntity = ref<Entity | null>(null)
const hasSearched = ref(false)

const entityTypes = [
  'person', 'organization', 'location', 'concept',
  'technology', 'event', 'document', 'other',
]

function truncateText(text: string, maxLen: number): string {
  if (!text) return ''
  if (text.length <= maxLen) return text
  return text.slice(0, maxLen) + '...'
}

async function handleSearch(): Promise<void> {
  if (!searchQuery.value.trim()) return
  hasSearched.value = true
  selectedEntity.value = null
  await searchEntities({
    query: searchQuery.value,
    entity_types: selectedTypes.value.length > 0
      ? selectedTypes.value
      : undefined,
    limit: 50,
  })
}

function selectEntity(entity: Entity): void {
  selectedEntity.value = entity
}

function handleViewTimeline(entityName: string): void {
  router.push({
    path: '/knowledge/graph/timeline',
    query: { entity: entityName },
  })
}
</script>

<style scoped>
.graph-explorer {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
  padding: var(--spacing-lg);
}

.explorer-header h4 {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin: 0;
}

.explorer-header h4 i {
  color: var(--color-primary);
}

.header-description {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  margin-top: var(--spacing-xs);
}

/* Search */
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
  font-size: var(--text-sm);
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

.search-btn {
  padding: var(--spacing-xs) var(--spacing-sm);
  background: var(--color-primary);
  border: none;
  border-radius: var(--radius-md);
  color: white;
  cursor: pointer;
}

.search-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Type Filters */
.type-filters {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
  margin-top: var(--spacing-sm);
}

.filter-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  font-weight: var(--font-medium);
}

.type-checkbox {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
}

.type-checkbox input {
  display: none;
}

.type-badge {
  font-size: var(--text-xs);
  padding: 2px var(--spacing-sm);
  border-radius: var(--radius-full);
  color: white;
  opacity: 0.5;
  transition: opacity var(--duration-200);
}

.type-checkbox input:checked + .type-badge {
  opacity: 1;
}

/* States */
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

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-2xl);
  color: var(--text-tertiary);
  gap: var(--spacing-md);
}

.loading-state i,
.empty-state i {
  font-size: var(--text-2xl);
}

/* Entity Grid */
.entity-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--spacing-md);
}

.entity-card {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--spacing-md);
  cursor: pointer;
  transition: all var(--duration-200);
}

.entity-card:hover {
  border-color: var(--border-strong);
  box-shadow: var(--shadow-sm);
}

.entity-card.selected {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 1px var(--color-primary);
}

.entity-card-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-xs);
}

.entity-type-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.entity-name {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.entity-type-badge {
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  text-transform: uppercase;
}

.entity-description {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: var(--spacing-sm) 0;
  line-height: 1.5;
}

.entity-meta {
  display: flex;
  gap: var(--spacing-md);
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.entity-meta i {
  margin-right: 4px;
}

.confidence-score,
.source-count {
  display: flex;
  align-items: center;
}

@media (max-width: 768px) {
  .entity-grid {
    grid-template-columns: 1fr;
  }

  .type-filters {
    overflow-x: auto;
    flex-wrap: nowrap;
    -webkit-overflow-scrolling: touch;
  }
}
</style>
