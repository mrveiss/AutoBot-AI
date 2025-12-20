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
.main-categories {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1rem;
  padding: 1.5rem;
  background: #f8fafc;
}

.main-category-card {
  display: flex;
  gap: 1rem;
  padding: 1.25rem;
  background: white;
  border-radius: 0.75rem;
  border: 2px solid transparent;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  cursor: pointer;
  transition: all 0.2s;
}

.main-category-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.category-icon {
  width: 3rem;
  height: 3rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 0.75rem;
  color: white;
  font-size: 1.25rem;
  flex-shrink: 0;
}

.category-info {
  flex: 1;
  min-width: 0;
}

.category-info h3 {
  font-size: 1rem;
  font-weight: 600;
  color: #1e293b;
  margin: 0 0 0.25rem 0;
}

.category-info p {
  font-size: 0.75rem;
  color: #64748b;
  margin: 0 0 0.75rem 0;
  line-height: 1.4;
}

.category-stats {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.fact-count {
  font-size: 0.75rem;
  font-weight: 500;
  color: #3b82f6;
  background: #eff6ff;
  padding: 0.25rem 0.5rem;
  border-radius: 0.375rem;
}

.populate-btn {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.75rem;
  font-size: 0.75rem;
}

.populate-btn i {
  font-size: 0.75rem;
}

@media (max-width: 640px) {
  .main-categories {
    grid-template-columns: 1fr;
    padding: 1rem;
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
