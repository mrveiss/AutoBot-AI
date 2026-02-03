<template>
  <div class="browser-header">
    <!-- Category Filter Tabs -->
    <div class="category-tabs">
      <BaseButton
        v-for="cat in categories"
        :key="cat.value ?? 'all'"
        :variant="selectedCategory === cat.value ? 'primary' : 'outline'"
        size="sm"
        @click="$emit('select-category', cat.value)"
        class="category-tab"
      >
        <i :class="cat.icon"></i>
        {{ cat.label }}
        <span v-if="cat.count > 0" class="category-count">{{ cat.count }}</span>
      </BaseButton>
    </div>

    <!-- Search bar -->
    <div class="search-bar">
      <i class="fas fa-search"></i>
      <input
        :value="searchQuery"
        type="text"
        placeholder="Search files and folders..."
        class="search-input"
        @input="$emit('search', ($event.target as HTMLInputElement).value)"
      />
      <BaseButton
        v-if="searchQuery"
        variant="ghost"
        size="xs"
        @click="$emit('clear-search')"
        class="clear-btn"
        aria-label="Clear search"
      >
        <i class="fas fa-times"></i>
      </BaseButton>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Knowledge Browser Header Component
 *
 * Header with category tabs and search functionality.
 * Extracted from KnowledgeBrowser.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import BaseButton from '@/components/base/BaseButton.vue'

interface CategoryOption {
  value: string | null
  label: string
  icon: string
  count: number
}

interface Props {
  categories: CategoryOption[]
  selectedCategory: string | null
  searchQuery: string
}

interface Emits {
  (e: 'select-category', category: string | null): void
  (e: 'search', query: string): void
  (e: 'clear-search'): void
}

defineProps<Props>()
defineEmits<Emits>()
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.browser-header {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-4);
  padding: var(--spacing-4) var(--spacing-6);
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
  align-items: center;
  justify-content: space-between;
}

.category-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
}

.category-tab {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  padding: var(--spacing-2) var(--spacing-3);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  transition: all var(--duration-200) var(--ease-in-out);
}

.category-tab i {
  font-size: var(--text-sm);
}

.category-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.25rem;
  height: 1.25rem;
  padding: 0 var(--spacing-1-5);
  background: var(--color-primary-bg-transparent);
  color: var(--color-primary);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  border-radius: var(--radius-full);
  margin-left: var(--spacing-1);
}

.search-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  min-width: 250px;
  max-width: 400px;
  flex: 1;
}

.search-bar i {
  color: var(--text-tertiary);
  font-size: var(--text-sm);
}

.search-input {
  flex: 1;
  border: none;
  outline: none;
  font-size: var(--text-sm);
  color: var(--text-primary);
  background: transparent;
}

.search-input::placeholder {
  color: var(--text-tertiary);
}

.clear-btn {
  padding: var(--spacing-1);
  color: var(--text-tertiary);
}

.clear-btn:hover {
  color: var(--text-secondary);
  background: var(--bg-secondary);
}

@media (max-width: 768px) {
  .browser-header {
    flex-direction: column;
    align-items: stretch;
  }

  .category-tabs {
    overflow-x: auto;
    padding-bottom: 0.5rem;
    margin-bottom: -0.5rem;
  }

  .search-bar {
    min-width: 100%;
    max-width: 100%;
  }
}
</style>
