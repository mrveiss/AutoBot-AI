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
import ErrorBoundary from '@/components/ErrorBoundary.vue'

// Import sub-components
import KnowledgeSearch from './KnowledgeSearch.vue'
import KnowledgeCategories from './KnowledgeCategories.vue'

// Lazy load heavier components using direct dynamic imports for Vue Router compatibility
const KnowledgeEntries = () => import('./KnowledgeEntries.vue')
const KnowledgeUpload = () => import('./KnowledgeUpload.vue')
const KnowledgeStats = () => import('./KnowledgeStats.vue')

const store = useKnowledgeStore()

// Tab configuration
const tabs = [
  { id: 'search', label: 'Search' },
  { id: 'categories', label: 'Categories' },
  { id: 'upload', label: 'Upload' },
  { id: 'manage', label: 'Manage' },
  { id: 'stats', label: 'Statistics' }
] as const

// Component mapping
const componentMap = {
  search: KnowledgeSearch,
  categories: KnowledgeCategories,
  upload: KnowledgeUpload,
  manage: KnowledgeEntries,
  stats: KnowledgeStats
} as const

// Active component based on tab
const activeComponent = computed(() => {
  return componentMap[store.activeTab as keyof typeof componentMap] || KnowledgeSearch
})
</script>

<style scoped>
.knowledge-manager {
  background: #f9fafb;
  border-radius: 0.5rem;
  overflow: hidden;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.tabs {
  display: flex;
  background: white;
  border-bottom: 2px solid #e5e7eb;
  overflow-x: auto;
}

.tab-button {
  padding: 1rem 1.5rem;
  border: none;
  background: none;
  color: #6b7280;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s;
  position: relative;
}

.tab-button:hover {
  color: #374151;
  background: #f3f4f6;
}

.tab-button.active {
  color: #3b82f6;
}

.tab-button.active::after {
  content: '';
  position: absolute;
  bottom: -2px;
  left: 0;
  right: 0;
  height: 2px;
  background: #3b82f6;
}

.tab-content {
  flex: 1;
  overflow-y: auto;
  background: white;
}

/* Responsive */
@media (max-width: 768px) {
  .tabs {
    -webkit-overflow-scrolling: touch;
  }

  .tab-button {
    padding: 0.75rem 1rem;
    font-size: 0.875rem;
  }
}
</style>
