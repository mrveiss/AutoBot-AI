<template>
  <div class="knowledge-health-analytics">
    <!-- Error Notification -->
    <div v-if="errorMessage" class="error-notification" role="alert" aria-live="assertive">
      <Icon name="exclamation-circle" />
      <span>{{ errorMessage }}</span>
      <button @click="clearError()" class="close-btn" :aria-label="$t('knowledge.stats.closeError')">
        <Icon name="times" />
      </button>
    </div>

    <!-- Vector Categories Distribution Chart -->
    <VectorStatsSection />

    <!-- Document Change Feed Section (PROMINENT) -->
    <div class="change-feed-section-wrapper">
      <div class="section-header prominent">
        <h3><Icon name="sync-alt" /> {{ $t('knowledge.stats.documentLifecycle') }}</h3>
        <span class="section-badge">{{ $t('knowledge.stats.realTimeTracking') }}</span>
      </div>
      <DocumentChangeFeed />
    </div>

    <!-- Compact Overview Row -->
    <StatsOverviewCards
      :document-count="store.documentCount"
      :category-count="store.categoryCount"
      :unique-tags-count="store.allTags.length"
      :avg-docs-per-category="avgDocsPerCategory"
      :avg-tags-per-doc="String(avgTagsPerDoc)"
      :total-storage-size="totalStorageSize"
      :avg-doc-size="avgDocSize"
    />

    <!-- Charts Section -->
    <StatsChartsSection
      :top-categories="topCategories"
      :max-category-count="maxCategoryCount"
      :documents-by-type="documentsByType"
      :total-documents="store.documentCount"
    />

    <!-- Recent Activity with Filter Chips -->
    <RecentActivityPanel :activities="recentActivities" />

    <!-- Tag Cloud -->
    <TagCloudPanel :tags="popularTags" />

    <!-- Actions -->
    <StatsActionsPanel
      @export="exportStats"
      @generate-report="generateReport"
    />
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import type { KnowledgeDocument } from '@/stores/useKnowledgeStore'
import { useKnowledgeController } from '@/models/controllers/index'
import DocumentChangeFeed from '@/components/knowledge/DocumentChangeFeed.vue'
import { formatFileSize } from '@/utils/formatHelpers'
import { createLogger } from '@/utils/debugUtils'
import { useTransientError } from '@/composables/useTransientError'
import {
  VectorStatsSection,
  StatsOverviewCards,
  StatsChartsSection,
  RecentActivityPanel,
  TagCloudPanel,
  StatsActionsPanel
} from '@/components/knowledge/stats'

// Import shared document feed wrapper styles
import '@/styles/document-feed-wrapper.css'

// Create scoped logger
const logger = createLogger('KnowledgeHealthAnalytics')
const { t } = useI18n()

// TypeScript Interfaces
interface Activity {
  id: string | number
  type: 'created' | 'updated'
  description: string
  timestamp: Date | string
}

interface KnowledgeController {
  refreshStats: () => Promise<void>
  getDetailedStats: () => Promise<Record<string, number | string | boolean | object>>
}

const store = useKnowledgeStore()

// Defensive controller initialization
let controller: KnowledgeController | null = null
try {
  controller = useKnowledgeController() as unknown as KnowledgeController
  logger.info('Knowledge controller initialized:', controller)
} catch (error) {
  logger.error('Failed to initialize knowledge controller:', error)
  controller = {
    refreshStats: async () => { logger.warn('Controller not available') },
    getDetailedStats: async () => ({})
  }
}

// State
const recentActivities = ref<Activity[]>([])
const { message: errorMessage, show: showErrorNotification, clear: clearError } = useTransientError()

// Computed statistics
const avgDocsPerCategory = computed(() => {
  if (store.categoryCount === 0) return 0
  return Math.round(store.documentCount / store.categoryCount)
})

const avgTagsPerDoc = computed(() => {
  if (store.documentCount === 0) return 0
  const totalTags = store.documents.reduce((sum, doc) => sum + doc.tags.length, 0)
  return (totalTags / store.documentCount).toFixed(1)
})

const totalStorageSize = computed(() => {
  return store.documents.reduce((sum, doc) => {
    return sum + (doc.metadata?.fileSize || estimateTextSize(doc.content))
  }, 0)
})

const avgDocSize = computed(() => {
  if (store.documentCount === 0) return 0
  return totalStorageSize.value / store.documentCount
})

const topCategories = computed(() => {
  return [...(store.categories || [])]
    .sort((a, b) => b.documentCount - a.documentCount)
    .slice(0, 5)
})

const maxCategoryCount = computed(() => {
  return Math.max(...(store.categories || []).map(c => c.documentCount), 1)
})

const documentsByType = computed(() => {
  const types: Record<string, number> = {}
  const documents = store.documents || []
  documents.forEach((doc: KnowledgeDocument) => {
    types[doc.type] = (types[doc.type] || 0) + 1
  })
  return types
})

const popularTags = computed(() => {
  const tagCounts: Record<string, number> = {}

  const documents = store.documents || []
  documents.forEach((doc: KnowledgeDocument) => {
    const tags = doc.tags || []
    tags.forEach((tag: string) => {
      tagCounts[tag] = (tagCounts[tag] || 0) + 1
    })
  })

  const maxCount = Math.max(...Object.values(tagCounts), 1)
  const minCount = Math.min(...Object.values(tagCounts), 1)

  return Object.entries(tagCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 30)
    .map(([name, count]) => ({
      name,
      count,
      size: 0.8 + ((count - minCount) / (maxCount - minCount)) * 1.2
    }))
})

const recentDocsCount = computed(() => {
  const oneWeekAgo = new Date()
  oneWeekAgo.setDate(oneWeekAgo.getDate() - 7)
  return store.documents.filter(doc =>
    new Date(doc.createdAt) > oneWeekAgo
  ).length
})

// Methods
const generateRecentActivities = () => {
  const activities: Activity[] = store.documents
    .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime())
    .slice(0, 10)
    .map(doc => {
      const actionType = new Date(doc.createdAt).getTime() === new Date(doc.updatedAt).getTime() ? 'created' : 'updated'
      return {
        id: doc.id,
        type: actionType as 'created' | 'updated',
        description: actionType === 'created'
          ? t('knowledge.health.activityCreated', { title: doc.title || 'Document' })
          : t('knowledge.health.activityUpdated', { title: doc.title || 'Document' }),
        timestamp: doc.updatedAt
      }
    })
  recentActivities.value = activities
}

const refreshStats = async () => {
  try {
    if (controller && typeof controller.refreshStats === 'function') {
      await controller.refreshStats()
    } else {
      logger.warn('Controller refreshStats method not available')
    }

    if (controller && typeof controller.getDetailedStats === 'function') {
      await controller.getDetailedStats()
    } else {
      logger.warn('Controller getDetailedStats method not available')
    }

    generateRecentActivities()
  } catch (error) {
    logger.error('Failed to refresh stats:', error)
    const errorMsg = error instanceof Error ? error.message : String(error)
    showErrorNotification(`Failed to load statistics: ${errorMsg}`)
  }
}

const exportStats = async () => {
  const stats = {
    overview: {
      totalDocuments: store.documentCount,
      totalCategories: store.categoryCount,
      uniqueTags: store.allTags.length,
      totalStorageSize: totalStorageSize.value,
      averageDocumentSize: avgDocSize.value,
      averageTagsPerDocument: avgTagsPerDoc.value,
      averageDocumentsPerCategory: avgDocsPerCategory.value
    },
    categories: store.categories.map(cat => ({
      name: cat.name,
      documentCount: cat.documentCount,
      percentage: ((cat.documentCount / store.documentCount) * 100).toFixed(1)
    })),
    documentTypes: documentsByType.value,
    popularTags: popularTags.value.map(tag => ({
      tag: tag.name,
      count: tag.count
    })),
    recentActivity: recentActivities.value,
    exportDate: new Date().toISOString()
  }

  const blob = new Blob([JSON.stringify(stats, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `knowledge-statistics-${new Date().toISOString().split('T')[0]}.json`
  a.click()
  URL.revokeObjectURL(url)
}

const generateReport = async () => {
  const report = `
# Knowledge Base Report
Generated: ${new Date().toLocaleString()}

## Overview
- Total Documents: ${store.documentCount}
- Categories: ${store.categoryCount}
- Unique Tags: ${store.allTags.length}
- Storage Used: ${formatFileSize(totalStorageSize.value)}

## Categories Breakdown
${store.categories.map(cat => `- ${cat.name}: ${cat.documentCount} documents`).join('\n')}

## Document Types
${Object.entries(documentsByType.value).map(([type, count]) => `- ${capitalize(type)}: ${count} (${getTypePercentage(count)}%)`).join('\n')}

## Growth Statistics
- Documents added this week: ${recentDocsCount.value}
- Average documents per category: ${avgDocsPerCategory.value}
- Average tags per document: ${avgTagsPerDoc.value}

## Popular Tags
${(popularTags.value || []).slice(0, 10).map(tag => `- ${tag.name}: ${tag.count} documents`).join('\n')}
  `.trim()

  const blob = new Blob([report], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `knowledge-report-${new Date().toISOString().split('T')[0]}.md`
  a.click()
  URL.revokeObjectURL(url)
}

// Utility functions
const estimateTextSize = (text: string): number => {
  return text.length
}

const getTypePercentage = (count: number): number => {
  if (store.documentCount === 0) return 0
  return Math.round((count / store.documentCount) * 100)
}

const capitalize = (str: string): string => {
  return str && str.length > 0 ? str.charAt(0).toUpperCase() + str.slice(1) : str || ''
}

// Load stats on mount (category fact counts are fetched by VectorStatsSection
// on its own useKnowledgeStats instance — the composable state is per-instance)
onMounted(async () => {
  await refreshStats()
})
</script>

<style scoped>
.knowledge-health-analytics {
  padding: var(--spacing-6);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-8);
}

/* Error Notification */
.error-notification {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-4) var(--spacing-6);
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  border-left: 4px solid var(--color-error);
  border-radius: var(--radius-lg);
  color: var(--color-danger-dark);
  animation: slideIn 0.3s ease-out;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.error-notification span {
  flex: 1;
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
}

.error-notification .close-btn {
  background: none;
  border: none;
  padding: var(--spacing-1);
  color: var(--color-danger-dark);
  cursor: pointer;
  opacity: 0.7;
  transition: opacity var(--duration-200);
  flex-shrink: 0;
}

.error-notification .close-btn:hover {
  opacity: 1;
}
</style>
