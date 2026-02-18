<!-- AutoBot - Knowledge Graph Pipeline (Issue #759) -->
<template>
  <div class="summaries-page">
    <!-- View Toggle -->
    <div class="view-toggle">
      <button
        :class="['toggle-btn', { active: view === 'search' }]"
        @click="view = 'search'"
      >
        <i class="fas fa-search"></i> Search
      </button>
      <button
        :class="['toggle-btn', { active: view === 'overview' }]"
        @click="view = 'overview'"
      >
        <i class="fas fa-file-alt"></i> Document Overview
      </button>
    </div>

    <!-- Search View -->
    <SummarySearch
      v-if="view === 'search' && !drillDownId"
      @drill-down="handleDrillDown"
    />

    <!-- Document Overview View -->
    <div v-if="view === 'overview' && !drillDownId" class="overview-section">
      <div class="doc-id-input">
        <label for="doc-id">Document ID</label>
        <div class="input-row">
          <input
            id="doc-id"
            v-model="documentId"
            type="text"
            placeholder="Enter document ID..."
            class="form-input"
            @keydown.enter="loadOverview"
          />
          <button
            class="load-btn"
            :disabled="!documentId.trim()"
            @click="loadOverview"
          >
            <i class="fas fa-eye"></i> Load
          </button>
        </div>
      </div>

      <DocumentOverview
        v-if="activeDocId"
        :document-id="activeDocId"
        @drill-down="handleDrillDown"
      />
    </div>

    <!-- Drill-Down View -->
    <div v-if="drillDownId" class="drill-down-section">
      <button class="back-btn" @click="drillDownId = null">
        <i class="fas fa-arrow-left"></i> Back to
        {{ view === 'search' ? 'Search' : 'Overview' }}
      </button>
      <DrillDownViewer :summary-id="drillDownId" />
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref } from 'vue'
import SummarySearch from './SummarySearch.vue'
import DocumentOverview from './DocumentOverview.vue'
import DrillDownViewer from './DrillDownViewer.vue'

const view = ref<'search' | 'overview'>('search')
const documentId = ref('')
const activeDocId = ref('')
const drillDownId = ref<string | null>(null)

function loadOverview(): void {
  if (documentId.value.trim()) {
    activeDocId.value = documentId.value.trim()
  }
}

function handleDrillDown(summaryId: string): void {
  drillDownId.value = summaryId
}
</script>

<style scoped>
.summaries-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow-y: auto;
}

/* View Toggle */
.view-toggle {
  display: flex;
  gap: var(--spacing-xs);
  padding: var(--spacing-md) var(--spacing-lg) 0;
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  margin: var(--spacing-md) var(--spacing-lg) 0;
  padding: var(--spacing-xs);
}

.toggle-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border: none;
  background: transparent;
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--duration-200);
}

.toggle-btn:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}

.toggle-btn.active {
  background: var(--bg-card);
  color: var(--color-primary);
  box-shadow: var(--shadow-sm);
}

/* Overview Section */
.overview-section {
  display: flex;
  flex-direction: column;
}

.doc-id-input {
  padding: var(--spacing-lg);
  padding-bottom: 0;
}

.doc-id-input label {
  display: block;
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin-bottom: var(--spacing-xs);
}

.input-row {
  display: flex;
  gap: var(--spacing-sm);
}

.form-input {
  flex: 1;
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.form-input:focus {
  outline: none;
  border-color: var(--color-primary);
}

.load-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-primary);
  border: none;
  border-radius: var(--radius-md);
  color: white;
  font-size: var(--text-sm);
  cursor: pointer;
}

.load-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Drill-Down Section */
.drill-down-section {
  display: flex;
  flex-direction: column;
}

.back-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin: var(--spacing-md) var(--spacing-lg) 0;
  padding: var(--spacing-xs) var(--spacing-md);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: var(--text-sm);
  cursor: pointer;
  align-self: flex-start;
}

.back-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
</style>
