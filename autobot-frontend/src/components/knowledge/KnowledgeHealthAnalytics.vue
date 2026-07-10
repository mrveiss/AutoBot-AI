<template>
  <div class="knowledge-health-analytics">
    <!-- Error Notification -->
    <div v-if="errorMessage" class="error-notification" role="alert" aria-live="assertive">
      <Icon name="exclamation-circle" />
      <span>{{ errorMessage }}</span>
      <button @click="errorMessage = ''" class="close-btn" :aria-label="$t('knowledge.stats.closeError')">
        <Icon name="times" />
      </button>
    </div>

    <!-- Vector Categories Distribution Chart -->
    <div v-if="vectorStats" class="vector-chart-section">
      <h4><Icon name="chart-pie" /> {{ $t('knowledge.stats.vectorDistribution') }}</h4>
      <div class="vector-categories-chart">
        <div
          v-for="(category, idx) in vectorStats.categories"
          :key="idx"
          class="category-bar"
        >
          <div class="category-info">
            <span class="category-name">{{ formatCategoryName(category) }}</span>
            <span class="category-count">{{ $t('knowledge.stats.factsCount', { count: getCategoryFactCount(category) }) }}</span>
          </div>
          <div class="category-progress">
            <div
              class="category-fill"
              :style="{
                width: getCategoryPercentage(category) + '%',
                backgroundColor: getCategoryColor(idx)
              }"
            ></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Document Change Feed Section (PROMINENT) -->
    <div class="change-feed-section-wrapper">
      <div class="section-header prominent">
        <h3><Icon name="sync-alt" /> {{ $t('knowledge.stats.documentLifecycle') }}</h3>
        <span class="section-badge">{{ $t('knowledge.stats.realTimeTracking') }}</span>
      </div>
      <DocumentChangeFeed />
    </div>

    <!-- Compact Overview Row -->
    <div class="stats-overview" role="region" :aria-label="$t('knowledge.stats.overviewAriaLabel')">
      <BasePanel variant="elevated" size="sm" role="article" aria-labelledby="analytics-documents-title">
        <div class="stat-icon documents" aria-hidden="true">
          <Icon name="file-alt" />
        </div>
        <div class="stat-content">
          <h4 id="analytics-documents-title">{{ $t('knowledge.stats.totalDocuments') }}</h4>
          <p class="stat-value" aria-live="polite">{{ store.documentCount }}</p>
          <p class="stat-change">
            {{ $t('knowledge.stats.avgDocsPerCategoryValue', { count: avgDocsPerCategory }) }}
          </p>
        </div>
      </BasePanel>

      <BasePanel variant="elevated" size="sm" role="article" aria-labelledby="analytics-categories-title">
        <div class="stat-icon categories" aria-hidden="true">
          <Icon name="folder" />
        </div>
        <div class="stat-content">
          <h4 id="analytics-categories-title">{{ $t('knowledge.stats.categories') }}</h4>
          <p class="stat-value" aria-live="polite">{{ store.categoryCount }}</p>
          <p class="stat-change">
            {{ $t('knowledge.stats.avgDocsPerCategoryValue', { count: avgDocsPerCategory }) }}
          </p>
        </div>
      </BasePanel>

      <BasePanel variant="elevated" size="sm">
        <div class="stat-icon tags">
          <Icon name="tags" />
        </div>
        <div class="stat-content">
          <h4>{{ $t('knowledge.stats.uniqueTags') }}</h4>
          <p class="stat-value">{{ store.allTags.length }}</p>
          <p class="stat-change">
            {{ $t('knowledge.stats.avgTagsPerDoc', { count: avgTagsPerDoc }) }}
          </p>
        </div>
      </BasePanel>

      <BasePanel variant="elevated" size="sm">
        <div class="stat-icon storage">
          <Icon name="database" />
        </div>
        <div class="stat-content">
          <h4>{{ $t('knowledge.stats.storageUsedTitle') }}</h4>
          <p class="stat-value">{{ formatFileSize(totalStorageSize) }}</p>
          <p class="stat-change">
            {{ $t('knowledge.stats.avgPerDoc', { size: formatFileSize(avgDocSize) }) }}
          </p>
        </div>
      </BasePanel>
    </div>

    <!-- Charts Section -->
    <div class="charts-section">
      <!-- Documents by Category -->
      <BasePanel variant="bordered" size="md">
        <h4>{{ $t('knowledge.stats.docsByCategory') }}</h4>
        <div class="bar-chart">
          <div
            v-for="category in topCategories"
            :key="category.name"
            class="bar-item"
          >
            <div class="bar-label">{{ category.name }}</div>
            <div class="bar-wrapper">
              <div
                class="bar-fill"
                :style="{
                  width: `${(category.documentCount / maxCategoryCount) * 100}%`,
                  backgroundColor: category.color || 'var(--color-info)'
                }"
              ></div>
              <span class="bar-value">{{ category.documentCount }}</span>
            </div>
          </div>
        </div>
      </BasePanel>

      <!-- Documents by Type -->
      <BasePanel variant="bordered" size="md">
        <h4>{{ $t('knowledge.stats.docsByType') }}</h4>
        <div class="pie-chart">
          <div class="type-stats">
            <div v-for="(count, type) in documentsByType" :key="type" class="type-item">
              <div class="type-color" :style="{ backgroundColor: getTypeColor(type) }"></div>
              <span class="type-name">{{ capitalize(type) }}</span>
              <span class="type-count">{{ count }}</span>
              <span class="type-percentage">({{ getTypePercentage(count) }}%)</span>
            </div>
          </div>
        </div>
      </BasePanel>
    </div>

    <!-- Recent Activity with Filter Chips -->
    <BasePanel variant="bordered" size="md">
      <div class="activity-header">
        <h4>{{ $t('knowledge.stats.recentActivity') }}</h4>
        <div class="feed-filter-chips" role="group" :aria-label="$t('knowledge.stats.recentActivity')">
          <button
            v-for="chip in feedChips"
            :key="chip.value"
            class="feed-chip"
            :class="{ active: activeFeedFilter === chip.value }"
            @click="activeFeedFilter = chip.value"
          >
            {{ $t(chip.labelKey) }}
          </button>
        </div>
      </div>
      <div class="activity-timeline">
        <div v-for="activity in filteredActivities" :key="activity.id" class="activity-item">
          <div class="activity-icon" :class="activity.type">
            <Icon :name="getActivityIcon(activity.type)" />
          </div>
          <div class="activity-content">
            <p class="activity-description">{{ activity.description }}</p>
            <p class="activity-time">{{ formatTimeAgo(activity.timestamp) }}</p>
          </div>
        </div>
        <EmptyState
          v-if="filteredActivities.length === 0"
          icon="clock"
          :message="$t('knowledge.stats.noRecentActivity')"
        />
      </div>
    </BasePanel>

    <!-- Tag Cloud -->
    <BasePanel variant="bordered" size="md">
      <h4>{{ $t('knowledge.stats.popularTags') }}</h4>
      <div class="tag-cloud" role="list" :aria-label="$t('knowledge.stats.popularTagsAriaLabel')">
        <span
          v-for="tag in popularTags"
          :key="tag.name"
          class="tag-cloud-item"
          :style="{ fontSize: `${tag.size}rem` }"
          :title="`${tag.count} documents`"
          :aria-label="`${tag.name}: ${tag.count} documents`"
          role="listitem"
          tabindex="0"
          @click="() => {}"
          @keypress.enter="() => {}"
        >
          {{ tag.name }}
        </span>
      </div>
    </BasePanel>

    <!-- Actions -->
    <div class="stats-actions">
      <button @click="exportStats" class="action-btn">
        <Icon name="download" />
        {{ $t('knowledge.stats.exportStats') }}
      </button>
      <button @click="generateReport" class="action-btn primary">
        <Icon name="file-chart-line" />
        {{ $t('knowledge.stats.generateReport') }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { IconName } from '@/components/ui/Icon.vue'
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, onMounted } from 'vue'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import type { KnowledgeDocument } from '@/stores/useKnowledgeStore'
import { useKnowledgeStats } from '@/composables/knowledge/useKnowledgeStats'
import { useKnowledgeController } from '@/models/controllers/index'
import DocumentChangeFeed from '@/components/knowledge/DocumentChangeFeed.vue'
import {
  formatFileSize,
  formatTimeAgo,
  formatCategoryName
} from '@/utils/formatHelpers'
import EmptyState from '@/components/ui/EmptyState.vue'
import BasePanel from '@/components/base/BasePanel.vue'
import { createLogger } from '@/utils/debugUtils'

// Import shared document feed wrapper styles
import '@/styles/document-feed-wrapper.css'

// Create scoped logger
const logger = createLogger('KnowledgeHealthAnalytics')

// TypeScript Interfaces
interface VectorStats {
  total_facts: number
  total_documents: number
  total_vectors: number
  indexed_documents: number
  db_size: number
  status: 'online' | 'offline' | 'unknown'
  rag_available: boolean
  initialized: boolean
  llama_index_configured: boolean
  index_available: boolean
  redis_db: string | number
  index_name: string
  embedding_model?: string
  embedding_dimensions?: number
  last_updated?: string
  categories?: string[]
}

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

// Composable: category facts fetching
const { categoryFactCounts, refreshCategoryFacts } = useKnowledgeStats()

// State
const recentActivities = ref<Activity[]>([])
const vectorStats = ref<VectorStats | null>(null)
const errorMessage = ref<string>('')

// Feed filter: 'all' | 'created' | 'updated'
type FeedFilter = 'all' | 'created' | 'updated'
const activeFeedFilter = ref<FeedFilter>('all')

const feedChips: { value: FeedFilter; labelKey: string }[] = [
  { value: 'all', labelKey: 'knowledge.health.feedAll' },
  { value: 'created', labelKey: 'knowledge.health.feedCreated' },
  { value: 'updated', labelKey: 'knowledge.health.feedUpdated' }
]

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

const filteredActivities = computed(() => {
  if (activeFeedFilter.value === 'all') return recentActivities.value
  return recentActivities.value.filter(a => a.type === activeFeedFilter.value)
})

// Methods
const generateRecentActivities = () => {
  const activities: Activity[] = store.documents
    .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime())
    .slice(0, 10)
    .map(doc => ({
      id: doc.id,
      type: (new Date(doc.createdAt).getTime() === new Date(doc.updatedAt).getTime() ? 'created' : 'updated') as 'created' | 'updated',
      description: `${doc.title || 'Document'} was ${
        new Date(doc.createdAt).getTime() === new Date(doc.updatedAt).getTime() ? 'created' : 'updated'
      }`,
      timestamp: doc.updatedAt
    }))
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

    // Populate vectorStats from the store for the category distribution chart
    const storeStats = store.stats
    if (storeStats) {
      vectorStats.value = {
        total_facts: storeStats.total_facts || 0,
        total_documents: storeStats.total_documents || 0,
        total_vectors: storeStats.total_vectors || 0,
        indexed_documents: storeStats.total_documents || 0,
        db_size: storeStats.db_size || 0,
        status: (storeStats.status as 'online' | 'offline' | 'unknown') || 'offline',
        rag_available: storeStats.rag_available || false,
        initialized: storeStats.initialized || false,
        llama_index_configured: storeStats.initialized || false,
        index_available: storeStats.initialized || false,
        redis_db: storeStats.redis_db ? parseInt(storeStats.redis_db) : 0,
        index_name: storeStats.index_name || 'unknown',
        last_updated: storeStats.last_updated || undefined,
        categories: Array.isArray(storeStats.categories)
          ? (storeStats.categories as unknown as { name?: string }[]).map((c) => c.name || c) as string[]
          : []
      }
    }
  } catch (error) {
    logger.error('Failed to refresh stats:', error)
    const errorMsg = error instanceof Error ? error.message : String(error)
    showErrorNotification(`Failed to load statistics: ${errorMsg}`)
  }
}

// Helper function to show error notifications
const showErrorNotification = (message: string) => {
  errorMessage.value = message
  logger.error(message)
  setTimeout(() => {
    errorMessage.value = ''
  }, 5000)
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

const getTypeColor = (type: string): string => {
  const colors: Record<string, string> = {
    document: 'var(--color-info)',
    webpage: 'var(--color-success)',
    api: 'var(--color-warning)',
    upload: 'var(--chart-purple)'
  }
  return colors[type] || 'var(--text-tertiary)'
}

const getTypePercentage = (count: number): number => {
  if (store.documentCount === 0) return 0
  return Math.round((count / store.documentCount) * 100)
}

const getActivityIcon = (type: string): IconName => {
  const icons: Record<string, IconName> = {
    created: 'plus-circle',
    updated: 'edit'
  }
  return icons[type] || 'circle'
}

const capitalize = (str: string): string => {
  return str && str.length > 0 ? str.charAt(0).toUpperCase() + str.slice(1) : str || ''
}

const getCategoryFactCount = (category: string): number => {
  return categoryFactCounts.value[category] || 0
}

const getCategoryPercentage = (category: string): number => {
  const total = vectorStats.value?.total_facts || 1
  const count = getCategoryFactCount(category)
  return Math.round((count / total) * 100)
}

const getCategoryColor = (index: number): string => {
  const colors = [
    'var(--color-primary)',
    'var(--color-success)',
    'var(--color-warning)',
    'var(--chart-purple)',
    'var(--color-error)',
    'var(--chart-cyan)'
  ]
  return colors[index % colors.length]
}

// Load stats on mount: unified refreshStats + refreshCategoryFacts
onMounted(async () => {
  // Fetch stats (controller + store) and populate recent activities
  await refreshStats()

  // Fetch category fact counts for the distribution chart
  const factsResult = await refreshCategoryFacts()
  if (factsResult === null) {
    logger.warn('Failed to fetch category facts, continuing with basic stats')
  }
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

/* Vector Chart Section */
.vector-chart-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  padding: var(--spacing-6);
}

.vector-chart-section h4 {
  color: var(--text-primary);
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  margin-bottom: var(--spacing-6);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.vector-categories-chart {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.category-bar {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.category-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: var(--text-sm);
}

.category-name {
  color: var(--text-primary);
  font-weight: var(--font-medium);
}

.category-count {
  color: var(--text-secondary);
  font-size: var(--text-xs);
}

.category-progress {
  height: 1.5rem;
  background: var(--bg-primary);
  border-radius: var(--radius-xl);
  overflow: hidden;
  position: relative;
}

.category-fill {
  height: 100%;
  border-radius: var(--radius-xl);
  transition: width var(--duration-500) var(--ease-out);
}

/* Overview Cards */
.stats-overview {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--spacing-6);
}

.stat-icon {
  width: 3.5rem;
  height: 3.5rem;
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-2xl);
  color: var(--text-on-primary);
}

.stat-icon.documents {
  background: var(--color-info);
}

.stat-icon.categories {
  background: var(--color-success);
}

.stat-icon.tags {
  background: var(--color-warning);
}

.stat-icon.storage {
  background: var(--chart-purple);
}

.stat-content {
  flex: 1;
}

.stat-content h4 {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2);
}

.stat-value {
  font-size: var(--text-3xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
  margin-bottom: var(--spacing-1);
}

.stat-change {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
}

/* Charts Section */
.charts-section {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: var(--spacing-6);
}

.charts-section h4 {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin-bottom: var(--spacing-4);
}

/* Bar Chart */
.bar-chart {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.bar-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
}

.bar-label {
  width: 120px;
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.bar-wrapper {
  flex: 1;
  height: 1.5rem;
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  position: relative;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  transition: width var(--duration-500) var(--ease-out);
}

.bar-value {
  position: absolute;
  right: var(--spacing-2);
  top: 50%;
  transform: translateY(-50%);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

/* Type Stats */
.type-stats {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.type-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-2);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
}

.type-color {
  width: 1rem;
  height: 1rem;
  border-radius: var(--radius-default);
}

.type-name {
  flex: 1;
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.type-count {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.type-percentage {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

/* Activity Section */
.activity-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-4);
  flex-wrap: wrap;
  gap: var(--spacing-3);
}

.activity-header h4 {
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0;
}

.feed-filter-chips {
  display: flex;
  gap: var(--spacing-2);
  flex-wrap: wrap;
}

.feed-chip {
  padding: var(--spacing-1) var(--spacing-3);
  border-radius: var(--radius-full);
  border: 1px solid var(--border-default);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  cursor: pointer;
  transition: var(--transition-all);
}

.feed-chip:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.feed-chip.active {
  background: var(--color-primary);
  color: var(--text-on-primary);
  border-color: var(--color-primary);
}

.activity-timeline {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
  max-height: 300px;
  overflow-y: auto;
}

.activity-item {
  display: flex;
  gap: var(--spacing-4);
  padding: var(--spacing-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
}

.activity-icon {
  width: 2rem;
  height: 2rem;
  border-radius: var(--radius-full);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-on-primary);
  font-size: var(--text-sm);
}

.activity-icon.created {
  background: var(--color-success);
}

.activity-icon.updated {
  background: var(--color-info);
}

.activity-content {
  flex: 1;
}

.activity-description {
  font-size: var(--text-sm);
  color: var(--text-primary);
  margin-bottom: var(--spacing-1);
}

.activity-time {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

/* Tag Cloud */
.tag-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-3);
  align-items: center;
}

.tag-cloud-item {
  color: var(--color-info);
  cursor: pointer;
  transition: var(--transition-all);
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-default);
  outline: none;
}

.tag-cloud-item:hover,
.tag-cloud-item:focus {
  color: var(--color-info-hover);
  transform: scale(1.1);
}

.tag-cloud-item:focus {
  box-shadow: 0 0 0 2px var(--color-info);
  background: var(--color-info-bg);
}

.tag-cloud-item:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

/* Actions */
.stats-actions {
  display: flex;
  justify-content: center;
  gap: var(--spacing-4);
  flex-wrap: wrap;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-6);
  border: 1px solid var(--border-default);
  background: var(--bg-primary);
  border-radius: var(--radius-md);
  font-weight: var(--font-medium);
  color: var(--text-primary);
  cursor: pointer;
  transition: var(--transition-all);
}

.action-btn:hover {
  background: var(--bg-secondary);
}

.action-btn.primary {
  background: var(--color-info);
  color: var(--text-on-primary);
  border-color: var(--color-info);
}

.action-btn.primary:hover {
  background: var(--color-info-hover);
  border-color: var(--color-info-hover);
}

/* Responsive */
@media (max-width: 768px) {
  .stats-overview {
    grid-template-columns: 1fr;
  }

  .charts-section {
    grid-template-columns: 1fr;
  }

  .bar-label {
    width: 80px;
    font-size: var(--text-xs);
  }

  .stats-actions {
    flex-direction: column;
  }

  .action-btn {
    width: 100%;
    justify-content: center;
  }

  .activity-header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
