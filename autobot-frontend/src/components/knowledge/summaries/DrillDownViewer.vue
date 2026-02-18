<!-- AutoBot - Knowledge Graph Pipeline (Issue #759) -->
<template>
  <div class="drill-down-viewer">
    <!-- Loading -->
    <div v-if="loading" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      <span>Loading drill-down data...</span>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="error-banner">
      <i class="fas fa-exclamation-triangle"></i>
      <span>{{ error }}</span>
    </div>

    <!-- Content -->
    <template v-else-if="drillDownData">
      <!-- Breadcrumb Navigation -->
      <nav class="breadcrumb-nav" aria-label="Summary hierarchy">
        <span
          v-for="(crumb, index) in drillDownData.breadcrumb"
          :key="crumb.id"
          class="breadcrumb-item"
        >
          <button
            v-if="index < drillDownData.breadcrumb.length - 1"
            class="breadcrumb-link"
            @click="navigateTo(crumb.id)"
          >
            <span :class="['crumb-level', crumb.level]">
              {{ crumb.level }}
            </span>
            {{ crumb.label }}
          </button>
          <span v-else class="breadcrumb-current">
            <span :class="['crumb-level', crumb.level]">
              {{ crumb.level }}
            </span>
            {{ crumb.label }}
          </span>
          <i
            v-if="index < drillDownData.breadcrumb.length - 1"
            class="fas fa-chevron-right breadcrumb-sep"
          />
        </span>
      </nav>

      <!-- Current Summary -->
      <div class="current-summary">
        <div class="summary-header">
          <span :class="['level-badge', drillDownData.summary.level]">
            {{ drillDownData.summary.level }}
          </span>
          <div
            v-if="drillDownData.summary.key_topics.length > 0"
            class="summary-topics"
          >
            <span
              v-for="topic in drillDownData.summary.key_topics"
              :key="topic"
              class="topic-badge"
            >
              {{ topic }}
            </span>
          </div>
        </div>

        <p class="summary-content">
          {{ drillDownData.summary.content }}
        </p>
      </div>

      <!-- Parent Link -->
      <div
        v-if="drillDownData.parent"
        class="parent-section"
      >
        <h5><i class="fas fa-arrow-up"></i> Parent Summary</h5>
        <div
          class="parent-card"
          @click="navigateTo(drillDownData.parent.id)"
        >
          <span :class="['level-badge', drillDownData.parent.level]">
            {{ drillDownData.parent.level }}
          </span>
          <p>{{ truncate(drillDownData.parent.content, 150) }}</p>
        </div>
      </div>

      <!-- Children Summaries -->
      <div
        v-if="drillDownData.children.length > 0"
        class="children-section"
      >
        <h5>
          <i class="fas fa-arrow-down"></i>
          Sub-summaries ({{ drillDownData.children.length }})
        </h5>
        <div class="children-list">
          <div
            v-for="child in drillDownData.children"
            :key="child.id"
            class="child-card"
            @click="navigateTo(child.id)"
          >
            <div class="child-header">
              <span :class="['level-badge', child.level]">
                {{ child.level }}
              </span>
              <div class="child-topics">
                <span
                  v-for="topic in child.key_topics.slice(0, 3)"
                  :key="topic"
                  class="mini-topic"
                >
                  {{ topic }}
                </span>
              </div>
            </div>
            <p>{{ truncate(child.content, 200) }}</p>
          </div>
        </div>
      </div>

      <!-- Source Chunks -->
      <div
        v-if="drillDownData.source_chunks.length > 0"
        class="chunks-section"
      >
        <h5>
          <i class="fas fa-file-code"></i>
          Source Chunks ({{ drillDownData.source_chunks.length }})
        </h5>
        <button
          class="toggle-chunks-btn"
          @click="showChunks = !showChunks"
        >
          <i :class="showChunks ? 'fas fa-eye-slash' : 'fas fa-eye'"></i>
          {{ showChunks ? 'Hide' : 'Show' }} Source Chunks
        </button>

        <div v-if="showChunks" class="chunks-list">
          <div
            v-for="chunk in drillDownData.source_chunks"
            :key="chunk.id"
            class="chunk-card"
          >
            <span class="chunk-id">{{ chunk.id }}</span>
            <pre class="chunk-content">{{ chunk.content }}</pre>
          </div>
        </div>
      </div>
    </template>

    <!-- No Data -->
    <div v-else class="empty-state">
      <i class="fas fa-search-plus"></i>
      <p>Select a summary to drill down into</p>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, onMounted, watch } from 'vue'
import {
  useKnowledgeGraph,
  type DrillDownResult,
} from '@/composables/useKnowledgeGraph'

const props = defineProps<{
  summaryId: string
}>()

const { drillDown, loading, error } = useKnowledgeGraph()
const drillDownData = ref<DrillDownResult | null>(null)
const showChunks = ref(false)

function truncate(text: string, maxLen: number): string {
  if (!text || text.length <= maxLen) return text
  return text.slice(0, maxLen) + '...'
}

async function loadDrillDown(id: string): Promise<void> {
  if (!id) return
  showChunks.value = false
  drillDownData.value = await drillDown(id)
}

function navigateTo(summaryId: string): void {
  loadDrillDown(summaryId)
}

onMounted(() => loadDrillDown(props.summaryId))
watch(() => props.summaryId, (newId) => loadDrillDown(newId))
</script>

<style scoped>
.drill-down-viewer {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
  padding: var(--spacing-lg);
}

/* Breadcrumb */
.breadcrumb-nav {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
}

.breadcrumb-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.breadcrumb-link {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  background: none;
  border: none;
  color: var(--color-primary);
  font-size: var(--text-sm);
  cursor: pointer;
  padding: 0;
}

.breadcrumb-link:hover {
  text-decoration: underline;
}

.breadcrumb-current {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.breadcrumb-sep {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.crumb-level {
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  padding: 1px var(--spacing-xs);
  border-radius: var(--radius-sm);
  text-transform: capitalize;
}

.crumb-level.chunk {
  background: rgba(34, 197, 94, 0.1);
  color: rgba(34, 197, 94, 0.9);
}

.crumb-level.section {
  background: rgba(168, 85, 247, 0.1);
  color: rgba(168, 85, 247, 0.9);
}

.crumb-level.document {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

/* Current Summary */
.current-summary {
  background: var(--bg-card);
  border: 2px solid var(--color-primary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
}

.summary-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-md);
  flex-wrap: wrap;
}

.level-badge {
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  padding: 2px var(--spacing-sm);
  border-radius: var(--radius-full);
  text-transform: capitalize;
  flex-shrink: 0;
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

.summary-topics {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
}

.topic-badge {
  font-size: var(--text-xs);
  padding: 1px var(--spacing-sm);
  background: var(--bg-secondary);
  border-radius: var(--radius-full);
  color: var(--text-secondary);
}

.summary-content {
  font-size: var(--text-sm);
  color: var(--text-primary);
  line-height: 1.7;
  margin: 0;
}

/* Sections */
h5 {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin: 0;
}

h5 i {
  color: var(--color-primary);
  font-size: var(--text-sm);
}

/* Parent */
.parent-card {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: var(--spacing-sm) var(--spacing-md);
  cursor: pointer;
  transition: border-color var(--duration-200);
  margin-top: var(--spacing-sm);
}

.parent-card:hover {
  border-color: var(--color-primary);
}

.parent-card p {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: var(--spacing-xs) 0 0 0;
}

/* Children */
.children-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-sm);
}

.child-card {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: var(--spacing-sm) var(--spacing-md);
  cursor: pointer;
  transition: border-color var(--duration-200);
}

.child-card:hover {
  border-color: var(--color-primary);
}

.child-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.child-topics {
  display: flex;
  gap: var(--spacing-xs);
}

.mini-topic {
  font-size: var(--text-xs);
  padding: 1px var(--spacing-xs);
  background: var(--bg-secondary);
  border-radius: var(--radius-full);
  color: var(--text-tertiary);
}

.child-card p {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: var(--spacing-xs) 0 0 0;
}

/* Chunks */
.toggle-chunks-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  margin-top: var(--spacing-sm);
  padding: var(--spacing-xs) var(--spacing-md);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: var(--text-sm);
  cursor: pointer;
}

.toggle-chunks-btn:hover {
  background: var(--bg-hover);
}

.chunks-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-sm);
}

.chunk-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: var(--spacing-sm) var(--spacing-md);
}

.chunk-id {
  font-size: var(--text-xs);
  font-family: 'Fira Code', monospace;
  color: var(--text-tertiary);
}

.chunk-content {
  font-size: var(--text-sm);
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
  margin: var(--spacing-xs) 0 0 0;
  font-family: inherit;
  line-height: 1.5;
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
</style>
