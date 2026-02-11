<!-- AutoBot - Knowledge Graph Pipeline (Issue #759) -->
<template>
  <div class="relationship-viewer">
    <div class="viewer-header">
      <h4><i class="fas fa-sitemap"></i> Relationship Explorer</h4>
      <p class="header-description">
        View and filter relationships for an entity
      </p>
    </div>

    <!-- Controls -->
    <div class="viewer-controls">
      <div class="control-group">
        <label for="rel-type-filter">Filter by Type</label>
        <select
          id="rel-type-filter"
          v-model="selectedRelType"
          class="control-input"
        >
          <option value="">All Types</option>
          <option
            v-for="relType in uniqueRelTypes"
            :key="relType"
            :value="relType"
          >
            {{ relType }}
          </option>
        </select>
      </div>

      <div class="control-group">
        <label for="max-hops">
          Max Hops: <strong>{{ maxHops }}</strong>
        </label>
        <input
          id="max-hops"
          v-model.number="maxHops"
          type="range"
          min="1"
          max="5"
          step="1"
          class="range-input"
        />
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      <span>Loading relationships...</span>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="error-banner">
      <i class="fas fa-exclamation-triangle"></i>
      <span>{{ error }}</span>
    </div>

    <!-- Empty -->
    <div
      v-else-if="filteredRelationships.length === 0"
      class="empty-state"
    >
      <i class="fas fa-link"></i>
      <p>No relationships found</p>
    </div>

    <!-- Relationship Cards -->
    <div v-else class="relationship-list">
      <div
        v-for="rel in filteredRelationships"
        :key="rel.id"
        class="relationship-card"
      >
        <div class="rel-flow">
          <div class="rel-node source">
            <span class="node-type">{{ rel.source_type }}</span>
            <span class="node-name">{{ rel.source_entity }}</span>
          </div>

          <div class="rel-connector">
            <div class="connector-line" />
            <span class="connector-label">
              {{ rel.relationship_type }}
            </span>
            <div class="connector-arrow" />
          </div>

          <div class="rel-node target">
            <span class="node-type">{{ rel.target_type }}</span>
            <span class="node-name">{{ rel.target_entity }}</span>
          </div>
        </div>

        <div v-if="rel.description" class="rel-description">
          {{ rel.description }}
        </div>

        <div class="rel-meta">
          <span class="rel-confidence">
            <i class="fas fa-bullseye"></i>
            {{ (rel.confidence * 100).toFixed(0) }}%
          </span>
        </div>
      </div>
    </div>

    <!-- Summary -->
    <div
      v-if="filteredRelationships.length > 0"
      class="viewer-summary"
    >
      Showing {{ filteredRelationships.length }}
      of {{ relationships.length }} relationships
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, computed, onMounted, watch } from 'vue'
import { useKnowledgeGraph } from '@/composables/useKnowledgeGraph'

const props = defineProps<{
  entityId: string
}>()

const {
  relationships,
  getRelationships,
  loading,
  error,
} = useKnowledgeGraph()

const selectedRelType = ref('')
const maxHops = ref(1)

const uniqueRelTypes = computed(() => {
  const types = new Set(
    relationships.value.map(r => r.relationship_type)
  )
  return Array.from(types).sort()
})

const filteredRelationships = computed(() => {
  if (!selectedRelType.value) return relationships.value
  return relationships.value.filter(
    r => r.relationship_type === selectedRelType.value
  )
})

async function fetchRelationships(): Promise<void> {
  if (props.entityId) {
    await getRelationships(props.entityId)
  }
}

onMounted(fetchRelationships)

watch(() => props.entityId, fetchRelationships)
</script>

<style scoped>
.relationship-viewer {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
  padding: var(--spacing-lg);
}

.viewer-header h4 {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin: 0;
}

.viewer-header h4 i {
  color: var(--color-primary);
}

.header-description {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  margin-top: var(--spacing-xs);
}

/* Controls */
.viewer-controls {
  display: flex;
  gap: var(--spacing-lg);
  flex-wrap: wrap;
}

.control-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
  min-width: 200px;
}

.control-group label {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.control-input {
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.range-input {
  accent-color: var(--color-primary);
}

/* States */
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

/* Relationship Cards */
.relationship-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.relationship-card {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--spacing-md);
}

.rel-flow {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.rel-node {
  display: flex;
  flex-direction: column;
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  min-width: 100px;
}

.node-type {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  text-transform: uppercase;
}

.node-name {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.rel-connector {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  min-width: 80px;
}

.connector-line {
  width: 100%;
  height: 2px;
  background: var(--color-primary);
  position: relative;
}

.connector-label {
  font-size: var(--text-xs);
  color: var(--color-primary);
  font-weight: var(--font-medium);
  white-space: nowrap;
  background: var(--bg-primary);
  padding: 0 var(--spacing-xs);
}

.connector-arrow {
  width: 0;
  height: 0;
  border-left: 6px solid transparent;
  border-right: 6px solid transparent;
  border-top: 6px solid var(--color-primary);
  transform: rotate(-90deg);
  position: absolute;
  right: -3px;
}

.rel-description {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-top: var(--spacing-sm);
  padding-top: var(--spacing-sm);
  border-top: 1px solid var(--border-subtle);
}

.rel-meta {
  display: flex;
  gap: var(--spacing-md);
  margin-top: var(--spacing-sm);
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.rel-confidence {
  display: flex;
  align-items: center;
  gap: 4px;
}

.viewer-summary {
  text-align: center;
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

@media (max-width: 768px) {
  .rel-flow {
    flex-direction: column;
  }

  .rel-node {
    width: 100%;
  }

  .rel-connector {
    transform: rotate(90deg);
    width: 60px;
  }

  .viewer-controls {
    flex-direction: column;
  }
}
</style>
