<template>
  <div v-if="stats" class="vector-stats-section">
    <div class="section-header">
      <h3><i class="fas fa-project-diagram"></i> Vector Database Statistics</h3>
      <button @click="$emit('refresh')"
              :disabled="loading"
              class="refresh-btn"
              aria-label="Refresh vector database statistics">
        <i class="fas fa-sync" :class="{ 'fa-spin': loading }" aria-hidden="true"></i>
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
          <p class="vector-stat-value">{{ stats.total_facts || 0 }}</p>
          <p class="vector-stat-label">Knowledge items stored</p>
        </div>
      </BasePanel>

      <BasePanel variant="elevated" size="medium" :class="{ 'needs-attention': needsVectorization }">
        <div class="vector-stat-icon vectors">
          <i class="fas fa-cubes"></i>
        </div>
        <div class="vector-stat-content">
          <h4>Total Vectors</h4>
          <p class="vector-stat-value">{{ stats.total_vectors || 0 }}</p>
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
          <p class="vector-stat-value">{{ formatFileSize(stats.db_size || 0) }}</p>
          <p class="vector-stat-label">Storage used</p>
        </div>
      </BasePanel>

      <BasePanel variant="elevated" size="medium">
        <div class="vector-stat-icon status">
          <i class="fas fa-check-circle"></i>
        </div>
        <div class="vector-stat-content">
          <h4>Status</h4>
          <StatusBadge :variant="getStatusVariant(stats.status)" size="small" class="vector-stat-value">
            {{ stats.status || 'unknown' }}
          </StatusBadge>
          <p class="vector-stat-label">RAG: {{ stats.rag_available ? 'Available' : 'Unavailable' }}</p>
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
          You have <strong>{{ stats.total_facts }} facts</strong> stored in the knowledge base,
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
          v-for="(category, idx) in stats.categories"
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
        <div class="health-item" :class="{ active: stats.initialized }">
          <i class="fas fa-check-circle"></i>
          <span>Initialized</span>
        </div>
        <div class="health-item" :class="{ active: stats.llama_index_configured }">
          <i class="fas fa-cube"></i>
          <span>LlamaIndex</span>
        </div>
        <div class="health-item" :class="{ active: stats.llama_index_configured }">
          <i class="fas fa-link"></i>
          <span>LangChain</span>
        </div>
        <div class="health-item" :class="{ active: stats.index_available }">
          <i class="fas fa-layer-group"></i>
          <span>Index Available</span>
        </div>
        <div class="health-item" :class="{ active: stats.rag_available }">
          <i class="fas fa-brain"></i>
          <span>RAG Available</span>
        </div>
      </div>
      <div class="health-details">
        <div class="detail-item">
          <label>Redis DB:</label>
          <span class="mono">{{ stats.redis_db }}</span>
        </div>
        <div class="detail-item">
          <label>Index Name:</label>
          <span class="mono">{{ stats.index_name }}</span>
        </div>
        <div class="detail-item">
          <label>Vector Framework:</label>
          <span class="mono">LlamaIndex + LangChain</span>
        </div>
        <div class="detail-item">
          <label>Embedding Model:</label>
          <span class="mono">{{ embeddingModelDisplay }}</span>
        </div>
        <div class="detail-item">
          <label>Text Splitter:</label>
          <span class="mono">LangChain RecursiveCharacterTextSplitter</span>
        </div>
        <div class="detail-item">
          <label>Last Updated:</label>
          <span>{{ formatDateTime(stats.last_updated) }}</span>
        </div>
        <div class="detail-item">
          <label>Indexed Documents:</label>
          <span>{{ stats.indexed_documents || 0 }}</span>
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
 * Vector Stats Section Component
 *
 * Displays vector database statistics including facts, vectors, health indicators.
 * Extracted from KnowledgeStats.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import { computed } from 'vue'
import BasePanel from '@/components/base/BasePanel.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import {
  formatFileSize,
  formatDateTime,
  formatCategoryName
} from '@/utils/formatHelpers'

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

interface Props {
  stats: VectorStats | null
  loading: boolean
  categoryFactCounts: Record<string, number>
}

interface Emits {
  (e: 'refresh'): void
}

const props = defineProps<Props>()
defineEmits<Emits>()

const needsVectorization = computed(() => {
  if (!props.stats) return false
  const totalFacts = props.stats.total_facts || 0
  const totalVectors = props.stats.total_vectors || 0
  return totalFacts > 0 && totalVectors === 0
})

const embeddingModelDisplay = computed(() => {
  if (!props.stats) return 'Loading...'
  const model = props.stats.embedding_model
  const dimensions = props.stats.embedding_dimensions
  if (model && dimensions) return `${model} (${dimensions}-dim)`
  if (model) return model
  return 'Not configured'
})

const getStatusVariant = (status: string): 'success' | 'danger' | 'secondary' => {
  const variantMap: Record<string, 'success' | 'danger' | 'secondary'> = {
    'online': 'success',
    'offline': 'danger',
    'unknown': 'secondary'
  }
  return variantMap[status] || 'secondary'
}

const getCategoryFactCount = (category: string): number => {
  return props.categoryFactCounts[category] || 0
}

const getCategoryPercentage = (category: string): number => {
  const total = props.stats?.total_facts || 1
  const count = getCategoryFactCount(category)
  return Math.round((count / total) * 100)
}

const getCategoryColor = (index: number): string => {
  // Uses CSS custom property values for consistency with design tokens
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
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.vector-stats-section {
  background: var(--chart-purple);
  border-radius: var(--radius-lg);
  padding: var(--spacing-8);
  margin-bottom: var(--spacing-8);
  color: var(--text-on-primary);
  box-shadow: var(--shadow-xl);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-6);
}

.section-header h3 {
  color: var(--text-on-primary);
  font-size: 1.5rem;
  font-weight: var(--font-bold);
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
}

.refresh-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  border: 1px solid var(--bg-primary-transparent-hover);
  background: var(--bg-primary-transparent);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  color: var(--text-on-primary);
  cursor: pointer;
  transition: all var(--duration-200) var(--ease-in-out);
}

.refresh-btn:hover:not(:disabled) {
  background: var(--bg-primary-transparent-hover);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.vector-overview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-6);
  margin-bottom: var(--spacing-8);
}

.needs-attention {
  border-color: var(--color-warning-border);
  animation: pulse-card 2s ease-in-out infinite;
}

@keyframes pulse-card {
  0%, 100% { border-color: var(--color-warning-border); opacity: 0.7; }
  50% { border-color: var(--color-warning); opacity: 1; }
}

.vector-stat-icon {
  width: 3.5rem;
  height: 3.5rem;
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.75rem;
  color: var(--text-on-primary);
  flex-shrink: 0;
}

.vector-stat-icon.facts { background: var(--chart-pink); }
.vector-stat-icon.vectors { background: var(--chart-cyan); }
.vector-stat-icon.database { background: var(--color-success); }
.vector-stat-icon.status { background: var(--chart-pink); }

.vector-stat-content h4 {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
  margin-bottom: var(--spacing-2);
  font-weight: var(--font-medium);
}

.vector-stat-value {
  font-size: 2rem;
  font-weight: var(--font-bold);
  color: var(--text-primary);
  margin-bottom: var(--spacing-1);
  line-height: 1;
}

.vector-stat-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.vector-stat-label.warning {
  color: var(--color-warning);
  font-weight: var(--font-semibold);
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
}

.vectorization-notice {
  display: flex;
  gap: var(--spacing-4);
  background: var(--color-warning-bg-transparent);
  border: 1px solid var(--color-warning-border);
  border-radius: var(--radius-lg);
  padding: var(--spacing-6);
  margin-bottom: var(--spacing-8);
  animation: pulse-warning 2s ease-in-out infinite;
}

@keyframes pulse-warning {
  0%, 100% { box-shadow: 0 0 0 0 var(--color-warning-border); }
  50% { box-shadow: 0 0 0 8px transparent; }
}

.notice-icon {
  width: 3rem;
  height: 3rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-warning-bg-transparent);
  border-radius: 50%;
  color: var(--color-warning);
  font-size: 1.5rem;
  flex-shrink: 0;
}

.notice-content h4 {
  color: var(--text-on-primary);
  font-size: 1.125rem;
  font-weight: var(--font-semibold);
  margin-bottom: var(--spacing-3);
}

.notice-content p {
  color: var(--text-on-primary-muted);
  font-size: var(--text-sm);
  line-height: 1.6;
  margin-bottom: var(--spacing-2);
}

.notice-content strong { color: var(--color-warning); font-weight: var(--font-bold); }

.notice-hint {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3);
  background: var(--bg-overlay);
  border-radius: var(--radius-md);
  margin-top: var(--spacing-3);
  font-size: 0.8125rem;
  color: var(--text-on-primary-muted);
}

.notice-hint i { color: var(--color-warning); }

.vector-chart-section {
  background: var(--bg-primary-transparent);
  backdrop-filter: blur(10px);
  border: 1px solid var(--bg-primary-transparent-hover);
  border-radius: var(--radius-lg);
  padding: var(--spacing-6);
  margin-bottom: var(--spacing-8);
}

.vector-chart-section h4 {
  color: var(--text-on-primary);
  font-size: 1.125rem;
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

.category-name { color: var(--text-on-primary); font-weight: var(--font-medium); }
.category-count { color: var(--text-on-primary-muted); font-size: var(--text-xs); }

.category-progress {
  height: 1.5rem;
  background: var(--bg-primary-transparent);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.category-fill {
  height: 100%;
  border-radius: var(--radius-lg);
  transition: width var(--duration-500) var(--ease-in-out);
  box-shadow: var(--shadow-glow);
}

.vector-health-section {
  background: var(--bg-primary-transparent);
  backdrop-filter: blur(10px);
  border: 1px solid var(--bg-primary-transparent-hover);
  border-radius: var(--radius-lg);
  padding: var(--spacing-6);
}

.vector-health-section h4 {
  color: var(--text-on-primary);
  font-size: 1.125rem;
  font-weight: var(--font-semibold);
  margin-bottom: var(--spacing-6);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.health-indicators {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}

.health-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-4);
  background: var(--bg-primary-transparent-light);
  border: 1px solid var(--bg-primary-transparent);
  border-radius: var(--radius-md);
  color: var(--text-on-primary-muted);
  font-size: var(--text-sm);
  transition: all var(--duration-300) var(--ease-in-out);
}

.health-item.active {
  background: var(--color-success-bg-transparent);
  border-color: var(--color-success);
  color: var(--text-on-primary);
}

.health-item.active i { color: var(--color-success); }

.health-details {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-4);
  padding-top: var(--spacing-4);
  border-top: 1px solid var(--bg-primary-transparent);
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.detail-item label {
  font-size: var(--text-xs);
  color: var(--text-on-primary-muted);
  font-weight: var(--font-medium);
}

.detail-item span {
  font-size: var(--text-sm);
  color: var(--text-on-primary);
}

.detail-item .mono {
  font-family: var(--font-mono);
  background: var(--bg-overlay);
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-sm);
}
</style>
