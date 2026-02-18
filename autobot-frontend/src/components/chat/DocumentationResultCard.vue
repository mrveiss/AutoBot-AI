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
/* Issue #704: Migrated to design tokens */

.doc-result-card {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--spacing-3-5);
  transition: all var(--duration-200) var(--ease-in-out);
  cursor: pointer;
}

.doc-result-card:hover {
  border-color: var(--border-default);
  box-shadow: var(--shadow-sm);
}

.doc-result-card.highlighted {
  border-color: var(--color-info);
  box-shadow: var(--shadow-focus);
}

.doc-result-card.expanded {
  background: var(--bg-secondary);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-2);
}

.header-left {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.category-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  padding: var(--spacing-0-5) var(--spacing-2);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  border-radius: var(--radius-full);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

/* Category-specific badge colors */
.category-badge.category-architecture { background: var(--chart-purple-bg); color: var(--chart-purple); }
.category-badge.category-developer { background: var(--color-info-bg); color: var(--color-info-dark); }
.category-badge.category-api { background: var(--color-success-bg); color: var(--color-success-dark); }
.category-badge.category-troubleshooting { background: var(--color-warning-bg); color: var(--color-warning-dark); }
.category-badge.category-deployment { background: var(--color-error-bg); color: var(--color-error-dark); }
.category-badge.category-security { background: var(--color-primary-bg); color: var(--color-primary-dark); }
.category-badge.category-features { background: var(--chart-orange-bg); color: var(--chart-orange); }
.category-badge.category-testing { background: var(--chart-green-bg); color: var(--chart-teal); }
.category-badge.category-workflow { background: var(--chart-purple-bg); color: var(--chart-purple); }
.category-badge.category-guides { background: var(--color-info-bg); color: var(--color-info); }
.category-badge.category-implementation { background: var(--bg-tertiary); color: var(--text-secondary); }
.category-badge.category-agents { background: var(--chart-pink-bg, rgba(236, 72, 153, 0.2)); color: var(--chart-pink); }

.section-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.header-right {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.relevance-score {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  padding: var(--spacing-0-5) var(--spacing-1-5);
  border-radius: var(--radius-default);
}

.relevance-score.score-excellent { background: var(--color-success-bg); color: var(--color-success-dark); }
.relevance-score.score-good { background: var(--color-info-bg); color: var(--color-info-dark); }
.relevance-score.score-fair { background: var(--color-warning-bg); color: var(--color-warning-dark); }
.relevance-score.score-low { background: var(--bg-tertiary); color: var(--text-tertiary); }

.expand-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  padding: 0;
  background: none;
  border: none;
  border-radius: var(--radius-default);
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all var(--duration-150) var(--ease-in-out);
}

.expand-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.card-title {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0 0 var(--spacing-2) 0;
  line-height: var(--leading-snug);
}

.card-content {
  margin-bottom: var(--spacing-3);
}

.card-content.truncated .content-preview {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.content-preview {
  font-size: 0.8125rem;
  color: var(--text-secondary);
  line-height: var(--leading-relaxed);
  margin: 0;
  white-space: pre-wrap;
}

.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: var(--spacing-2);
  border-top: 1px solid var(--border-subtle);
}

.footer-left {
  flex: 1;
  min-width: 0;
}

.file-path {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  font-size: 0.6875rem;
  color: var(--text-muted);
  font-family: var(--font-mono);
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.footer-right {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
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
  border-radius: var(--radius-default);
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all var(--duration-150) var(--ease-in-out);
}

.action-btn:hover {
  background: var(--bg-tertiary);
  border-color: var(--border-subtle);
  color: var(--text-secondary);
}

.action-btn.copy-btn:hover { color: var(--color-info); }
.action-btn.insert-btn:hover { color: var(--color-success); }
.action-btn.open-btn:hover { color: var(--chart-purple); }

.action-btn:focus-visible {
  outline: 2px solid var(--color-info);
  outline-offset: 1px;
}
</style>
