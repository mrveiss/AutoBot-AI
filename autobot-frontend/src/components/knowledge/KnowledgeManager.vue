<template>
  <ErrorBoundary :fallback="$t('knowledge.manager.errorFallback')">
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
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import ErrorBoundary from '@/components/common/ErrorBoundary.vue'

// Import sub-components
import KnowledgeBrowser from './KnowledgeBrowser.vue'
import KnowledgeCategories from './KnowledgeCategories.vue'

// Lazy load heavier components using direct dynamic imports for Vue Router compatibility
const KnowledgeEntries = () => import('./KnowledgeEntries.vue')
const KnowledgeUpload = () => import('./KnowledgeUpload.vue')
const KnowledgeHealth = () => import('./KnowledgeHealth.vue')
const KnowledgeAdvanced = () => import('./KnowledgeAdvanced.vue')
// Issue #3270: wire up existing but previously unreachable components
const KnowledgeSystemDocs = () => import('./KnowledgeSystemDocs.vue')
const KnowledgePromptEditor = () => import('./KnowledgePromptEditor.vue')

const store = useKnowledgeStore()

type TabId = 'entries' | 'search' | 'upload' | 'manage' | 'categories' | 'stats' | 'system-docs' | 'prompt-editor' | 'advanced'

// Tab configuration
const tabs = computed<{ id: TabId; label: string }[]>(() => [
  { id: 'search', label: t('knowledge.manager.tabSearch') },
  { id: 'categories', label: t('knowledge.manager.tabCategories') },
  { id: 'upload', label: t('knowledge.manager.tabUpload') },
  { id: 'manage', label: t('knowledge.manager.tabManage') },
  { id: 'stats', label: t('knowledge.manager.tabStatistics') },
  { id: 'system-docs', label: t('knowledge.manager.tabSystemDocs') },
  { id: 'prompt-editor', label: t('knowledge.manager.tabPromptEditor') },
  { id: 'advanced', label: t('knowledge.manager.tabAdvanced') }
])

// Component mapping
const componentMap = {
  search: KnowledgeBrowser,
  categories: KnowledgeCategories,
  upload: KnowledgeUpload,
  manage: KnowledgeEntries,
  stats: KnowledgeHealth,
  'system-docs': KnowledgeSystemDocs,
  'prompt-editor': KnowledgePromptEditor,
  advanced: KnowledgeAdvanced
} as const

// Active component based on tab
const activeComponent = computed(() => {
  return componentMap[store.activeTab as keyof typeof componentMap] || KnowledgeBrowser
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
