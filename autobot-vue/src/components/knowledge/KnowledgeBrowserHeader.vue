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
.browser-header {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  padding: 1rem 1.5rem;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
  align-items: center;
  justify-content: space-between;
}

.category-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.category-tab {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 0.75rem;
  border-radius: 0.5rem;
  font-size: 0.875rem;
  font-weight: 500;
  transition: all 0.2s;
}

.category-tab i {
  font-size: 0.875rem;
}

.category-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.25rem;
  height: 1.25rem;
  padding: 0 0.375rem;
  background: rgba(59, 130, 246, 0.1);
  color: #3b82f6;
  font-size: 0.75rem;
  font-weight: 600;
  border-radius: 0.625rem;
  margin-left: 0.25rem;
}

.search-bar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 0.5rem;
  min-width: 250px;
  max-width: 400px;
  flex: 1;
}

.search-bar i {
  color: #94a3b8;
  font-size: 0.875rem;
}

.search-input {
  flex: 1;
  border: none;
  outline: none;
  font-size: 0.875rem;
  color: #1e293b;
  background: transparent;
}

.search-input::placeholder {
  color: #94a3b8;
}

.clear-btn {
  padding: 0.25rem;
  color: #94a3b8;
}

.clear-btn:hover {
  color: #64748b;
  background: #f1f5f9;
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
