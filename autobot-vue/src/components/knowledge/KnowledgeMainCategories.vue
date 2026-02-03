<template>
  <div class="main-categories">
    <div
      v-for="mainCat in categories"
      :key="mainCat.id"
      class="main-category-card"
      :style="{ borderColor: mainCat.color }"
      @click="$emit('select', mainCat.id)"
    >
      <div class="category-icon" :style="{ backgroundColor: mainCat.color }">
        <i :class="mainCat.icon"></i>
      </div>
      <div class="category-info">
        <h3>{{ mainCat.name }}</h3>
        <p>{{ mainCat.description }}</p>
        <div class="category-stats">
          <span class="fact-count">{{ mainCat.count }} facts</span>
          <!-- Populate button for system categories -->
          <BaseButton
            v-if="mainCat.id !== 'user-knowledge'"
            variant="primary"
            size="sm"
            :loading="populationStates[mainCat.id]?.isPopulating"
            :disabled="populationStates[mainCat.id]?.isPopulating"
            @click.stop="$emit('populate', mainCat.id)"
            class="populate-btn"
          >
            <i v-if="!populationStates[mainCat.id]?.isPopulating" class="fas fa-sync"></i>
            <span v-if="!populationStates[mainCat.id]?.isPopulating">Populate</span>
            <span v-else>{{ populationStates[mainCat.id]?.progress || 0 }}%</span>
          </BaseButton>
          <!-- Import button for user knowledge -->
          <BaseButton
            v-if="mainCat.id === 'user-knowledge'"
            variant="primary"
            size="sm"
            @click.stop="$emit('import')"
            class="populate-btn"
          >
            <i class="fas fa-file-import"></i>
            <span>Import</span>
          </BaseButton>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Knowledge Main Categories Component
 *
 * Displays the main category cards for knowledge navigation.
 * Extracted from KnowledgeBrowser.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import BaseButton from '@/components/base/BaseButton.vue'

interface MainCategory {
  id: string
  name: string
  description: string
  icon: string
  color: string
  count: number
}

interface PopulationState {
  isPopulating: boolean
  progress: number
}

interface Props {
  categories: MainCategory[]
  populationStates: Record<string, PopulationState>
}

interface Emits {
  (e: 'select', categoryId: string): void
  (e: 'populate', categoryId: string): void
  (e: 'import'): void
}

defineProps<Props>()
defineEmits<Emits>()
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.main-categories {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--spacing-4);
  padding: var(--spacing-6);
  background: var(--bg-secondary);
}

.main-category-card {
  display: flex;
  gap: var(--spacing-4);
  padding: var(--spacing-5);
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
  border: 2px solid transparent;
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  transition: all var(--duration-200) var(--ease-in-out);
}

.main-category-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-lg);
}

.category-icon {
  width: 3rem;
  height: 3rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-lg);
  color: var(--text-on-primary);
  font-size: 1.25rem;
  flex-shrink: 0;
}

.category-info {
  flex: 1;
  min-width: 0;
}

.category-info h3 {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0 0 var(--spacing-1) 0;
}

.category-info p {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin: 0 0 var(--spacing-3) 0;
  line-height: var(--leading-normal);
}

.category-stats {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-3);
}

.fact-count {
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  color: var(--color-primary);
  background: var(--color-primary-bg);
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-md);
}

.populate-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  padding: var(--spacing-1-5) var(--spacing-3);
  font-size: var(--text-xs);
}

.populate-btn i {
  font-size: var(--text-xs);
}

@media (max-width: 640px) {
  .main-categories {
    grid-template-columns: 1fr;
    padding: var(--spacing-4);
  }

  .main-category-card {
    flex-direction: column;
    align-items: flex-start;
  }

  .category-stats {
    width: 100%;
  }
}
</style>
