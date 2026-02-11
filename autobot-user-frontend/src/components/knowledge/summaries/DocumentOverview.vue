<!-- AutoBot - Knowledge Graph Pipeline (Issue #759) -->
<template>
  <div class="document-overview">
    <!-- Loading -->
    <div v-if="loading" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      <span>Loading document overview...</span>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="error-banner">
      <i class="fas fa-exclamation-triangle"></i>
      <span>{{ error }}</span>
    </div>

    <!-- Overview Content -->
    <template v-else-if="overview">
      <!-- Document Header -->
      <div class="overview-header">
        <h4>
          <i class="fas fa-file-alt"></i>
          {{ overview.title || 'Document Overview' }}
        </h4>
        <div class="header-stats">
          <span class="header-stat">
            <i class="fas fa-circle"></i>
            {{ overview.entity_count }} entities
          </span>
          <span class="header-stat">
            <i class="fas fa-clock"></i>
            {{ overview.event_count }} events
          </span>
        </div>
      </div>

      <!-- Key Topics -->
      <div
        v-if="overview.key_topics.length > 0"
        class="topics-section"
      >
        <span
          v-for="topic in overview.key_topics"
          :key="topic"
          class="topic-badge"
        >
          {{ topic }}
        </span>
      </div>

      <!-- Document Summary -->
      <div
        v-if="overview.document_summary"
        class="summary-card document-level"
      >
        <div class="summary-card-header">
          <span class="level-badge document">Document Summary</span>
        </div>
        <p class="summary-content">
          {{ overview.document_summary.content }}
        </p>
        <div
          v-if="overview.document_summary.key_topics.length > 0"
          class="summary-topics"
        >
          <span
            v-for="topic in overview.document_summary.key_topics"
            :key="topic"
            class="mini-topic"
          >
            {{ topic }}
          </span>
        </div>
      </div>

      <!-- Section Summaries -->
      <div
        v-if="overview.section_summaries.length > 0"
        class="sections-list"
      >
        <h5>
          <i class="fas fa-layer-group"></i>
          Sections ({{ overview.section_summaries.length }})
        </h5>

        <div
          v-for="section in overview.section_summaries"
          :key="section.id"
          class="summary-card section-level"
        >
          <div
            class="summary-card-header"
            @click="toggleSection(section.id)"
          >
            <span class="level-badge section">Section</span>
            <div class="section-topics-preview">
              <span
                v-for="topic in section.key_topics.slice(0, 3)"
                :key="topic"
                class="mini-topic"
              >
                {{ topic }}
              </span>
            </div>
            <i
              :class="[
                'fas',
                expandedSections.has(section.id)
                  ? 'fa-chevron-up'
                  : 'fa-chevron-down',
              ]"
              class="expand-icon"
            />
          </div>

          <div v-if="expandedSections.has(section.id)">
            <p class="summary-content">{{ section.content }}</p>

            <button
              class="drill-down-btn"
              @click="$emit('drill-down', section.id)"
            >
              <i class="fas fa-search-plus"></i>
              Drill Down
            </button>
          </div>
        </div>
      </div>
    </template>

    <!-- No Data -->
    <div v-else class="empty-state">
      <i class="fas fa-file-alt"></i>
      <p>Enter a document ID to view its overview</p>
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
  type DocumentOverview,
} from '@/composables/useKnowledgeGraph'

const props = defineProps<{
  documentId: string
}>()

defineEmits<{
  (e: 'drill-down', summaryId: string): void
}>()

const { getOverview, loading, error } = useKnowledgeGraph()
const overview = ref<DocumentOverview | null>(null)
const expandedSections = ref(new Set<string>())

function toggleSection(sectionId: string): void {
  if (expandedSections.value.has(sectionId)) {
    expandedSections.value.delete(sectionId)
  } else {
    expandedSections.value.add(sectionId)
  }
}

async function loadOverview(): Promise<void> {
  if (!props.documentId) return
  expandedSections.value.clear()
  overview.value = await getOverview(props.documentId)
}

onMounted(loadOverview)
watch(() => props.documentId, loadOverview)
</script>

<style scoped>
.document-overview {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
  padding: var(--spacing-lg);
}

/* Header */
.overview-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: var(--spacing-sm);
}

.overview-header h4 {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin: 0;
}

.overview-header h4 i {
  color: var(--color-primary);
}

.header-stats {
  display: flex;
  gap: var(--spacing-md);
}

.header-stat {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 4px;
}

.header-stat i {
  font-size: var(--text-xs);
  color: var(--color-primary);
}

/* Topics */
.topics-section {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
}

.topic-badge {
  font-size: var(--text-sm);
  padding: var(--spacing-xs) var(--spacing-md);
  background: var(--color-primary-bg);
  color: var(--color-primary);
  border-radius: var(--radius-full);
  font-weight: var(--font-medium);
}

/* Summary Cards */
.summary-card {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--spacing-md);
}

.summary-card.document-level {
  border-left: 4px solid var(--color-primary);
}

.summary-card.section-level {
  border-left: 4px solid rgba(168, 85, 247, 0.8);
}

.summary-card-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  cursor: pointer;
}

.level-badge {
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  padding: 2px var(--spacing-sm);
  border-radius: var(--radius-full);
  flex-shrink: 0;
}

.level-badge.document {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.level-badge.section {
  background: rgba(168, 85, 247, 0.1);
  color: rgba(168, 85, 247, 0.9);
}

.section-topics-preview {
  display: flex;
  gap: var(--spacing-xs);
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.expand-icon {
  color: var(--text-tertiary);
  font-size: var(--text-sm);
  flex-shrink: 0;
}

.summary-content {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: 1.7;
  margin: var(--spacing-sm) 0 0 0;
}

.summary-topics {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
  margin-top: var(--spacing-sm);
}

.mini-topic {
  font-size: var(--text-xs);
  padding: 1px var(--spacing-sm);
  background: var(--bg-secondary);
  border-radius: var(--radius-full);
  color: var(--text-secondary);
}

/* Sections */
.sections-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.sections-list h5 {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin: 0;
}

.sections-list h5 i {
  color: var(--color-primary);
}

.drill-down-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  margin-top: var(--spacing-sm);
  padding: var(--spacing-xs) var(--spacing-md);
  background: transparent;
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-md);
  color: var(--color-primary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--duration-200);
}

.drill-down-btn:hover {
  background: var(--color-primary-bg);
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

@media (max-width: 768px) {
  .overview-header {
    flex-direction: column;
  }
}
</style>
