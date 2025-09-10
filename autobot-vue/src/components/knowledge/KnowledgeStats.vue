<template>
  <div class="knowledge-stats">
    <div class="stats-header">
      <h3>Knowledge Base Statistics</h3>
      <button @click="refreshStats" :disabled="isRefreshing" class="refresh-btn">
        <i class="fas fa-sync" :class="{ 'fa-spin': isRefreshing }"></i>
        Refresh
      </button>
    </div>

    <!-- Overview Cards -->
    <div class="stats-overview">
      <div class="stat-card">
        <div class="stat-icon documents">
          <i class="fas fa-file-alt"></i>
        </div>
        <div class="stat-content">
          <h4>Total Documents</h4>
          <p class="stat-value">{{ store.documentCount }}</p>
          <p class="stat-change positive">
            <i class="fas fa-arrow-up"></i>
            {{ recentDocsCount }} this week
          </p>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon categories">
          <i class="fas fa-folder"></i>
        </div>
        <div class="stat-content">
          <h4>Categories</h4>
          <p class="stat-value">{{ store.categoryCount }}</p>
          <p class="stat-change">
            {{ avgDocsPerCategory }} avg docs/category
          </p>
        </div>
      </div>

      <div class="stat-card">
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
      </div>

      <div class="stat-card">
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
      </div>
    </div>

    <!-- Charts Section -->
    <div class="charts-section">
      <!-- Documents by Category -->
      <div class="chart-container">
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
      </div>

      <!-- Documents by Type -->
      <div class="chart-container">
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
      </div>
    </div>

    <!-- Recent Activity -->
    <div class="activity-section">
      <h4>Recent Activity</h4>
      <div class="activity-timeline">
        <div v-for="activity in recentActivities" :key="activity.id" class="activity-item">
          <div class="activity-icon" :class="activity.type">
            <i :class="getActivityIcon(activity.type)"></i>
          </div>
          <div class="activity-content">
            <p class="activity-description">{{ activity.description }}</p>
            <p class="activity-time">{{ formatRelativeTime(activity.timestamp) }}</p>
          </div>
        </div>
        <div v-if="recentActivities.length === 0" class="no-activity">
          <p>No recent activity</p>
        </div>
      </div>
    </div>

    <!-- Tag Cloud -->
    <div class="tag-cloud-section">
      <h4>Popular Tags</h4>
      <div class="tag-cloud">
        <span
          v-for="tag in popularTags"
          :key="tag.name"
          class="tag-cloud-item"
          :style="{ fontSize: `${tag.size}rem` }"
          :title="`${tag.count} documents`"
        >
          {{ tag.name }}
        </span>
      </div>
    </div>

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
import { useKnowledgeController } from '@/models/controllers'
import type { KnowledgeCategory } from '@/stores/useKnowledgeStore'

const store = useKnowledgeStore()

// Defensive controller initialization
let controller: any = null
try {
  controller = useKnowledgeController()
  console.log('Knowledge controller initialized:', controller)
} catch (error) {
  console.error('Failed to initialize knowledge controller:', error)
  controller = {
    refreshStats: async () => console.warn('Controller not available'),
    getDetailedStats: async () => ({}),
    cleanupKnowledgeBase: async () => console.warn('Controller not available'),
    reindexKnowledgeBase: async () => console.warn('Controller not available')
  }
}

// State
const isRefreshing = ref(false)
const detailedStats = ref<any>(null)
const recentActivities = ref<any[]>([])

// Computed statistics
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
  (store.documents || []).forEach(doc => {
    types[doc.type] = (types[doc.type] || 0) + 1
  })
  return types
})

const popularTags = computed(() => {
  const tagCounts: Record<string, number> = {}

  (store.documents || []).forEach(doc => {
    (doc.tags || []).forEach(tag => {
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
      console.warn('Controller refreshStats method not available')
    }
    
    if (controller && typeof controller.getDetailedStats === 'function') {
      detailedStats.value = await controller.getDetailedStats()
    } else {
      console.warn('Controller getDetailedStats method not available')
      detailedStats.value = {}
    }
    
    generateRecentActivities()
  } catch (error) {
    console.error('Failed to refresh stats:', error)
  } finally {
    isRefreshing.value = false
  }
}

const generateRecentActivities = () => {
  // Generate activities from recent documents
  const activities = store.documents
    .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime())
    .slice(0, 10)
    .map(doc => ({
      id: doc.id,
      type: new Date(doc.createdAt).getTime() === new Date(doc.updatedAt).getTime() ? 'created' : 'updated',
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
      console.warn('Controller cleanupKnowledgeBase method not available')
    }
    
    if (controller && typeof controller.reindexKnowledgeBase === 'function') {
      await controller.reindexKnowledgeBase()
    } else {
      console.warn('Controller reindexKnowledgeBase method not available')
    }
    
    await refreshStats()
  } catch (error) {
    console.error('Failed to optimize knowledge base:', error)
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
const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 Bytes'
  const k = 1024
  const sizes = ['Bytes', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

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

const formatRelativeTime = (date: Date | string): string => {
  const d = typeof date === 'string' ? new Date(date) : date
  const now = new Date()
  const diff = now.getTime() - d.getTime()

  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)

  if (minutes < 60) return `${minutes} minutes ago`
  if (hours < 24) return `${hours} hours ago`
  if (days < 7) return `${days} days ago`

  return d.toLocaleDateString()
}

const capitalize = (str: string): string => {
  return str && str.length > 0 ? str.charAt(0).toUpperCase() + str.slice(1) : str || ''
}

// Load stats on mount
onMounted(() => {
  refreshStats()
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

/* Overview Cards */
.stats-overview {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.stat-card {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  padding: 1.5rem;
  display: flex;
  gap: 1rem;
}

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

/* Charts Section */
.charts-section {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.chart-container {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  padding: 1.5rem;
}

.chart-container h4 {
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
.activity-section {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  padding: 1.5rem;
  margin-bottom: 2rem;
}

.activity-section h4 {
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 1rem;
}

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

.no-activity {
  text-align: center;
  padding: 2rem;
  color: #6b7280;
}

/* Tag Cloud */
.tag-cloud-section {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  padding: 1.5rem;
  margin-bottom: 2rem;
}

.tag-cloud-section h4 {
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 1rem;
}

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
}

.tag-cloud-item:hover {
  color: #2563eb;
  transform: scale(1.1);
}

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
}
</style>
