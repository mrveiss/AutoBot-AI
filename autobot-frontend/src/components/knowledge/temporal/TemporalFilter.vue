<!-- AutoBot - Knowledge Graph Pipeline (Issue #759) -->
<template>
  <div class="temporal-filter">
    <h5><i class="fas fa-filter"></i> Event Filters</h5>

    <!-- Date Range -->
    <div class="filter-group">
      <label for="start-date">Start Date</label>
      <input
        id="start-date"
        v-model="filters.start_date"
        type="datetime-local"
        class="filter-input"
      />
    </div>

    <div class="filter-group">
      <label for="end-date">End Date</label>
      <input
        id="end-date"
        v-model="filters.end_date"
        type="datetime-local"
        class="filter-input"
      />
    </div>

    <!-- Event Type Checkboxes -->
    <div class="filter-group">
      <label>Event Types</label>
      <div class="checkbox-list">
        <label
          v-for="eventType in eventTypes"
          :key="eventType.value"
          class="checkbox-item"
        >
          <input
            v-model="filters.event_types"
            :value="eventType.value"
            type="checkbox"
          />
          <span
            class="type-dot"
            :style="{ backgroundColor: eventType.color }"
          />
          <span>{{ eventType.label }}</span>
        </label>
      </div>
    </div>

    <!-- Entity Name Filter -->
    <div class="filter-group">
      <label for="entity-filter">Entity Name</label>
      <input
        id="entity-filter"
        v-model="filters.entity_name"
        type="text"
        placeholder="Filter by entity..."
        class="filter-input"
      />
    </div>

    <!-- Actions -->
    <div class="filter-actions">
      <button class="filter-btn secondary" @click="resetFilters">
        <i class="fas fa-undo"></i> Reset
      </button>
      <button class="filter-btn primary" @click="applyFilters">
        <i class="fas fa-search"></i> Search
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { reactive } from 'vue'

const emit = defineEmits<{
  (e: 'filter-change', filters: {
    start_date?: string
    end_date?: string
    event_types?: string[]
    entity_name?: string
  }): void
}>()

const eventTypes = [
  { value: 'action', label: 'Action', color: 'rgba(59, 130, 246, 0.9)' },
  { value: 'decision', label: 'Decision', color: 'rgba(168, 85, 247, 0.9)' },
  { value: 'change', label: 'Change', color: 'rgba(249, 115, 22, 0.9)' },
  { value: 'milestone', label: 'Milestone', color: 'rgba(34, 197, 94, 0.9)' },
  { value: 'occurrence', label: 'Occurrence', color: 'rgba(107, 114, 128, 0.9)' },
]

const filters = reactive({
  start_date: '',
  end_date: '',
  event_types: [] as string[],
  entity_name: '',
})

function applyFilters(): void {
  emit('filter-change', {
    start_date: filters.start_date || undefined,
    end_date: filters.end_date || undefined,
    event_types: filters.event_types.length > 0
      ? filters.event_types
      : undefined,
    entity_name: filters.entity_name || undefined,
  })
}

function resetFilters(): void {
  filters.start_date = ''
  filters.end_date = ''
  filters.event_types = []
  filters.entity_name = ''
  applyFilters()
}
</script>

<style scoped>
.temporal-filter {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
  padding: var(--spacing-md);
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
}

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
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.filter-group > label {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-secondary);
}

.filter-input {
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.filter-input:focus {
  outline: none;
  border-color: var(--color-primary);
}

/* Checkboxes */
.checkbox-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.checkbox-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--text-sm);
  color: var(--text-primary);
  cursor: pointer;
}

.checkbox-item input {
  accent-color: var(--color-primary);
}

.type-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

/* Actions */
.filter-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.filter-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  cursor: pointer;
  transition: all var(--duration-200);
}

.filter-btn.secondary {
  background: transparent;
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
}

.filter-btn.secondary:hover {
  background: var(--bg-hover);
}

.filter-btn.primary {
  background: var(--color-primary);
  border: none;
  color: white;
}

.filter-btn.primary:hover {
  opacity: 0.9;
}
</style>
