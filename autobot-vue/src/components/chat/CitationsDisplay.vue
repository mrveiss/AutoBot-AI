<template>
  <div class="knowledge-citations">
    <div class="citations-header" @click="toggleExpanded">
      <div class="citations-header-left">
        <i class="fas fa-brain text-indigo-600" aria-hidden="true"></i>
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
  margin-top: 12px;
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.05) 0%, rgba(99, 102, 241, 0.02) 100%);
  overflow: hidden;
}

.citations-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;
}

.citations-header:hover {
  background: rgba(99, 102, 241, 0.1);
}

.citations-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.citations-label {
  font-size: 13px;
  font-weight: 600;
  color: #4f46e5;
}

.citations-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  background: #4f46e5;
  color: white;
  font-size: 11px;
  font-weight: 600;
  border-radius: 10px;
}

.citations-list {
  border-top: 1px solid rgba(99, 102, 241, 0.15);
}

.citation-item {
  display: flex;
  gap: 10px;
  padding: 10px 14px;
  border-bottom: 1px solid rgba(99, 102, 241, 0.1);
  cursor: pointer;
  transition: background 0.2s;
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
  background: rgba(99, 102, 241, 0.15);
  color: #4f46e5;
  font-size: 11px;
  font-weight: 600;
  border-radius: 6px;
}

.citation-content {
  flex: 1;
  min-width: 0;
}

.citation-text {
  font-size: 13px;
  color: #334155;
  line-height: 1.5;
  margin-bottom: 6px;
}

.citation-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 11px;
}

.citation-score,
.citation-source {
  display: flex;
  align-items: center;
  gap: 4px;
}

.citation-score {
  font-weight: 600;
}

.score-excellent {
  color: #22c55e;
}

.score-good {
  color: #84cc16;
}

.score-acceptable {
  color: #f59e0b;
}

.score-low {
  color: #94a3b8;
}

.citation-source {
  color: #64748b;
}

/* Transition */
.slide-fade-enter-active {
  transition: all 0.3s ease-out;
}

.slide-fade-leave-active {
  transition: all 0.2s ease-in;
}

.slide-fade-enter-from,
.slide-fade-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

@media (max-width: 640px) {
  .citation-meta {
    flex-direction: column;
    gap: 4px;
  }
}
</style>
