<template>
  <div class="knowledge-citations">
    <div
      class="citations-header"
      role="button"
      tabindex="0"
      :aria-expanded="isExpanded"
      @click="toggleExpanded"
      @keydown.enter.prevent="toggleExpanded"
      @keydown.space.prevent="toggleExpanded"
    >
      <div class="citations-header-left">
        <Icon name="layer-group" class="text-autobot-primary" />
        <span class="citations-label">{{ $t('chat.citations.sources') }}</span>
        <span class="citations-count">{{ citations.length }}</span>
      </div>
      <Icon :name="isExpanded ? 'chevron-up' : 'chevron-down'" />
    </div>
    <Transition name="slide-fade">
      <div v-if="isExpanded" class="citations-list">
        <div
          v-for="(citation, idx) in citations"
          :key="citation.id || idx"
          class="citation-item"
          role="button"
          tabindex="0"
          @click="$emit('citation-click', citation)"
          @keydown.enter.prevent="$emit('citation-click', citation)"
          @keydown.space.prevent="$emit('citation-click', citation)"
        >
          <div class="citation-rank">
            <Icon :name="sourceIcon(citation)" />
          </div>
          <div class="citation-content">
            <div class="citation-text">
              <a
                v-if="citation.url && isSafeUrl(citation.url)"
                :href="citation.url"
                target="_blank"
                rel="noopener noreferrer"
                class="citation-link"
                @click.stop
              >{{ citationTitle(citation) }}</a>
              <span v-else>{{ citationTitle(citation) }}</span>
            </div>
            <div
              v-if="citation.type === 'knowledge_base' && citation.content"
              class="citation-excerpt"
            >
              {{ truncateContent(citation.content) }}
            </div>
            <div
              v-if="citation.type === 'llm_training' && citation.model"
              class="citation-excerpt"
            >
              {{ $t('chat.citations.model') }} {{ citation.model }}
            </div>
            <div v-if="stepDetails(citation).length" class="citation-excerpt">
              <div v-for="detail in stepDetails(citation)" :key="detail">{{ detail }}</div>
            </div>
            <div v-if="resultLinks(citation).length" class="citation-excerpt">
              {{ $t('chat.citations.resultLinks') }}
              <a
                v-for="link in resultLinks(citation)"
                :key="link"
                :href="link"
                target="_blank"
                rel="noopener noreferrer"
                class="citation-link"
                @click.stop
              >{{ link }}</a>
            </div>
            <div class="citation-meta">
              <span
                class="citation-reliability"
                :class="reliabilityClass(citation.reliability)"
              >
                {{ reliabilityLabel(citation.reliability) }}
              </span>
              <span
                v-if="citation.type === 'knowledge_base' && citation.score != null"
                class="citation-score"
                :class="getScoreClass(citation.score!)"
              >
                <Icon name="chart-line" />
                {{ formatScore(citation.score!) }}%
              </span>
              <span
                v-if="citation.type === 'knowledge_base' && citation.source"
                class="citation-source"
              >
                <Icon name="file-alt" />
                {{ formatSourcePath(citation.source) }}
              </span>
            </div>
          </div>
        </div>
        <div v-if="unproven.length || partial" class="citation-item" role="note">
          <div class="citation-content">
            <div v-if="unproven.length" class="citation-text">{{ $t('chat.citations.unprovenTitle') }} {{ unproven.join(', ') }}</div>
            <div v-if="unproven.length" class="citation-excerpt">{{ $t('chat.citations.unprovenHint') }}</div>
            <div v-if="partial" class="citation-excerpt">{{ $t('chat.citations.checkPartial') }}</div>
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
 * Issue #1186: Always-Visible Source Attribution — extended for type/reliability/web
 */

import type { IconName } from '@/components/ui/Icon.vue'
import Icon from '@/components/ui/Icon.vue'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

interface Citation {
  id?: string
  rank?: number
  content?: string
  score?: number
  source?: string
  // New fields (Issue #1186)
  type?: string // knowledge_base, llm_training, web_search, web_page, system_state, tool_output (#21976)
  reliability?: string
  title?: string
  model?: string
  url?: string
  step_id?: string
  /** A tool step's `tool`, redacted `args`, `origin` (host, exit code, page, result URLs) and times. */
  metadata?: Record<string, unknown>
}

interface Props {
  citations: Citation[]
  /** Quoted values found in no tool result of the turn (#21976). */
  unproven?: string[]
  /** The check read only part of a step's output (or could not read it): say so (#21976). */
  partial?: boolean
  maxLength?: number
  initiallyExpanded?: boolean
}

interface Emits {
  (e: 'citation-click', citation: Citation): void
  (e: 'expanded-change', expanded: boolean): void
}

const props = withDefaults(defineProps<Props>(), {
  maxLength: 200,
  unproven: () => [],
  partial: false,
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
  if (!sourcePath) return t('common.unknown')
  const parts = sourcePath.split('/')
  return parts[parts.length - 1] || sourcePath
}

const sourceIcon = (citation: Citation): IconName => {
  switch (citation.type) {
    case 'knowledge_base': return 'book'
    case 'llm_training':   return 'robot'
    case 'web':
    case 'web_page':
    case 'web_search':     return 'globe'
    default:               return 'file-alt'
  }
}

const reliabilityClass = (reliability: string | undefined): string => {
  switch (reliability) {
    case 'verified':
    case 'high':   return 'reliability-high'
    case 'medium': return 'reliability-medium'
    case 'low':    return 'reliability-low'
    default:       return 'reliability-medium'
  }
}

const reliabilityLabel = (reliability: string | undefined): string => {
  if (!reliability) return t('chat.citations.reliabilityMedium')
  const key = `chat.citations.reliability${reliability.charAt(0).toUpperCase() + reliability.slice(1)}`
  return t(key)
}

/** The lines that say how a tool step produced its result: tool, arguments, host, exit code (#21976). */
const stepDetails = (citation: Citation): string[] => {
  const meta = citation.metadata
  if (!meta?.tool) return []
  const origin = (meta.origin ?? {}) as Record<string, unknown>
  const args = meta.args && Object.keys(meta.args as object).length ? JSON.stringify(meta.args) : ''
  return [
    `${t('chat.citations.tool')} ${meta.tool}`,
    args && `${t('chat.citations.arguments')} ${args}`,
    origin.host && `${t('chat.citations.host')} ${origin.host}`,
    origin.return_code != null && `${t('chat.citations.exitCode')} ${origin.return_code}`,
  ].filter((line): line is string => typeof line === 'string' && line !== '')
}

/** The safe result URLs of a search step: all of them, none primary (#21976). */
const resultLinks = (citation: Citation): string[] => {
  const urls = (citation.metadata?.origin as { urls?: unknown } | undefined)?.urls
  return Array.isArray(urls) ? urls.filter((u): u is string => typeof u === 'string' && isSafeUrl(u)) : []
}

const isSafeUrl = (url: string): boolean => {
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'https:' || parsed.protocol === 'http:'
  } catch {
    return false
  }
}

const citationTitle = (citation: Citation): string => {
  if (citation.title) return citation.title
  if (citation.type === 'llm_training') return t('chat.citations.aiTrainingData')
  if (citation.type === 'web' || citation.type === 'web_page') return citation.url || t('chat.citations.webSource')
  return citation.source ? formatSourcePath(citation.source) : t('chat.citations.knowledgeBase')
}
</script>

<style scoped>
.knowledge-citations {
  margin-top: var(--spacing-3);
  border: 1px solid var(--color-primary-bg);
  border-radius: var(--radius-lg);
  background: var(--bg-card);
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

.citation-link {
  color: var(--color-primary-hover);
  text-decoration: underline;
  word-break: break-all;
}

.citation-link:hover {
  color: var(--color-primary);
}

.citation-excerpt {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  line-height: var(--leading-normal);
  margin-bottom: var(--spacing-1-5);
}

.citation-reliability {
  display: inline-flex;
  align-items: center;
  padding: 2px var(--spacing-1-5);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
}

.reliability-high {
  background: rgba(34, 197, 94, 0.15);
  color: var(--chart-green);
}

.reliability-medium {
  background: rgba(251, 191, 36, 0.15);
  color: var(--color-warning);
}

.reliability-low {
  background: rgba(239, 68, 68, 0.15);
  color: var(--color-error);
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
