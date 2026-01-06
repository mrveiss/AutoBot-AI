<template>
  <div class="knowledge-stats">
    <!-- Error Notification -->
    <div v-if="errorMessage" class="error-notification" role="alert" aria-live="assertive">
      <i class="fas fa-exclamation-circle"></i>
      <span>{{ errorMessage }}</span>
      <button @click="errorMessage = ''" class="close-btn" aria-label="Close error message">
        <i class="fas fa-times"></i>
      </button>
    </div>

    <!-- Vector Database Statistics Section -->
    <div v-if="vectorStats" class="vector-stats-section">
      <div class="section-header">
        <h3><i class="fas fa-project-diagram"></i> Vector Database Statistics</h3>
        <button @click="refreshVectorStats"
                :disabled="isRefreshingVectorStats"
                class="refresh-btn"
                aria-label="Refresh vector database statistics">
          <i class="fas fa-sync" :class="{ 'fa-spin': isRefreshingVectorStats }" aria-hidden="true"></i>
          Refresh
        </button>
      </div>

      <div class="vector-overview-grid">
        <BasePanel variant="elevated" size="medium">
          <div class="vector-stat-icon facts">
            <i class="fas fa-lightbulb"></i>
          </div>
          <div class="vector-stat-content">
            <h4>Total Facts</h4>
            <p class="vector-stat-value">{{ vectorStats.total_facts || 0 }}</p>
            <p class="vector-stat-label">Knowledge items stored</p>
          </div>
        </BasePanel>

        <BasePanel variant="elevated" size="medium" :class="{ 'needs-attention': needsVectorization }">
          <div class="vector-stat-icon vectors">
            <i class="fas fa-cubes"></i>
          </div>
          <div class="vector-stat-content">
            <h4>Total Vectors</h4>
            <p class="vector-stat-value">{{ vectorStats.total_vectors || 0 }}</p>
            <p v-if="needsVectorization" class="vector-stat-label warning">
              <i class="fas fa-exclamation-triangle"></i> Not vectorized
            </p>
            <p v-else class="vector-stat-label">Embeddings generated</p>
          </div>
        </BasePanel>

        <BasePanel variant="elevated" size="medium">
          <div class="vector-stat-icon database">
            <i class="fas fa-database"></i>
          </div>
          <div class="vector-stat-content">
            <h4>Database Size</h4>
            <p class="vector-stat-value">{{ formatFileSize(vectorStats.db_size || 0) }}</p>
            <p class="vector-stat-label">Storage used</p>
          </div>
        </BasePanel>

        <BasePanel variant="elevated" size="medium">
          <div class="vector-stat-icon status">
            <i class="fas fa-check-circle"></i>
          </div>
          <div class="vector-stat-content">
            <h4>Status</h4>
            <StatusBadge :variant="getStatusVariant(vectorStats.status)" size="small" class="vector-stat-value">
              {{ vectorStats.status || 'unknown' }}
            </StatusBadge>
            <p class="vector-stat-label">RAG: {{ vectorStats.rag_available ? 'Available' : 'Unavailable' }}</p>
          </div>
        </BasePanel>
      </div>

      <!-- Vectorization Notice -->
      <div v-if="needsVectorization" class="vectorization-notice">
        <div class="notice-icon">
          <i class="fas fa-info-circle"></i>
        </div>
        <div class="notice-content">
          <h4>Vector Embeddings Not Generated</h4>
          <p>
            You have <strong>{{ vectorStats.total_facts }} facts</strong> stored in the knowledge base,
            but they haven't been vectorized yet. Vector embeddings enable semantic search and RAG capabilities.
          </p>
          <p class="notice-hint">
            <i class="fas fa-lightbulb"></i>
            Vectors are typically generated automatically when facts are added through the proper ingestion pipeline.
            If you imported facts manually, they may need to be re-indexed to generate embeddings.
          </p>
        </div>
      </div>

      <!-- Vector Categories Distribution Chart -->
      <div class="vector-chart-section">
        <h4><i class="fas fa-chart-pie"></i> Vector Distribution by Category</h4>
        <div class="vector-categories-chart">
          <div
            v-for="(category, idx) in vectorStats.categories"
            :key="idx"
            class="category-bar"
          >
            <div class="category-info">
              <span class="category-name">{{ formatCategoryName(category) }}</span>
              <span class="category-count">{{ getCategoryFactCount(category) }} facts</span>
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

      <!-- Vector Index Health -->
      <div class="vector-health-section">
        <h4><i class="fas fa-heartbeat"></i> Vector Index Health</h4>
        <div class="health-indicators">
          <div class="health-item" :class="{ active: vectorStats.initialized }">
            <i class="fas fa-check-circle"></i>
            <span>Initialized</span>
          </div>
          <div class="health-item" :class="{ active: vectorStats.llama_index_configured }">
            <i class="fas fa-cube"></i>
            <span>LlamaIndex</span>
          </div>
          <div class="health-item" :class="{ active: vectorStats.llama_index_configured }">
            <i class="fas fa-link"></i>
            <span>LangChain</span>
          </div>
          <div class="health-item" :class="{ active: vectorStats.index_available }">
            <i class="fas fa-layer-group"></i>
            <span>Index Available</span>
          </div>
          <div class="health-item" :class="{ active: vectorStats.rag_available }">
            <i class="fas fa-brain"></i>
            <span>RAG Available</span>
          </div>
        </div>
        <div class="health-details">
          <div class="detail-item">
            <label>Redis DB:</label>
            <span class="mono">{{ vectorStats.redis_db }}</span>
          </div>
          <div class="detail-item">
            <label>Index Name:</label>
            <span class="mono">{{ vectorStats.index_name }}</span>
          </div>
          <div class="detail-item">
            <label>Vector Framework:</label>
            <span class="mono">LlamaIndex + LangChain</span>
          </div>
          <div class="detail-item">
            <label>Embedding Model:</label>
            <span class="mono">{{ getEmbeddingModelDisplay() }}</span>
          </div>
          <div class="detail-item">
            <label>Text Splitter:</label>
            <span class="mono">LangChain RecursiveCharacterTextSplitter</span>
          </div>
          <div class="detail-item">
            <label>Last Updated:</label>
            <span>{{ formatDateTimeHelper(vectorStats.last_updated) }}</span>
          </div>
          <div class="detail-item">
            <label>Indexed Documents:</label>
            <span>{{ vectorStats.indexed_documents || 0 }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Document Change Feed Section (PROMINENT) -->
    <div class="change-feed-section-wrapper">
      <div class="section-header prominent">
        <h3><i class="fas fa-sync-alt"></i> Document Lifecycle & Vectorization</h3>
        <span class="section-badge">Real-time Tracking</span>
      </div>
      <DocumentChangeFeed />
    </div>

    <!-- Overview Cards -->
    <div class="stats-overview" role="region" aria-label="Knowledge base overview statistics">
      <BasePanel variant="elevated" size="small" role="article" aria-labelledby="facts-title">
        <div class="stat-icon facts" aria-hidden="true">
          <i class="fas fa-lightbulb"></i>
        </div>
        <div class="stat-content">
          <h4 id="facts-title">Total Facts</h4>
          <p class="stat-value" aria-live="polite">{{ vectorStats?.total_facts || 0 }}</p>
          <p class="stat-change" aria-label="Knowledge items stored in Redis database">
            Knowledge items in Redis
          </p>
        </div>
      </BasePanel>

      <BasePanel variant="elevated" size="small" role="article" aria-labelledby="documents-title">
        <div class="stat-icon documents" aria-hidden="true">
          <i class="fas fa-file-alt"></i>
        </div>
        <div class="stat-content">
          <h4 id="documents-title">Total Documents</h4>
          <p class="stat-value" aria-live="polite">{{ vectorStats?.total_documents || 0 }}</p>
          <p class="stat-change" :class="{ 'needs-vectorization': needsVectorization }"
             :aria-label="needsVectorization ? 'Warning: Facts are not vectorized for semantic search' : 'Facts are vectorized and ready for semantic search'">
            <i v-if="needsVectorization" class="fas fa-exclamation-triangle" aria-hidden="true"></i>
            {{ needsVectorization ? 'Not vectorized' : 'Vectorized for RAG' }}
          </p>
        </div>
      </BasePanel>

      <BasePanel variant="elevated" size="small" role="article" aria-labelledby="categories-title">
        <div class="stat-icon categories" aria-hidden="true">
          <i class="fas fa-folder"></i>
        </div>
        <div class="stat-content">
          <h4 id="categories-title">Categories</h4>
          <p class="stat-value" aria-live="polite">{{ store.categoryCount }}</p>
          <p class="stat-change" aria-label="Average documents per category">
            {{ avgDocsPerCategory }} avg docs/category
          </p>
        </div>
      </BasePanel>

      <BasePanel variant="elevated" size="small">
        <div class="stat-icon tags">
          <i class="fas fa-tags"></i>
        </div>
        <div class="stat-content">
          <h4>Unique Tags</h4>
          <p class="stat-value">{{ store.allTags.length }}</p>
          <p class="stat-change">
            {{ avgTagsPerDoc }} avg tags/doc
          </p>
        </div>
      </BasePanel>

      <BasePanel variant="elevated" size="small">
        <div class="stat-icon storage">
          <i class="fas fa-database"></i>
        </div>
        <div class="stat-content">
          <h4>Storage Used</h4>
          <p class="stat-value">{{ formatFileSize(totalStorageSize) }}</p>
          <p class="stat-change">
            {{ formatFileSize(avgDocSize) }} avg/doc
          </p>
        </div>
      </BasePanel>
    </div>

    <!-- Charts Section -->
    <div class="charts-section">
      <!-- Documents by Category -->
      <BasePanel variant="bordered" size="medium">
        <h4>Documents by Category</h4>
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
                  backgroundColor: category.color || '#3b82f6'
                }"
              ></div>
              <span class="bar-value">{{ category.documentCount }}</span>
            </div>
          </div>
        </div>
      </BasePanel>

      <!-- Documents by Type -->
      <BasePanel variant="bordered" size="medium">
        <h4>Documents by Type</h4>
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

    <!-- Recent Activity -->
    <BasePanel variant="bordered" size="medium">
      <h4>Recent Activity</h4>
      <div class="activity-timeline">
        <div v-for="activity in recentActivities" :key="activity.id" class="activity-item">
          <div class="activity-icon" :class="activity.type">
            <i :class="getActivityIcon(activity.type)"></i>
          </div>
          <div class="activity-content">
            <p class="activity-description">{{ activity.description }}</p>
            <p class="activity-time">{{ formatTimeAgo(activity.timestamp) }}</p>
          </div>
        </div>
        <EmptyState
          v-if="recentActivities.length === 0"
          icon="fas fa-clock"
          message="No recent activity"
        />
      </div>
    </BasePanel>

    <!-- Tag Cloud -->
    <BasePanel variant="bordered" size="medium">
      <h4>Popular Tags</h4>
      <div class="tag-cloud" role="list" aria-label="Popular tags in knowledge base">
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

    <!-- System Knowledge Navigation Card (Issue #678: Consolidated ManPageManager to Manage → Advanced) -->
    <BasePanel variant="bordered" size="medium" class="system-knowledge-nav">
      <div class="nav-card-content">
        <div class="nav-card-icon">
          <i class="fas fa-terminal"></i>
        </div>
        <div class="nav-card-info">
          <h4>System Knowledge Management</h4>
          <p>Initialize machine knowledge, integrate man pages, and manage system-level documentation.</p>
          <div class="nav-card-features">
            <span class="feature-tag"><i class="fas fa-desktop"></i> Machine Profile</span>
            <span class="feature-tag"><i class="fas fa-book"></i> Man Pages</span>
            <span class="feature-tag"><i class="fas fa-search"></i> Search</span>
          </div>
        </div>
        <router-link to="/knowledge/manage" class="nav-card-action">
          <BaseButton variant="primary" size="sm">
            <i class="fas fa-arrow-right"></i>
            Go to Manage → Advanced
          </BaseButton>
        </router-link>
      </div>
    </BasePanel>

    <!-- Actions -->
    <div class="stats-actions">
      <button @click="exportStats" class="action-btn">
        <i class="fas fa-download"></i>
        Export Statistics
      </button>
      <button @click="optimizeKnowledge" class="action-btn">
        <i class="fas fa-compress"></i>
        Optimize Database
      </button>
      <button @click="generateReport" class="action-btn primary">
        <i class="fas fa-file-chart-line"></i>
        Generate Report
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import { useKnowledgeController } from '@/models/controllers/index'
// ManPageManager removed - consolidated to Manage → Advanced (Issue #678)
import DocumentChangeFeed from '@/components/knowledge/DocumentChangeFeed.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import apiClient from '@/utils/ApiClient'
import { parseApiResponse } from '@/utils/apiResponseHelpers'
import {
  formatFileSize,
  formatTimeAgo,
  formatDateTime as formatDateTimeHelper,
  formatCategoryName
} from '@/utils/formatHelpers'
import EmptyState from '@/components/ui/EmptyState.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import BasePanel from '@/components/base/BasePanel.vue'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for KnowledgeStats
const logger = createLogger('KnowledgeStats')

// Import shared document feed wrapper styles
import '@/styles/document-feed-wrapper.css'

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
  type: 'created' | 'updated' | 'deleted' | 'imported'
  description: string
  timestamp: Date | string
}

interface KnowledgeController {
  refreshStats: () => Promise<void>
  getDetailedStats: () => Promise<Record<string, any>>
  cleanupKnowledgeBase: () => Promise<void>
  reindexKnowledgeBase: () => Promise<void>
}

interface DetailedStats {
  [key: string]: number | string | boolean | object
}

const store = useKnowledgeStore()

// Defensive controller initialization
let controller: KnowledgeController | null = null
try {
  controller = useKnowledgeController() as any
  logger.info('Knowledge controller initialized:', controller)
} catch (error) {
  logger.error('Failed to initialize knowledge controller:', error)
  controller = {
    refreshStats: async () => { logger.warn('Controller not available') },
    getDetailedStats: async () => ({}),
    cleanupKnowledgeBase: async () => { logger.warn('Controller not available') },
    reindexKnowledgeBase: async () => { logger.warn('Controller not available') }
  }
}

// State
const isRefreshing = ref<boolean>(false)
const detailedStats = ref<DetailedStats | null>(null)
const recentActivities = ref<Activity[]>([])
const vectorStats = ref<VectorStats | null>(null)
const isRefreshingVectorStats = ref<boolean>(false)
const categoryFactCounts = ref<Record<string, number>>({})
const errorMessage = ref<string>('')

// Computed statistics
const needsVectorization = computed(() => {
  if (!vectorStats.value) return false
  const totalFacts = vectorStats.value.total_facts || 0
  const totalVectors = vectorStats.value.total_vectors || 0
  return totalFacts > 0 && totalVectors === 0
})

const recentDocsCount = computed(() => {
  const oneWeekAgo = new Date()
  oneWeekAgo.setDate(oneWeekAgo.getDate() - 7)

  return store.documents.filter(doc =>
    new Date(doc.createdAt) > oneWeekAgo
  ).length
})

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
  documents.forEach((doc: any) => {
    types[doc.type] = (types[doc.type] || 0) + 1
  })
  return types
})

const popularTags = computed(() => {
  const tagCounts: Record<string, number> = {}

  const documents = store.documents || []
  documents.forEach((doc: any) => {
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

// Methods
const refreshStats = async () => {
  isRefreshing.value = true

  try {
    if (controller && typeof controller.refreshStats === 'function') {
      await controller.refreshStats()
    } else {
      logger.warn('Controller refreshStats method not available')
    }

    if (controller && typeof controller.getDetailedStats === 'function') {
      detailedStats.value = await controller.getDetailedStats()
    } else {
      logger.warn('Controller getDetailedStats method not available')
      detailedStats.value = {}
    }

    generateRecentActivities()
  } catch (error) {
    logger.error('Failed to refresh stats:', error)
  } finally {
    isRefreshing.value = false
  }
}

const generateRecentActivities = () => {
  // Generate activities from recent documents
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

const optimizeKnowledge = async () => {
  if (!confirm('Optimize knowledge base? This will clean up unused data and rebuild indexes.')) {
    return
  }

  try {
    if (controller && typeof controller.cleanupKnowledgeBase === 'function') {
      await controller.cleanupKnowledgeBase()
    } else {
      logger.warn('Controller cleanupKnowledgeBase method not available')
    }

    if (controller && typeof controller.reindexKnowledgeBase === 'function') {
      await controller.reindexKnowledgeBase()
    } else {
      logger.warn('Controller reindexKnowledgeBase method not available')
    }

    await refreshStats()
  } catch (error) {
    logger.error('Failed to optimize knowledge base:', error)
  }
}

const generateReport = async () => {
  // Generate a comprehensive report
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
// NOTE: formatFileSize removed - now using shared utility from @/utils/formatHelpers

const estimateTextSize = (text: string): number => {
  // Rough estimate: 1 character = 1 byte
  return text.length
}

const getTypeColor = (type: string): string => {
  const colors: Record<string, string> = {
    document: '#3b82f6',
    webpage: '#10b981',
    api: '#f59e0b',
    upload: '#8b5cf6'
  }
  return colors[type] || '#6b7280'
}

const getTypePercentage = (count: number): number => {
  if (store.documentCount === 0) return 0
  return Math.round((count / store.documentCount) * 100)
}

const getActivityIcon = (type: string): string => {
  const icons: Record<string, string> = {
    created: 'fas fa-plus-circle',
    updated: 'fas fa-edit',
    deleted: 'fas fa-trash',
    imported: 'fas fa-download'
  }
  return icons[type] || 'fas fa-circle'
}

// StatusBadge variant mapping function
const getStatusVariant = (status: string): 'success' | 'danger' | 'secondary' => {
  const variantMap: Record<string, 'success' | 'danger' | 'secondary'> = {
    'online': 'success',
    'offline': 'danger',
    'unknown': 'secondary'
  }
  return variantMap[status] || 'secondary'
}

// NOTE: formatRelativeTime removed - now using formatTimeAgo from @/utils/formatHelpers

const capitalize = (str: string): string => {
  return str && str.length > 0 ? str.charAt(0).toUpperCase() + str.slice(1) : str || ''
}

// Helper function to show error notifications
const showErrorNotification = (message: string) => {
  errorMessage.value = message
  logger.error(message)
  // Clear error message after 5 seconds
  setTimeout(() => {
    errorMessage.value = ''
  }, 5000)
}

// Vector Stats Functions
// NEW: Use shared store's refreshStats action (consolidates API calls)
const refreshVectorStats = async () => {
  isRefreshingVectorStats.value = true
  errorMessage.value = '' // Clear any previous errors

  try {
    // Use shared store instead of direct API call - reduces duplicate requests
    await store.refreshStats()

    // Map store stats to local vectorStats format
    const storeStats = store.stats
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
        ? storeStats.categories.map((c: any) => c.name || c)
        : [],
      embedding_model: 'nomic-embed-text',  // From detailed stats
      embedding_dimensions: 768  // From detailed stats
    }

    // Fetch category fact counts (secondary API call - only when needed)
    try {
      const factsResponse = await apiClient.get('/api/knowledge_base/facts/by_category')
      const factsData = await parseApiResponse(factsResponse)

      if (factsData && factsData.categories) {
        const counts: Record<string, number> = {}
        Object.keys(factsData.categories).forEach((category: string) => {
          counts[category] = factsData.categories[category].length
        })
        categoryFactCounts.value = counts
      }
    } catch (factsError) {
      logger.warn('Failed to fetch category facts, continuing with basic stats:', factsError)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : 'Unknown error occurred'
    logger.error('Failed to refresh vector stats:', error)
    showErrorNotification(`Failed to load statistics: ${errorMsg}`)

    // Set default values on error to prevent UI breaking
    if (!vectorStats.value) {
      vectorStats.value = {
        total_facts: 0,
        total_documents: 0,
        total_vectors: 0,
        indexed_documents: 0,
        db_size: 0,
        status: 'offline',
        rag_available: false,
        initialized: false,
        llama_index_configured: false,
        index_available: false,
        redis_db: 0,
        index_name: 'unknown'
      }
    }
  } finally {
    isRefreshingVectorStats.value = false
  }
}

// NOTE: formatCategoryName removed - now using shared utility from @/utils/formatHelpers

const getCategoryFactCount = (category: string): number => {
  return categoryFactCounts.value[category] || 0
}

const getCategoryPercentage = (category: string): number => {
  const total = vectorStats.value?.total_facts || 1
  const count = getCategoryFactCount(category)
  return Math.round((count / total) * 100)
}

const getCategoryColor = (index: number): string => {
  const colors = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444', '#06b6d4']
  return colors[index % colors.length]
}

// NOTE: formatDateTime removed - now using formatDateTimeHelper from @/utils/formatHelpers

const getEmbeddingModelDisplay = (): string => {
  if (!vectorStats.value) return 'Loading...'

  const model = vectorStats.value.embedding_model
  const dimensions = vectorStats.value.embedding_dimensions

  if (model && dimensions) {
    return `${model} (${dimensions}-dim)`
  } else if (model) {
    return model
  } else {
    return 'Not configured'
  }
}

// Load stats on mount
onMounted(() => {
  refreshStats()
  refreshVectorStats()
})
</script>

<style scoped>
.knowledge-stats {
  padding: 1.5rem;
}

.stats-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
}

.stats-header h3 {
  font-size: 1.25rem;
  font-weight: 600;
  color: #1f2937;
}

.refresh-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border: 1px solid #d1d5db;
  background: white;
  border-radius: 0.375rem;
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.2s;
}

.refresh-btn:hover:not(:disabled) {
  background: #f3f4f6;
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Error Notification */
.error-notification {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem 1.5rem;
  margin-bottom: 1.5rem;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-left: 4px solid #ef4444;
  border-radius: 0.5rem;
  color: #991b1b;
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

.error-notification i.fa-exclamation-circle {
  font-size: 1.25rem;
  color: #ef4444;
  flex-shrink: 0;
}

.error-notification span {
  flex: 1;
  font-size: 0.875rem;
  font-weight: 500;
}

.error-notification .close-btn {
  background: none;
  border: none;
  padding: 0.25rem;
  color: #991b1b;
  cursor: pointer;
  opacity: 0.7;
  transition: opacity 0.2s;
  flex-shrink: 0;
}

.error-notification .close-btn:hover {
  opacity: 1;
}

/* Overview Cards */
.stats-overview {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

/* stat-card structure removed - now using BasePanel */

.stat-icon {
  width: 3.5rem;
  height: 3.5rem;
  border-radius: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5rem;
  color: white;
}

.stat-icon.facts {
  background: linear-gradient(135deg, #f093fb, #f5576c);
}

.stat-icon.documents {
  background: linear-gradient(135deg, #3b82f6, #2563eb);
}

.stat-icon.categories {
  background: linear-gradient(135deg, #10b981, #059669);
}

.stat-icon.tags {
  background: linear-gradient(135deg, #f59e0b, #d97706);
}

.stat-icon.storage {
  background: linear-gradient(135deg, #8b5cf6, #7c3aed);
}

.stat-content {
  flex: 1;
}

.stat-content h4 {
  font-size: 0.875rem;
  color: #6b7280;
  margin-bottom: 0.5rem;
}

.stat-value {
  font-size: 1.875rem;
  font-weight: 700;
  color: #1f2937;
  margin-bottom: 0.25rem;
}

.stat-change {
  font-size: 0.875rem;
  color: #6b7280;
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.stat-change.positive {
  color: #10b981;
}

.stat-change.needs-vectorization {
  color: #f59e0b;
  font-weight: 500;
}

/* Charts Section */
.charts-section {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

/* chart-container structure removed - now using BasePanel */

.charts-section h4 {
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 1rem;
}

/* Bar Chart */
.bar-chart {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.bar-item {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.bar-label {
  width: 120px;
  font-size: 0.875rem;
  color: #374151;
}

.bar-wrapper {
  flex: 1;
  height: 1.5rem;
  background: #f3f4f6;
  border-radius: 0.375rem;
  position: relative;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  transition: width 0.5s ease;
}

.bar-value {
  position: absolute;
  right: 0.5rem;
  top: 50%;
  transform: translateY(-50%);
  font-size: 0.75rem;
  font-weight: 500;
  color: #374151;
}

/* Type Stats */
.type-stats {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.type-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem;
  background: #f9fafb;
  border-radius: 0.375rem;
}

.type-color {
  width: 1rem;
  height: 1rem;
  border-radius: 0.25rem;
}

.type-name {
  flex: 1;
  font-weight: 500;
  color: #374151;
}

.type-count {
  font-weight: 600;
  color: #1f2937;
}

.type-percentage {
  font-size: 0.875rem;
  color: #6b7280;
}

/* Activity Section */
/* activity-section structure removed - now using BasePanel */
/* h4 styling now handled by component-level styles */

.activity-timeline {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  max-height: 300px;
  overflow-y: auto;
}

.activity-item {
  display: flex;
  gap: 1rem;
  padding: 0.75rem;
  background: #f9fafb;
  border-radius: 0.375rem;
}

.activity-icon {
  width: 2rem;
  height: 2rem;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 0.875rem;
}

.activity-icon.created {
  background: #10b981;
}

.activity-icon.updated {
  background: #3b82f6;
}

.activity-icon.deleted {
  background: #ef4444;
}

.activity-content {
  flex: 1;
}

.activity-description {
  font-size: 0.875rem;
  color: #374151;
  margin-bottom: 0.25rem;
}

.activity-time {
  font-size: 0.75rem;
  color: #6b7280;
}

/* Tag Cloud */
/* tag-cloud-section structure removed - now using BasePanel */
/* h4 styling now handled by component-level styles */

.tag-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: center;
}

.tag-cloud-item {
  color: #3b82f6;
  cursor: pointer;
  transition: all 0.2s;
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
  outline: none;
}

.tag-cloud-item:hover,
.tag-cloud-item:focus {
  color: #2563eb;
  transform: scale(1.1);
}

.tag-cloud-item:focus {
  box-shadow: 0 0 0 2px #3b82f6;
  background: rgba(59, 130, 246, 0.1);
}

/* Vector Database Statistics Section */
.vector-stats-section {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 0.75rem;
  padding: 2rem;
  margin-bottom: 2rem;
  color: white;
  box-shadow: 0 10px 40px rgba(102, 126, 234, 0.3);
}

/* Document change feed wrapper styles now in shared CSS: @/styles/document-feed-wrapper.css */

.vectorization-notice {
  display: flex;
  gap: 1rem;
  background: rgba(251, 191, 36, 0.15);
  border: 1px solid rgba(251, 191, 36, 0.4);
  border-radius: 0.75rem;
  padding: 1.5rem;
  margin-bottom: 2rem;
  animation: pulse-warning 2s ease-in-out infinite;
}

@keyframes pulse-warning {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(251, 191, 36, 0.4);
  }
  50% {
    box-shadow: 0 0 0 8px rgba(251, 191, 36, 0);
  }
}

.notice-icon {
  width: 3rem;
  height: 3rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(251, 191, 36, 0.2);
  border-radius: 50%;
  color: #fbbf24;
  font-size: 1.5rem;
  flex-shrink: 0;
}

.notice-content h4 {
  color: white;
  font-size: 1.125rem;
  font-weight: 600;
  margin-bottom: 0.75rem;
}

.notice-content p {
  color: rgba(255, 255, 255, 0.9);
  font-size: 0.875rem;
  line-height: 1.6;
  margin-bottom: 0.5rem;
}

.notice-content strong {
  color: #fbbf24;
  font-weight: 700;
}

.notice-hint {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 0.5rem;
  margin-top: 0.75rem;
  font-size: 0.8125rem;
  color: rgba(255, 255, 255, 0.8);
}

.notice-hint i {
  color: #fbbf24;
}

.vector-stats-section .section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

.vector-stats-section .section-header h3 {
  color: white;
  font-size: 1.5rem;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.vector-overview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

/* vector-stat-card structure removed - now using BasePanel */
/* BasePanel handles background, border, padding automatically */

.needs-attention {
  border-color: rgba(251, 191, 36, 0.5);
  animation: pulse-card 2s ease-in-out infinite;
}

@keyframes pulse-card {
  0%, 100% {
    border-color: rgba(251, 191, 36, 0.3);
  }
  50% {
    border-color: rgba(251, 191, 36, 0.6);
  }
}

.vector-stat-icon {
  width: 3.5rem;
  height: 3.5rem;
  border-radius: 0.75rem;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.75rem;
  color: white;
  flex-shrink: 0;
}

.vector-stat-icon.facts {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
}

.vector-stat-icon.vectors {
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
}

.vector-stat-icon.database {
  background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
}

.vector-stat-icon.status {
  background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
}

.vector-stat-content h4 {
  font-size: 0.875rem;
  color: #6b7280;
  margin-bottom: 0.5rem;
  font-weight: 500;
}

.vector-stat-value {
  font-size: 2rem;
  font-weight: 700;
  color: #1f2937;
  margin-bottom: 0.25rem;
  line-height: 1;
}

.vector-stat-label {
  font-size: 0.75rem;
  color: #6b7280;
}

.vector-stat-label.warning {
  color: #fbbf24;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

/* Vector Chart Section */
.vector-chart-section {
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 0.75rem;
  padding: 1.5rem;
  margin-bottom: 2rem;
}

.vector-chart-section h4 {
  color: white;
  font-size: 1.125rem;
  font-weight: 600;
  margin-bottom: 1.5rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.vector-categories-chart {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.category-bar {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.category-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.875rem;
}

.category-name {
  color: white;
  font-weight: 500;
}

.category-count {
  color: rgba(255, 255, 255, 0.7);
  font-size: 0.75rem;
}

.category-progress {
  height: 1.5rem;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 0.75rem;
  overflow: hidden;
  position: relative;
}

.category-fill {
  height: 100%;
  border-radius: 0.75rem;
  transition: width 0.5s ease;
  box-shadow: 0 0 10px rgba(255, 255, 255, 0.3);
}

/* Vector Health Section */
.vector-health-section {
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 0.75rem;
  padding: 1.5rem;
}

.vector-health-section h4 {
  color: white;
  font-size: 1.125rem;
  font-weight: 600;
  margin-bottom: 1.5rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.health-indicators {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.health-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 0.5rem;
  color: rgba(255, 255, 255, 0.5);
  font-size: 0.875rem;
  transition: all 0.3s ease;
}

.health-item.active {
  background: rgba(16, 185, 129, 0.2);
  border-color: #10b981;
  color: white;
}

.health-item.active i {
  color: #10b981;
}

.health-details {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  padding-top: 1rem;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.detail-item label {
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.6);
  font-weight: 500;
}

.detail-item span {
  font-size: 0.875rem;
  color: white;
}

.detail-item .mono {
  font-family: 'Courier New', monospace;
  background: rgba(0, 0, 0, 0.2);
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
}

/* Man Pages Section */
/* manpages-section structure removed - now using BasePanel */

/* Actions */
.stats-actions {
  display: flex;
  justify-content: center;
  gap: 1rem;
  flex-wrap: wrap;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1.5rem;
  border: 1px solid #d1d5db;
  background: white;
  border-radius: 0.375rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover {
  background: #f3f4f6;
}

.action-btn.primary {
  background: #3b82f6;
  color: white;
  border-color: #3b82f6;
}

.action-btn.primary:hover {
  background: #2563eb;
  border-color: #2563eb;
}

/* System Knowledge Navigation Card (Issue #678) */
.system-knowledge-nav {
  margin-bottom: 2rem;
}

.nav-card-content {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  padding: 0.5rem;
}

.nav-card-icon {
  width: 4rem;
  height: 4rem;
  border-radius: 0.75rem;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.nav-card-icon i {
  font-size: 1.75rem;
  color: white;
}

.nav-card-info {
  flex: 1;
}

.nav-card-info h4 {
  font-size: 1.125rem;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 0.5rem;
}

.nav-card-info p {
  font-size: 0.875rem;
  color: #6b7280;
  margin-bottom: 0.75rem;
  line-height: 1.5;
}

.nav-card-features {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.feature-tag {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.625rem;
  background: #f3f4f6;
  border-radius: 9999px;
  font-size: 0.75rem;
  color: #4b5563;
}

.feature-tag i {
  font-size: 0.625rem;
  color: #9ca3af;
}

.nav-card-action {
  flex-shrink: 0;
}

.nav-card-action a {
  text-decoration: none;
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
    font-size: 0.75rem;
  }

  .stats-actions {
    flex-direction: column;
  }

  .action-btn {
    width: 100%;
    justify-content: center;
  }

  .nav-card-content {
    flex-direction: column;
    text-align: center;
  }

  .nav-card-features {
    justify-content: center;
  }
}
</style>
