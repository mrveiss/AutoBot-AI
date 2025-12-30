<template>
  <div
    class="doc-suggestion-chip"
    :class="{ 'selected': isSelected, 'clickable': clickable }"
    @click="handleClick"
    :title="fullTitle"
    role="button"
    :tabindex="clickable ? 0 : -1"
    @keydown.enter="handleClick"
    @keydown.space.prevent="handleClick"
  >
    <span class="chip-icon" :class="iconClass">
      <i :class="categoryIcon" aria-hidden="true"></i>
    </span>
    <span class="chip-label">{{ displayLabel }}</span>
    <span v-if="showScore && score !== undefined" class="chip-score" :class="scoreClass">
      {{ formatScore(score) }}%
    </span>
    <button
      v-if="dismissible"
      class="chip-dismiss"
      @click.stop="$emit('dismiss')"
      aria-label="Dismiss suggestion"
    >
      <i class="fas fa-times" aria-hidden="true"></i>
    </button>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Documentation Suggestion Chip Component
 *
 * Displays a compact documentation suggestion that can be clicked
 * to quickly insert or search for documentation content.
 *
 * Issue #165: Chat Documentation UI Integration
 */

import { computed } from 'vue'

interface Props {
  label: string
  category?: string
  filePath?: string
  score?: number
  isSelected?: boolean
  clickable?: boolean
  dismissible?: boolean
  showScore?: boolean
  maxLabelLength?: number
}

interface Emits {
  (e: 'click'): void
  (e: 'dismiss'): void
}

const props = withDefaults(defineProps<Props>(), {
  category: 'general',
  isSelected: false,
  clickable: true,
  dismissible: false,
  showScore: false,
  maxLabelLength: 40
})

const emit = defineEmits<Emits>()

// Category icon mapping
const categoryIcons: Record<string, string> = {
  architecture: 'fas fa-project-diagram',
  developer: 'fas fa-code',
  api: 'fas fa-plug',
  troubleshooting: 'fas fa-wrench',
  deployment: 'fas fa-rocket',
  security: 'fas fa-shield-alt',
  features: 'fas fa-star',
  testing: 'fas fa-vial',
  workflow: 'fas fa-sitemap',
  guides: 'fas fa-book',
  implementation: 'fas fa-cogs',
  agents: 'fas fa-robot',
  general: 'fas fa-file-alt'
}

const categoryIcon = computed(() => {
  return categoryIcons[props.category] || categoryIcons.general
})

const iconClass = computed(() => {
  return `category-${props.category}`
})

const displayLabel = computed(() => {
  if (props.label.length <= props.maxLabelLength) {
    return props.label
  }
  return props.label.substring(0, props.maxLabelLength - 3) + '...'
})

const fullTitle = computed(() => {
  let title = props.label
  if (props.filePath) {
    title += `\n${props.filePath}`
  }
  if (props.score !== undefined) {
    title += `\nRelevance: ${formatScore(props.score)}%`
  }
  return title
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
  if (props.clickable) {
    emit('click')
  }
}
</script>

<style scoped>
.doc-suggestion-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.625rem;
  background: linear-gradient(135deg, #f0f4f8 0%, #e2e8f0 100%);
  border: 1px solid #cbd5e1;
  border-radius: 9999px;
  font-size: 0.75rem;
  color: #475569;
  transition: all 0.15s ease;
  max-width: 100%;
}

.doc-suggestion-chip.clickable {
  cursor: pointer;
}

.doc-suggestion-chip.clickable:hover {
  background: linear-gradient(135deg, #e2e8f0 0%, #cbd5e1 100%);
  border-color: #94a3b8;
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.doc-suggestion-chip.selected {
  background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
  border-color: #3b82f6;
  color: #1e40af;
}

.chip-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1rem;
  height: 1rem;
  font-size: 0.625rem;
  border-radius: 50%;
  flex-shrink: 0;
}

/* Category-specific icon colors */
.chip-icon.category-architecture { color: #8b5cf6; }
.chip-icon.category-developer { color: #3b82f6; }
.chip-icon.category-api { color: #10b981; }
.chip-icon.category-troubleshooting { color: #f59e0b; }
.chip-icon.category-deployment { color: #ef4444; }
.chip-icon.category-security { color: #6366f1; }
.chip-icon.category-features { color: #f97316; }
.chip-icon.category-testing { color: #14b8a6; }
.chip-icon.category-workflow { color: #8b5cf6; }
.chip-icon.category-guides { color: #0ea5e9; }
.chip-icon.category-implementation { color: #64748b; }
.chip-icon.category-agents { color: #a855f7; }
.chip-icon.category-general { color: #6b7280; }

.chip-label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
}

.chip-score {
  font-size: 0.625rem;
  font-weight: 600;
  padding: 0.125rem 0.375rem;
  border-radius: 9999px;
  flex-shrink: 0;
}

.chip-score.score-excellent {
  background: #dcfce7;
  color: #166534;
}

.chip-score.score-good {
  background: #dbeafe;
  color: #1e40af;
}

.chip-score.score-fair {
  background: #fef3c7;
  color: #92400e;
}

.chip-score.score-low {
  background: #f3f4f6;
  color: #6b7280;
}

.chip-dismiss {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1rem;
  height: 1rem;
  padding: 0;
  background: none;
  border: none;
  border-radius: 50%;
  color: #94a3b8;
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.15s ease;
}

.chip-dismiss:hover {
  background: #fee2e2;
  color: #dc2626;
}

.chip-dismiss:focus-visible {
  outline: 2px solid #3b82f6;
  outline-offset: 1px;
}
</style>
