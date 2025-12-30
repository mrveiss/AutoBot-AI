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
.doc-category-filter {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 0.5rem;
  padding: 0.75rem;
}

.filter-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
}

.filter-title {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.75rem;
  font-weight: 600;
  color: #475569;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0;
}

.clear-btn {
  font-size: 0.6875rem;
  color: #3b82f6;
  background: none;
  border: none;
  cursor: pointer;
  padding: 0.125rem 0.375rem;
  border-radius: 0.25rem;
  transition: all 0.15s ease;
}

.clear-btn:hover {
  background: #dbeafe;
}

.loading-state,
.error-state {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  font-size: 0.75rem;
  color: #64748b;
}

.error-state {
  color: #dc2626;
}

.retry-btn {
  font-size: 0.6875rem;
  color: #3b82f6;
  background: none;
  border: none;
  cursor: pointer;
  text-decoration: underline;
}

.category-list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  max-height: 300px;
  overflow-y: auto;
}

.category-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.5rem 0.625rem;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 0.375rem;
  cursor: pointer;
  transition: all 0.15s ease;
  text-align: left;
}

.category-item:hover {
  border-color: #cbd5e1;
  background: #f1f5f9;
}

.category-item.selected {
  border-color: #3b82f6;
  background: #eff6ff;
}

/* Category-specific selected colors */
.category-item.selected.category-architecture { border-color: #8b5cf6; background: #f5f3ff; }
.category-item.selected.category-developer { border-color: #3b82f6; background: #eff6ff; }
.category-item.selected.category-api { border-color: #10b981; background: #ecfdf5; }
.category-item.selected.category-troubleshooting { border-color: #f59e0b; background: #fffbeb; }
.category-item.selected.category-deployment { border-color: #ef4444; background: #fef2f2; }
.category-item.selected.category-security { border-color: #6366f1; background: #eef2ff; }
.category-item.selected.category-features { border-color: #f97316; background: #fff7ed; }
.category-item.selected.category-testing { border-color: #14b8a6; background: #f0fdfa; }
.category-item.selected.category-workflow { border-color: #8b5cf6; background: #f5f3ff; }
.category-item.selected.category-guides { border-color: #0ea5e9; background: #f0f9ff; }

.category-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.25rem;
  height: 1.25rem;
  font-size: 0.6875rem;
  color: #64748b;
  flex-shrink: 0;
}

.category-item.selected .category-icon {
  color: inherit;
}

.category-name {
  flex: 1;
  font-size: 0.8125rem;
  font-weight: 500;
  color: #334155;
}

.category-count {
  font-size: 0.6875rem;
  font-weight: 600;
  color: #94a3b8;
  background: #f1f5f9;
  padding: 0.125rem 0.375rem;
  border-radius: 9999px;
}

.category-item.selected .category-count {
  background: rgba(0, 0, 0, 0.1);
  color: inherit;
}

.quick-filters {
  display: flex;
  gap: 0.375rem;
  margin-top: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px solid #e2e8f0;
}

.quick-filter-btn {
  flex: 1;
  padding: 0.375rem 0.5rem;
  font-size: 0.6875rem;
  font-weight: 600;
  color: #64748b;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 0.25rem;
  cursor: pointer;
  transition: all 0.15s ease;
}

.quick-filter-btn:hover {
  background: #f1f5f9;
  border-color: #cbd5e1;
}

.quick-filter-btn.active {
  background: #3b82f6;
  border-color: #3b82f6;
  color: #ffffff;
}

/* Scrollbar styling */
.category-list::-webkit-scrollbar {
  width: 4px;
}

.category-list::-webkit-scrollbar-track {
  background: #f1f5f9;
  border-radius: 2px;
}

.category-list::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 2px;
}

.category-list::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}
</style>
