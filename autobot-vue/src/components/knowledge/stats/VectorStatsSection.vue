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
  const colors = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444', '#06b6d4']
  return colors[index % colors.length]
}
</script>

<style scoped>
.vector-stats-section {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 0.75rem;
  padding: 2rem;
  margin-bottom: 2rem;
  color: white;
  box-shadow: 0 10px 40px rgba(102, 126, 234, 0.3);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

.section-header h3 {
  color: white;
  font-size: 1.5rem;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.refresh-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border: 1px solid rgba(255, 255, 255, 0.3);
  background: rgba(255, 255, 255, 0.1);
  border-radius: 0.375rem;
  font-size: 0.875rem;
  color: white;
  cursor: pointer;
  transition: all 0.2s;
}

.refresh-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.2);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.vector-overview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.needs-attention {
  border-color: rgba(251, 191, 36, 0.5);
  animation: pulse-card 2s ease-in-out infinite;
}

@keyframes pulse-card {
  0%, 100% { border-color: rgba(251, 191, 36, 0.3); }
  50% { border-color: rgba(251, 191, 36, 0.6); }
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

.vector-stat-icon.facts { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }
.vector-stat-icon.vectors { background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); }
.vector-stat-icon.database { background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%); }
.vector-stat-icon.status { background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); }

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
  0%, 100% { box-shadow: 0 0 0 0 rgba(251, 191, 36, 0.4); }
  50% { box-shadow: 0 0 0 8px rgba(251, 191, 36, 0); }
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

.notice-content strong { color: #fbbf24; font-weight: 700; }

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

.notice-hint i { color: #fbbf24; }

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

.category-name { color: white; font-weight: 500; }
.category-count { color: rgba(255, 255, 255, 0.7); font-size: 0.75rem; }

.category-progress {
  height: 1.5rem;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 0.75rem;
  overflow: hidden;
}

.category-fill {
  height: 100%;
  border-radius: 0.75rem;
  transition: width 0.5s ease;
  box-shadow: 0 0 10px rgba(255, 255, 255, 0.3);
}

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

.health-item.active i { color: #10b981; }

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
</style>
