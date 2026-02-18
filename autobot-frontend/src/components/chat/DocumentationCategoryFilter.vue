<template>
  <div class="doc-category-filter">
    <div class="filter-header">
      <h4 class="filter-title">
        <i class="fas fa-filter" aria-hidden="true"></i>
        Categories
      </h4>
      <button
        v-if="selectedCategories.length > 0"
        class="clear-btn"
        @click="clearSelection"
        aria-label="Clear category filters"
      >
        Clear
      </button>
    </div>

    <div v-if="isLoading" class="loading-state">
      <i class="fas fa-spinner fa-spin" aria-hidden="true"></i>
      <span>Loading categories...</span>
    </div>

    <div v-else-if="error" class="error-state">
      <i class="fas fa-exclamation-triangle" aria-hidden="true"></i>
      <span>{{ error }}</span>
      <button class="retry-btn" @click="$emit('retry')">Retry</button>
    </div>

    <div v-else class="category-list" role="group" aria-label="Documentation categories">
      <button
        v-for="category in sortedCategories"
        :key="category.id"
        class="category-item"
        :class="{
          'selected': isSelected(category.id),
          [`category-${category.id}`]: true
        }"
        @click="toggleCategory(category.id)"
        :aria-pressed="isSelected(category.id)"
        :title="category.description"
      >
        <span class="category-icon">
          <i :class="getCategoryIcon(category.id)" aria-hidden="true"></i>
        </span>
        <span class="category-name">{{ category.name }}</span>
        <span class="category-count">{{ category.count }}</span>
      </button>
    </div>

    <!-- Quick filters -->
    <div v-if="!isLoading && !error && categories.length > 0" class="quick-filters">
      <button
        class="quick-filter-btn"
        :class="{ 'active': showAllSelected }"
        @click="selectAll"
        aria-label="Select all categories"
      >
        All
      </button>
      <button
        class="quick-filter-btn"
        :class="{ 'active': showDevSelected }"
        @click="selectDeveloper"
        aria-label="Select developer categories"
      >
        Dev
      </button>
      <button
        class="quick-filter-btn"
        :class="{ 'active': showDocsSelected }"
        @click="selectDocumentation"
        aria-label="Select documentation categories"
      >
        Docs
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Documentation Category Filter Component
 *
 * Provides category filtering for documentation search results.
 * Supports single and multi-select modes with quick filter presets.
 *
 * Issue #165: Chat Documentation UI Integration
 */

import { computed } from 'vue'

interface Category {
  id: string
  name: string
  description?: string
  count: number
}

interface Props {
  categories: Category[]
  selectedCategories: string[]
  isLoading?: boolean
  error?: string | null
  multiSelect?: boolean
}

interface Emits {
  (e: 'update:selectedCategories', value: string[]): void
  (e: 'category-change', categories: string[]): void
  (e: 'retry'): void
}

const props = withDefaults(defineProps<Props>(), {
  isLoading: false,
  error: null,
  multiSelect: true
})

const emit = defineEmits<Emits>()

// Category icon mapping
const categoryIcons: Record<string, string> = {
  architecture: 'fas fa-project-diagram',
  developer: 'fas fa-code',
  api: 'fas fa-plug',
  troubleshooting: 'fas fa-wrench',
  deployment: 'fas fa-rocket',
  security: 'fas fa-shield-alt',
  features: 'fas fa-star',
  testing: 'fas fa-vial',
  workflow: 'fas fa-sitemap',
  guides: 'fas fa-book',
  implementation: 'fas fa-cogs',
  agents: 'fas fa-robot',
  general: 'fas fa-file-alt'
}

// Developer-focused categories
const devCategories = ['developer', 'api', 'architecture', 'implementation', 'testing']
// Documentation-focused categories
const docCategories = ['guides', 'features', 'troubleshooting', 'deployment']

const sortedCategories = computed(() => {
  return [...props.categories].sort((a, b) => b.count - a.count)
})

const showAllSelected = computed(() => {
  return props.selectedCategories.length === 0
})

const showDevSelected = computed(() => {
  return devCategories.every(c => props.selectedCategories.includes(c)) &&
         props.selectedCategories.length === devCategories.length
})

const showDocsSelected = computed(() => {
  return docCategories.every(c => props.selectedCategories.includes(c)) &&
         props.selectedCategories.length === docCategories.length
})

const getCategoryIcon = (categoryId: string): string => {
  return categoryIcons[categoryId] || categoryIcons.general
}

const isSelected = (categoryId: string): boolean => {
  return props.selectedCategories.includes(categoryId)
}

const toggleCategory = (categoryId: string) => {
  let newSelection: string[]

  if (props.multiSelect) {
    if (isSelected(categoryId)) {
      newSelection = props.selectedCategories.filter(c => c !== categoryId)
    } else {
      newSelection = [...props.selectedCategories, categoryId]
    }
  } else {
    newSelection = isSelected(categoryId) ? [] : [categoryId]
  }

  emit('update:selectedCategories', newSelection)
  emit('category-change', newSelection)
}

const clearSelection = () => {
  emit('update:selectedCategories', [])
  emit('category-change', [])
}

const selectAll = () => {
  emit('update:selectedCategories', [])
  emit('category-change', [])
}

const selectDeveloper = () => {
  const available = devCategories.filter(c =>
    props.categories.some(cat => cat.id === c)
  )
  emit('update:selectedCategories', available)
  emit('category-change', available)
}

const selectDocumentation = () => {
  const available = docCategories.filter(c =>
    props.categories.some(cat => cat.id === c)
  )
  emit('update:selectedCategories', available)
  emit('category-change', available)
}
</script>

<style scoped>
/* Issue #704: Migrated to design tokens */

.doc-category-filter {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--spacing-3);
}

.filter-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-3);
}

.filter-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wider);
  margin: 0;
}

.clear-btn {
  font-size: 0.6875rem;
  color: var(--color-info);
  background: none;
  border: none;
  cursor: pointer;
  padding: var(--spacing-0-5) var(--spacing-1-5);
  border-radius: var(--radius-default);
  transition: all var(--duration-150) var(--ease-in-out);
}

.clear-btn:hover {
  background: var(--color-info-bg);
}

.loading-state,
.error-state {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3);
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.error-state {
  color: var(--color-error);
}

.retry-btn {
  font-size: 0.6875rem;
  color: var(--color-info);
  background: none;
  border: none;
  cursor: pointer;
  text-decoration: underline;
}

.category-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
  max-height: 300px;
  overflow-y: auto;
}

.category-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  width: 100%;
  padding: var(--spacing-2) var(--spacing-2-5);
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-150) var(--ease-in-out);
  text-align: left;
}

.category-item:hover {
  border-color: var(--border-emphasis);
  background: var(--bg-hover);
}

.category-item.selected {
  border-color: var(--color-info);
  background: var(--color-info-bg);
}

/* Category-specific selected colors */
.category-item.selected.category-architecture {
  border-color: var(--chart-purple);
  background: var(--chart-purple-bg);
}

.category-item.selected.category-developer {
  border-color: var(--color-info);
  background: var(--color-info-bg);
}

.category-item.selected.category-api {
  border-color: var(--color-success);
  background: var(--color-success-bg);
}

.category-item.selected.category-troubleshooting {
  border-color: var(--color-warning);
  background: var(--color-warning-bg);
}

.category-item.selected.category-deployment {
  border-color: var(--color-error);
  background: var(--color-error-bg);
}

.category-item.selected.category-security {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.category-item.selected.category-features {
  border-color: var(--chart-orange);
  background: var(--chart-orange-bg);
}

.category-item.selected.category-testing {
  border-color: var(--chart-teal);
  background: var(--chart-green-bg);
}

.category-item.selected.category-workflow {
  border-color: var(--chart-purple);
  background: var(--chart-purple-bg);
}

.category-item.selected.category-guides {
  border-color: var(--chart-cyan);
  background: var(--chart-blue-bg);
}

.category-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.25rem;
  height: 1.25rem;
  font-size: 0.6875rem;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.category-item.selected .category-icon {
  color: inherit;
}

.category-name {
  flex: 1;
  font-size: 0.8125rem;
  font-weight: var(--font-medium);
  color: var(--text-secondary);
}

.category-count {
  font-size: 0.6875rem;
  font-weight: var(--font-semibold);
  color: var(--text-secondary);
  background: var(--bg-hover);
  padding: var(--spacing-0-5) var(--spacing-1-5);
  border-radius: var(--radius-full);
}

.category-item.selected .category-count {
  background: rgba(0, 0, 0, 0.1);
  color: inherit;
}

.quick-filters {
  display: flex;
  gap: var(--spacing-1-5);
  margin-top: var(--spacing-3);
  padding-top: var(--spacing-3);
  border-top: 1px solid var(--border-subtle);
}

.quick-filter-btn {
  flex: 1;
  padding: var(--spacing-1-5) var(--spacing-2);
  font-size: 0.6875rem;
  font-weight: var(--font-semibold);
  color: var(--text-tertiary);
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-default);
  cursor: pointer;
  transition: all var(--duration-150) var(--ease-in-out);
}

.quick-filter-btn:hover {
  background: var(--bg-hover);
  border-color: var(--border-emphasis);
}

.quick-filter-btn.active {
  background: var(--color-info);
  border-color: var(--color-info);
  color: var(--text-on-primary);
}

/* Scrollbar styling */
.category-list::-webkit-scrollbar {
  width: 4px;
}

.category-list::-webkit-scrollbar-track {
  background: var(--scrollbar-track);
  border-radius: var(--radius-xs);
}

.category-list::-webkit-scrollbar-thumb {
  background: var(--scrollbar-thumb);
  border-radius: var(--radius-xs);
}

.category-list::-webkit-scrollbar-thumb:hover {
  background: var(--scrollbar-thumb-hover);
}
</style>
