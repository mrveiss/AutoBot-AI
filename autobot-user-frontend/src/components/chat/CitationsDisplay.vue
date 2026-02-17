<template>
  <div class="knowledge-citations">
    <div class="citations-header" @click="toggleExpanded">
      <div class="citations-header-left">
        <i class="fas fa-brain text-autobot-primary" aria-hidden="true"></i>
        <span class="citations-label">Knowledge Sources</span>
        <span class="citations-count">{{ citations.length }}</span>
      </div>
      <i
        :class="isExpanded ? 'fas fa-chevron-up' : 'fas fa-chevron-down'"
        aria-hidden="true"
      ></i>
    </div>
    <Transition name="slide-fade">
      <div v-if="isExpanded" class="citations-list">
        <div
          v-for="(citation, idx) in citations"
          :key="citation.id || idx"
          class="citation-item"
          @click="$emit('citation-click', citation)"
        >
          <div class="citation-rank">[{{ citation.rank || idx + 1 }}]</div>
          <div class="citation-content">
            <div class="citation-text">{{ truncateContent(citation.content) }}</div>
            <div class="citation-meta">
              <span class="citation-score" :class="getScoreClass(citation.score)">
                <i class="fas fa-chart-line" aria-hidden="true"></i>
                {{ formatScore(citation.score) }}%
              </span>
              <span v-if="citation.source" class="citation-source">
                <i class="fas fa-file-alt" aria-hidden="true"></i>
                {{ formatSourcePath(citation.source) }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Citations Display Component
 *
 * Displays knowledge base citations for AI responses.
 * Extracted from ChatMessages.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 * Issue #249: Knowledge Base Citations Display
 * Issue #704: Migrated to design tokens
 */

import { ref } from 'vue'

interface Citation {
  id?: string
  rank?: number
  content: string
  score: number
  source?: string
}

interface Props {
  citations: Citation[]
  maxLength?: number
  initiallyExpanded?: boolean
}

interface Emits {
  (e: 'citation-click', citation: Citation): void
  (e: 'expanded-change', expanded: boolean): void
}

const props = withDefaults(defineProps<Props>(), {
  maxLength: 200,
  initiallyExpanded: false
})

const emit = defineEmits<Emits>()

const isExpanded = ref(props.initiallyExpanded)

const toggleExpanded = () => {
  isExpanded.value = !isExpanded.value
  emit('expanded-change', isExpanded.value)
}

const truncateContent = (content: string): string => {
  if (!content) return ''
  if (content.length <= props.maxLength) return content
  return content.substring(0, props.maxLength).trim() + '...'
}

const getScoreClass = (score: number): string => {
  if (score >= 0.9) return 'score-excellent'
  if (score >= 0.8) return 'score-good'
  if (score >= 0.7) return 'score-acceptable'
  return 'score-low'
}

const formatScore = (score: number): string => {
  return (score * 100).toFixed(0)
}

const formatSourcePath = (sourcePath: string): string => {
  if (!sourcePath) return 'Unknown'
  const parts = sourcePath.split('/')
  return parts[parts.length - 1] || sourcePath
}
</script>

<style scoped>
.knowledge-citations {
  margin-top: var(--spacing-3);
  border: 1px solid var(--color-primary-bg);
  border-radius: var(--radius-lg);
  background: linear-gradient(
    135deg,
    var(--color-primary-bg) 0%,
    rgba(99, 102, 241, 0.02) 100%
  );
  overflow: hidden;
}

.citations-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-2-5) var(--spacing-3-5);
  cursor: pointer;
  user-select: none;
  transition: background var(--duration-200);
}

.citations-header:hover {
  background: var(--color-primary-bg);
}

.citations-header-left {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.citations-label {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-primary-hover);
}

.citations-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 var(--spacing-1-5);
  background: var(--color-primary-hover);
  color: var(--text-on-primary);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  border-radius: var(--radius-full);
}

.citations-list {
  border-top: 1px solid var(--color-primary-bg-hover);
}

.citation-item {
  display: flex;
  gap: var(--spacing-2-5);
  padding: var(--spacing-2-5) var(--spacing-3-5);
  border-bottom: 1px solid var(--color-primary-bg);
  cursor: pointer;
  transition: background var(--duration-200);
}

.citation-item:last-child {
  border-bottom: none;
}

.citation-item:hover {
  background: rgba(99, 102, 241, 0.08);
}

.citation-rank {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-primary-bg-hover);
  color: var(--color-primary-hover);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  border-radius: var(--radius-md);
}

.citation-content {
  flex: 1;
  min-width: 0;
}

.citation-text {
  font-size: var(--text-sm);
  color: var(--text-primary);
  line-height: var(--leading-normal);
  margin-bottom: var(--spacing-1-5);
}

.citation-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-3);
  font-size: var(--text-xs);
}

.citation-score,
.citation-source {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
}

.citation-score {
  font-weight: var(--font-semibold);
}

.score-excellent {
  color: var(--chart-green);
}

.score-good {
  color: var(--color-success-light);
}

.score-acceptable {
  color: var(--color-warning);
}

.score-low {
  color: var(--text-secondary);
}

.citation-source {
  color: var(--text-tertiary);
}

/* Transition */
.slide-fade-enter-active {
  transition: all var(--duration-300) var(--ease-out);
}

.slide-fade-leave-active {
  transition: all var(--duration-200) var(--ease-in);
}

.slide-fade-enter-from,
.slide-fade-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

@media (max-width: 640px) {
  .citation-meta {
    flex-direction: column;
    gap: var(--spacing-1);
  }
}
</style>
