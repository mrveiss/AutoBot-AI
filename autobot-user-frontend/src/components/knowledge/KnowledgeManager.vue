<template>
  <ErrorBoundary fallback="Knowledge Base failed to load. Please try refreshing.">
    <div class="knowledge-manager">
      <div class="tabs">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          :class="['tab-button', { active: store.activeTab === tab.id }]"
          @click="store.setActiveTab(tab.id)"
          :aria-label="tab.label"
        >
          {{ tab.label }}
        </button>
      </div>

      <div class="tab-content">
        <component :is="activeComponent" />
      </div>
    </div>
  </ErrorBoundary>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import ErrorBoundary from '@/components/common/ErrorBoundary.vue'

// Import sub-components
import KnowledgeSearch from './KnowledgeSearch.vue'
import KnowledgeCategories from './KnowledgeCategories.vue'

// Lazy load heavier components using direct dynamic imports for Vue Router compatibility
const KnowledgeEntries = () => import('./KnowledgeEntries.vue')
const KnowledgeUpload = () => import('./KnowledgeUpload.vue')
const KnowledgeStats = () => import('./KnowledgeStats.vue')
const KnowledgeAdvanced = () => import('./KnowledgeAdvanced.vue')

const store = useKnowledgeStore()

// Tab configuration - Added Advanced tab
const tabs = [
  { id: 'search', label: 'Search' },
  { id: 'categories', label: 'Categories' },
  { id: 'upload', label: 'Upload' },
  { id: 'manage', label: 'Manage' },
  { id: 'stats', label: 'Statistics' },
  { id: 'advanced', label: 'Advanced' }
] as const

// Component mapping - Added KnowledgeAdvanced
const componentMap = {
  search: KnowledgeSearch,
  categories: KnowledgeCategories,
  upload: KnowledgeUpload,
  manage: KnowledgeEntries,
  stats: KnowledgeStats,
  advanced: KnowledgeAdvanced
} as const

// Active component based on tab
const activeComponent = computed(() => {
  return componentMap[store.activeTab as keyof typeof componentMap] || KnowledgeSearch
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.knowledge-manager {
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  overflow: hidden;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.tabs {
  display: flex;
  background: var(--bg-primary);
  border-bottom: 2px solid var(--border-default);
  overflow-x: auto;
}

.tab-button {
  padding: var(--spacing-4) var(--spacing-6);
  border: none;
  background: none;
  color: var(--text-secondary);
  font-weight: var(--font-medium);
  cursor: pointer;
  white-space: nowrap;
  transition: all var(--duration-200) var(--ease-in-out);
  position: relative;
}

.tab-button:hover {
  color: var(--text-primary);
  background: var(--bg-secondary);
}

.tab-button.active {
  color: var(--color-primary);
}

.tab-button.active::after {
  content: '';
  position: absolute;
  bottom: -2px;
  left: 0;
  right: 0;
  height: 2px;
  background: var(--color-primary);
}

.tab-content {
  flex: 1;
  overflow-y: auto;
  background: var(--bg-primary);
}

/* Responsive */
@media (max-width: 768px) {
  .tabs {
    -webkit-overflow-scrolling: touch;
  }

  .tab-button {
    padding: var(--spacing-3) var(--spacing-4);
    font-size: var(--text-sm);
  }
}
</style>
