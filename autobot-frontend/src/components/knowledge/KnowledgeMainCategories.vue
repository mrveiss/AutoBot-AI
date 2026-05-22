<template>
  <div class="main-categories-wrapper">
    <!-- Issue #5590: fetch-layer error (5xx / network) — generic message, no Redis blame -->
    <div
      v-if="kbFetchError"
      class="kb-status-panel kb-status-panel--error"
      role="alert"
    >
      <Icon name="exclamation-triangle" class="kb-status-panel__icon" />
      <div class="kb-status-panel__body">
        <h3 class="kb-status-panel__title">
          {{ $t('knowledge.categoriesFetchError.title') }}
        </h3>
        <p class="kb-status-panel__text">
          {{ $t('knowledge.categoriesFetchError.description') }}
        </p>
      </div>
    </div>

    <!-- Issue #5201: broken-KB alert — only when backend explicitly reports Redis down -->
    <div
      v-else-if="!kbConnected"
      class="kb-status-panel kb-status-panel--error"
      role="alert"
    >
      <Icon name="exclamation-triangle" class="kb-status-panel__icon" />
      <div class="kb-status-panel__body">
        <h3 class="kb-status-panel__title">
          {{ $t('knowledge.categoriesError.title') }}
        </h3>
        <p class="kb-status-panel__text">
          {{ $t('knowledge.categoriesError.description') }}
        </p>
      </div>
    </div>

    <!-- Issue #5201: empty-KB hint — only when categories have loaded and every count is 0 -->
    <div
      v-else-if="showEmptyStateHint"
      class="kb-status-panel kb-status-panel--info"
      role="status"
    >
      <Icon name="info-circle" class="kb-status-panel__icon" />
      <div class="kb-status-panel__body">
        <h3 class="kb-status-panel__title">
          {{ $t('knowledge.emptyState.title') }}
        </h3>
        <p class="kb-status-panel__text">
          {{ $t('knowledge.emptyState.description') }}
        </p>
        <p class="kb-status-panel__text">
          {{ $t('knowledge.emptyState.hint') }}
        </p>
      </div>
    </div>

    <div class="main-categories">
      <div
        v-for="mainCat in categories"
        :key="mainCat.id"
        class="main-category-card"
        :style="{ borderColor: mainCat.color }"
        @click="$emit('select', mainCat.id)"
      >
        <div class="category-icon" :style="{ backgroundColor: mainCat.color }">
          <Icon :name="mainCat.icon" />
        </div>
        <div class="category-info">
          <h3>{{ mainCat.name }}</h3>
          <p>{{ mainCat.description }}</p>
          <div class="category-stats">
            <span class="fact-count">{{ mainCat.count }} {{ $t('knowledge.browser.facts') }}</span>
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
              <Icon name="sync" v-if="!populationStates[mainCat.id]?.isPopulating" />
              <span v-if="!populationStates[mainCat.id]?.isPopulating">{{ $t('knowledge.browser.populate') }}</span>
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
              <Icon name="file-import" />
              <span>{{ $t('knowledge.browser.import') }}</span>
            </BaseButton>
          </div>
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
 * Issue #5201: Distinguish empty-KB from broken-KB with clear CTA panels
 */

import Icon from '@/components/ui/Icon.vue'
import { computed } from 'vue'
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
  // Issue #5201: reflects backend Redis/KB reachability. Defaults to true
  // to preserve behavior with older backends that don't send the flag.
  kbConnected?: boolean
  // Issue #5590: true when the fetch itself failed (5xx / network error),
  // distinct from kbConnected=false which the backend sets for Redis outages.
  kbFetchError?: boolean
}

interface Emits {
  (e: 'select', categoryId: string): void
  (e: 'populate', categoryId: string): void
  (e: 'import'): void
}

const props = withDefaults(defineProps<Props>(), {
  kbConnected: true,
  kbFetchError: false,
})
defineEmits<Emits>()

// Show the empty-state hint only once categories have loaded AND every
// visible card has a zero count. Rendering it before categories load
// would flash a "you're empty" message during normal startup.
const showEmptyStateHint = computed(
  () =>
    props.kbConnected &&
    props.categories.length > 0 &&
    props.categories.every((c) => (c.count ?? 0) === 0),
)
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.main-categories-wrapper {
  display: flex;
  flex-direction: column;
}

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
  font-size: var(--text-xl);
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

/* Issue #5201: status panels for empty-KB / broken-KB states */
.kb-status-panel {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-3);
  margin: var(--spacing-4) var(--spacing-6) var(--spacing-0);
  padding: var(--spacing-4) var(--spacing-5);
  border-radius: var(--radius-lg);
  border: 1px solid transparent;
}

.kb-status-panel__icon {
  font-size: var(--text-xl);
  margin-top: var(--spacing-0-5);
  flex-shrink: 0;
}

.kb-status-panel__body {
  flex: 1;
  min-width: 0;
}

.kb-status-panel__title {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  margin: 0 0 var(--spacing-1) 0;
}

.kb-status-panel__text {
  font-size: var(--text-xs);
  line-height: var(--leading-normal);
  margin: 0 0 var(--spacing-1) 0;
}

.kb-status-panel__text:last-child {
  margin-bottom: var(--spacing-0);
}

.kb-status-panel--info {
  background: var(--color-primary-bg);
  border-color: var(--color-primary-light);
  color: var(--color-primary-dark);
}

.kb-status-panel--info .kb-status-panel__icon {
  color: var(--color-primary);
}

.kb-status-panel--error {
  background: var(--color-error-alpha-10);
  border-color: var(--color-error);
  color: var(--color-error);
}

.kb-status-panel--error .kb-status-panel__icon {
  color: var(--color-error);
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

  .kb-status-panel {
    margin: var(--spacing-3) var(--spacing-4) var(--spacing-0);
    padding: var(--spacing-3);
  }
}
</style>
