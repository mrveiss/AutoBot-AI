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
 * Issue #704: Migrated to design tokens for SSOT theming
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
/* Issue #704: Migrated to design tokens for SSOT theming */

.doc-suggestion-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1-5);
  padding: var(--spacing-1) var(--spacing-2-5);
  background: linear-gradient(135deg, var(--bg-tertiary) 0%, var(--border-emphasis) 100%);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  transition: all var(--duration-150) var(--ease-in-out);
  max-width: 100%;
}

.doc-suggestion-chip.clickable {
  cursor: pointer;
}

.doc-suggestion-chip.clickable:hover {
  background: linear-gradient(135deg, var(--border-emphasis) 0%, var(--border-strong) 100%);
  border-color: var(--color-secondary-light);
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}

.doc-suggestion-chip.selected {
  background: linear-gradient(135deg, var(--color-info-bg) 0%, rgba(59, 130, 246, 0.2) 100%);
  border-color: var(--color-info);
  color: var(--color-info-dark);
}

.chip-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: var(--spacing-4);
  height: var(--spacing-4);
  font-size: 0.625rem;
  border-radius: var(--radius-full);
  flex-shrink: 0;
}

/* Category-specific icon colors - using design token chart colors */
.chip-icon.category-architecture { color: var(--chart-purple); }
.chip-icon.category-developer { color: var(--chart-blue); }
.chip-icon.category-api { color: var(--color-success); }
.chip-icon.category-troubleshooting { color: var(--color-warning); }
.chip-icon.category-deployment { color: var(--color-error); }
.chip-icon.category-security { color: var(--color-primary); }
.chip-icon.category-features { color: var(--chart-orange); }
.chip-icon.category-testing { color: var(--chart-teal); }
.chip-icon.category-workflow { color: var(--chart-purple); }
.chip-icon.category-guides { color: var(--chart-cyan); }
.chip-icon.category-implementation { color: var(--text-tertiary); }
.chip-icon.category-agents { color: var(--chart-purple-light); }
.chip-icon.category-general { color: var(--text-muted); }

.chip-label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: var(--font-medium);
}

.chip-score {
  font-size: 0.625rem;
  font-weight: var(--font-semibold);
  padding: var(--spacing-0-5) var(--spacing-1-5);
  border-radius: var(--radius-full);
  flex-shrink: 0;
}

.chip-score.score-excellent {
  background: var(--color-success-bg);
  color: var(--color-success-dark);
}

.chip-score.score-good {
  background: var(--color-info-bg);
  color: var(--color-info-dark);
}

.chip-score.score-fair {
  background: var(--color-warning-bg);
  color: var(--color-warning-dark);
}

.chip-score.score-low {
  background: var(--bg-hover);
  color: var(--text-muted);
}

.chip-dismiss {
  display: flex;
  align-items: center;
  justify-content: center;
  width: var(--spacing-4);
  height: var(--spacing-4);
  padding: 0;
  background: none;
  border: none;
  border-radius: var(--radius-full);
  color: var(--color-secondary-light);
  cursor: pointer;
  flex-shrink: 0;
  transition: all var(--duration-150) var(--ease-in-out);
}

.chip-dismiss:hover {
  background: var(--color-error-bg);
  color: var(--color-error-hover);
}

.chip-dismiss:focus-visible {
  outline: 2px solid var(--color-info);
  outline-offset: 1px;
}
</style>
