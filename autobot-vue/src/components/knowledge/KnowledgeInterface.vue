<template>
  <div class="knowledge-interface">
    <!-- Header -->
    <div class="knowledge-header">
      <h2 class="text-lg font-semibold text-gray-800 dark:text-gray-200">
        Knowledge Base Management
      </h2>
      <p class="text-sm text-gray-600 dark:text-gray-400">
        Manage and explore the AutoBot knowledge base with intelligent search and categorization
      </p>
    </div>

    <!-- Navigation Tabs -->
    <div class="knowledge-nav">
      <div class="nav-tabs">
        <button 
          v-for="tab in tabs" 
          :key="tab.id"
          @click="activeTab = tab.id"
          :class="tabButtonClass(tab.id)"
          class="tab-button"
        >
          <component :is="tab.icon" class="w-4 h-4" />
          <span>{{ tab.label }}</span>
        </button>
      </div>
    </div>

    <!-- Content Area -->
    <div class="knowledge-content">
      <!-- Overview Tab -->
      <div v-if="activeTab === 'overview'" class="tab-content">
        <KnowledgeStats />
      </div>

      <!-- Search Tab -->
      <div v-if="activeTab === 'search'" class="tab-content">
        <KnowledgeSearch />
      </div>

      <!-- Categories Tab -->
      <div v-if="activeTab === 'categories'" class="tab-content">
        <KnowledgeCategories />
      </div>

      <!-- Entries Tab -->
      <div v-if="activeTab === 'entries'" class="tab-content">
        <KnowledgeEntries />
      </div>

      <!-- Upload Tab -->
      <div v-if="activeTab === 'upload'" class="tab-content">
        <KnowledgeUpload />
      </div>

      <!-- Management Tab -->
      <div v-if="activeTab === 'management'" class="tab-content">
        <KnowledgeManager />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { 
  ChartBarIcon, 
  MagnifyingGlassIcon, 
  FolderIcon, 
  DocumentIcon, 
  CloudArrowUpIcon, 
  CogIcon 
} from '@heroicons/vue/24/outline'

// Import knowledge components
import KnowledgeStats from './KnowledgeStats.vue'
import KnowledgeSearch from './KnowledgeSearch.vue'
import KnowledgeCategories from './KnowledgeCategories.vue'
import KnowledgeEntries from './KnowledgeEntries.vue'
import KnowledgeUpload from './KnowledgeUpload.vue'
import KnowledgeManager from './KnowledgeManager.vue'

const activeTab = ref('overview')

const tabs = [
  {
    id: 'overview',
    label: 'Overview',
    icon: ChartBarIcon,
    description: 'Knowledge base statistics and overview'
  },
  {
    id: 'search',
    label: 'Search',
    icon: MagnifyingGlassIcon,
    description: 'Search through knowledge entries'
  },
  {
    id: 'categories',
    label: 'Categories',
    icon: FolderIcon,
    description: 'Browse knowledge by categories'
  },
  {
    id: 'entries',
    label: 'Entries',
    icon: DocumentIcon,
    description: 'View all knowledge entries'
  },
  {
    id: 'upload',
    label: 'Upload',
    icon: CloudArrowUpIcon,
    description: 'Upload new knowledge content'
  },
  {
    id: 'management',
    label: 'Manage',
    icon: CogIcon,
    description: 'Knowledge base management tools'
  }
]

const tabButtonClass = computed(() => (tabId) => {
  const baseClasses = 'flex items-center space-x-2 px-4 py-2 rounded-lg transition-colors font-medium'
  const activeClasses = 'bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-700'
  const inactiveClasses = 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-800 dark:hover:text-gray-200'
  
  return `${baseClasses} ${activeTab.value === tabId ? activeClasses : inactiveClasses}`
})
</script>

<style scoped>
.knowledge-interface {
  @apply flex flex-col h-full bg-gray-50 dark:bg-gray-900;
}

.knowledge-header {
  @apply px-6 py-4 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700;
}

.knowledge-nav {
  @apply px-6 py-4 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700;
}

.nav-tabs {
  @apply flex flex-wrap gap-2;
}

.tab-button {
  @apply text-sm border;
}

.knowledge-content {
  @apply flex-1 overflow-auto;
}

.tab-content {
  @apply h-full;
}

/* Responsive design */
@media (max-width: 768px) {
  .nav-tabs {
    @apply grid grid-cols-2 gap-2;
  }
  
  .tab-button {
    @apply text-xs px-2 py-1;
  }
  
  .tab-button span {
    @apply hidden sm:inline;
  }
}

/* Dark mode enhancements */
.dark .knowledge-interface {
  @apply bg-gray-900;
}

.dark .knowledge-header,
.dark .knowledge-nav {
  @apply bg-gray-800 border-gray-700;
}
</style>