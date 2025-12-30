<template>
  <div
    class="doc-result-card"
    :class="{ 'expanded': isExpanded, 'highlighted': isHighlighted }"
    @click="handleClick"
    role="article"
    :aria-expanded="isExpanded"
  >
    <!-- Card Header -->
    <div class="card-header">
      <div class="header-left">
        <span class="category-badge" :class="`category-${category}`">
          <i :class="categoryIcon" aria-hidden="true"></i>
          {{ categoryLabel }}
        </span>
        <span v-if="section" class="section-label">{{ section }}</span>
      </div>
      <div class="header-right">
        <span v-if="score !== undefined" class="relevance-score" :class="scoreClass">
          <i class="fas fa-chart-line" aria-hidden="true"></i>
          {{ formatScore(score) }}%
        </span>
        <button
          class="expand-btn"
          @click.stop="toggleExpand"
          :aria-label="isExpanded ? 'Collapse content' : 'Expand content'"
        >
          <i :class="isExpanded ? 'fas fa-chevron-up' : 'fas fa-chevron-down'" aria-hidden="true"></i>
        </button>
      </div>
    </div>

    <!-- Card Title -->
    <h3 class="card-title">{{ title }}</h3>

    <!-- Card Content -->
    <div class="card-content" :class="{ 'truncated': !isExpanded }">
      <p class="content-preview">{{ displayContent }}</p>
    </div>

    <!-- Card Footer -->
    <div class="card-footer">
      <div class="footer-left">
        <span class="file-path" :title="filePath">
          <i class="fas fa-file-alt" aria-hidden="true"></i>
          {{ displayFilePath }}
        </span>
      </div>
      <div class="footer-right">
        <button
          class="action-btn copy-btn"
          @click.stop="copyContent"
          title="Copy content"
          aria-label="Copy documentation content"
        >
          <i :class="isCopied ? 'fas fa-check' : 'fas fa-copy'" aria-hidden="true"></i>
        </button>
        <button
          class="action-btn insert-btn"
          @click.stop="insertIntoChat"
          title="Insert into chat"
          aria-label="Insert documentation into chat"
        >
          <i class="fas fa-quote-right" aria-hidden="true"></i>
        </button>
        <button
          v-if="filePath"
          class="action-btn open-btn"
          @click.stop="openDocument"
          title="Open document"
          aria-label="Open full document"
        >
          <i class="fas fa-external-link-alt" aria-hidden="true"></i>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Documentation Result Card Component
 *
 * Displays a documentation search result with expandable content,
 * relevance scoring, and quick action buttons.
 *
 * Issue #165: Chat Documentation UI Integration
 */

import { ref, computed } from 'vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('DocumentationResultCard')

interface Props {
  title: string
  content: string
  category?: string
  section?: string
  filePath?: string
  score?: number
  isHighlighted?: boolean
  maxContentLength?: number
}

interface Emits {
  (e: 'click'): void
  (e: 'expand', expanded: boolean): void
  (e: 'copy', content: string): void
  (e: 'insert', content: string): void
  (e: 'open', filePath: string): void
}

const props = withDefaults(defineProps<Props>(), {
  category: 'general',
  isHighlighted: false,
  maxContentLength: 300
})

const emit = defineEmits<Emits>()

const isExpanded = ref(false)
const isCopied = ref(false)

// Category configuration
const categoryConfig: Record<string, { icon: string; label: string }> = {
  architecture: { icon: 'fas fa-project-diagram', label: 'Architecture' },
  developer: { icon: 'fas fa-code', label: 'Developer' },
  api: { icon: 'fas fa-plug', label: 'API' },
  troubleshooting: { icon: 'fas fa-wrench', label: 'Troubleshooting' },
  deployment: { icon: 'fas fa-rocket', label: 'Deployment' },
  security: { icon: 'fas fa-shield-alt', label: 'Security' },
  features: { icon: 'fas fa-star', label: 'Features' },
  testing: { icon: 'fas fa-vial', label: 'Testing' },
  workflow: { icon: 'fas fa-sitemap', label: 'Workflow' },
  guides: { icon: 'fas fa-book', label: 'Guides' },
  implementation: { icon: 'fas fa-cogs', label: 'Implementation' },
  agents: { icon: 'fas fa-robot', label: 'Agents' },
  general: { icon: 'fas fa-file-alt', label: 'General' }
}

const categoryIcon = computed(() => {
  return categoryConfig[props.category]?.icon || categoryConfig.general.icon
})

const categoryLabel = computed(() => {
  return categoryConfig[props.category]?.label || props.category
})

const displayContent = computed(() => {
  if (isExpanded.value || props.content.length <= props.maxContentLength) {
    return props.content
  }
  return props.content.substring(0, props.maxContentLength).trim() + '...'
})

const displayFilePath = computed(() => {
  if (!props.filePath) return ''
  const parts = props.filePath.split('/')
  if (parts.length <= 3) return props.filePath
  return '.../' + parts.slice(-2).join('/')
})

const scoreClass = computed(() => {
  if (props.score === undefined) return ''
  if (props.score >= 0.9) return 'score-excellent'
  if (props.score >= 0.8) return 'score-good'
  if (props.score >= 0.7) return 'score-fair'
  return 'score-low'
})

const formatScore = (score: number): string => {
  return Math.round(score * 100).toString()
}

const handleClick = () => {
  emit('click')
}

const toggleExpand = () => {
  isExpanded.value = !isExpanded.value
  emit('expand', isExpanded.value)
}

const copyContent = async () => {
  try {
    await navigator.clipboard.writeText(props.content)
    isCopied.value = true
    emit('copy', props.content)
    setTimeout(() => {
      isCopied.value = false
    }, 2000)
  } catch (error) {
    logger.error('Failed to copy content:', error)
  }
}

const insertIntoChat = () => {
  emit('insert', props.content)
}

const openDocument = () => {
  if (props.filePath) {
    emit('open', props.filePath)
  }
}
</script>

<style scoped>
.doc-result-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 0.5rem;
  padding: 0.875rem;
  transition: all 0.2s ease;
  cursor: pointer;
}

.doc-result-card:hover {
  border-color: #cbd5e1;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.doc-result-card.highlighted {
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.doc-result-card.expanded {
  background: #f8fafc;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.category-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.125rem 0.5rem;
  font-size: 0.625rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.025em;
  border-radius: 9999px;
  background: #f1f5f9;
  color: #475569;
}

/* Category-specific badge colors */
.category-badge.category-architecture { background: #ede9fe; color: #6d28d9; }
.category-badge.category-developer { background: #dbeafe; color: #1d4ed8; }
.category-badge.category-api { background: #d1fae5; color: #047857; }
.category-badge.category-troubleshooting { background: #fef3c7; color: #b45309; }
.category-badge.category-deployment { background: #fee2e2; color: #b91c1c; }
.category-badge.category-security { background: #e0e7ff; color: #4338ca; }
.category-badge.category-features { background: #ffedd5; color: #c2410c; }
.category-badge.category-testing { background: #ccfbf1; color: #0f766e; }
.category-badge.category-workflow { background: #f3e8ff; color: #7c3aed; }
.category-badge.category-guides { background: #e0f2fe; color: #0369a1; }
.category-badge.category-implementation { background: #f1f5f9; color: #475569; }
.category-badge.category-agents { background: #fae8ff; color: #a21caf; }

.section-label {
  font-size: 0.75rem;
  color: #64748b;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.relevance-score {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.75rem;
  font-weight: 600;
  padding: 0.125rem 0.375rem;
  border-radius: 0.25rem;
}

.relevance-score.score-excellent { background: #dcfce7; color: #166534; }
.relevance-score.score-good { background: #dbeafe; color: #1e40af; }
.relevance-score.score-fair { background: #fef3c7; color: #92400e; }
.relevance-score.score-low { background: #f3f4f6; color: #6b7280; }

.expand-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  padding: 0;
  background: none;
  border: none;
  border-radius: 0.25rem;
  color: #64748b;
  cursor: pointer;
  transition: all 0.15s ease;
}

.expand-btn:hover {
  background: #f1f5f9;
  color: #334155;
}

.card-title {
  font-size: 0.875rem;
  font-weight: 600;
  color: #1e293b;
  margin: 0 0 0.5rem 0;
  line-height: 1.4;
}

.card-content {
  margin-bottom: 0.75rem;
}

.card-content.truncated .content-preview {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.content-preview {
  font-size: 0.8125rem;
  color: #475569;
  line-height: 1.6;
  margin: 0;
  white-space: pre-wrap;
}

.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 0.5rem;
  border-top: 1px solid #f1f5f9;
}

.footer-left {
  flex: 1;
  min-width: 0;
}

.file-path {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.6875rem;
  color: #94a3b8;
  font-family: ui-monospace, monospace;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.footer-right {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.75rem;
  height: 1.75rem;
  padding: 0;
  background: none;
  border: 1px solid transparent;
  border-radius: 0.25rem;
  color: #64748b;
  cursor: pointer;
  transition: all 0.15s ease;
}

.action-btn:hover {
  background: #f1f5f9;
  border-color: #e2e8f0;
  color: #334155;
}

.action-btn.copy-btn:hover { color: #3b82f6; }
.action-btn.insert-btn:hover { color: #10b981; }
.action-btn.open-btn:hover { color: #8b5cf6; }

.action-btn:focus-visible {
  outline: 2px solid #3b82f6;
  outline-offset: 1px;
}
</style>
