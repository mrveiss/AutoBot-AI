<template>
  <!-- Issue #3232: Collapsible reasoning trace panel -->
  <div
    v-if="entries.length > 0 || isActive"
    class="reasoning-trace"
    :class="{ 'reasoning-trace--active': isActive }"
  >
    <!-- Header row with toggle -->
    <button
      class="reasoning-trace__header"
      :aria-expanded="expanded"
      :aria-label="$t('reasoningTrace.toggleLabel')"
      @click="expanded = !expanded"
    >
      <span class="reasoning-trace__icon" aria-hidden="true">
        <Icon name="circle-notch" class="animate-spin reasoning-trace__spin-icon" v-if="isActive" />
        <Icon name="brain" v-else />
      </span>
      <span class="reasoning-trace__title">{{ $t('reasoningTrace.title') }}</span>
      <span class="reasoning-trace__count">{{ entries.length }}</span>
      <i
        class="fas reasoning-trace__chevron"
        :class="expanded ? 'fa-chevron-up' : 'fa-chevron-down'"
        aria-hidden="true"
      ></i>
    </button>

    <!-- Collapsible body -->
    <transition name="trace-collapse">
      <div v-if="expanded" class="reasoning-trace__body" role="list">
        <div
          v-for="entry in entries"
          :key="entry.id"
          class="reasoning-trace__entry"
          :class="`reasoning-trace__entry--${entry.kind}`"
          role="listitem"
        >
          <span class="reasoning-trace__entry-icon" aria-hidden="true">
            <Icon :name="iconForKind(entry.kind)" />
          </span>
          <span class="reasoning-trace__entry-body">
            <span class="reasoning-trace__entry-label">{{ entry.label }}</span>
            <span
              v-if="entry.detail"
              class="reasoning-trace__entry-detail"
            >{{ entry.detail }}</span>
          </span>
          <span
            v-if="entry.durationMs != null"
            class="reasoning-trace__entry-duration"
          >{{ formatDuration(entry.durationMs) }}</span>
          <span
            v-if="entry.kind === 'tool_result'"
            class="reasoning-trace__entry-status"
            :class="entry.success ? 'reasoning-trace__entry-status--ok' : 'reasoning-trace__entry-status--error'"
            :aria-label="entry.success ? $t('reasoningTrace.success') : $t('reasoningTrace.error')"
          >
            <Icon :name="entry.success ? 'check' : 'times'" />
          </span>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import type { IconName } from '@/components/ui/Icon.vue'
import { ref } from 'vue'
import type { TraceEntry, TraceEntryKind } from '@/composables/useReasoningTrace'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface Props {
  entries: TraceEntry[]
  isActive?: boolean
}

withDefaults(defineProps<Props>(), {
  isActive: false,
})

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const expanded = ref(true)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function iconForKind(kind: TraceEntryKind): IconName {
  const map: Record<TraceEntryKind, IconName> = {
    step_start: 'play-circle',
    step_complete: 'check-circle',
    tool_call: 'wrench',
    tool_result: 'reply',
    llm_chunk: 'comment-dots',
    plan: 'list-ol',
  }
  return map[kind] ?? 'circle'
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}
import Icon from '@/components/ui/Icon.vue'
</script>

<style scoped>
.reasoning-trace {
  border: 1px solid var(--border-default, #334155);
  border-radius: var(--radius-lg);
  margin-bottom: var(--spacing-2);
  background: var(--color-bg-subtle, #0f172a);
  overflow: hidden;
  font-size: var(--text-xs);
}

.reasoning-trace--active {
  border-color: var(--color-electric-500, #6366f1);
}

/* Header */
.reasoning-trace__header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  width: 100%;
  padding: 0.4rem 0.75rem;
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-muted, #94a3b8);
  text-align: left;
  user-select: none;
}

.reasoning-trace__header:hover {
  color: var(--text-primary, #e2e8f0);
}

.reasoning-trace__icon {
  font-size: 0.85rem;
  color: var(--color-electric-400, #818cf8);
  width: 1rem;
  text-align: center;
}

.reasoning-trace__spin-icon {
  animation: fa-spin 1.2s linear infinite;
}

.reasoning-trace__title {
  flex: 1;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.reasoning-trace__count {
  font-size: 0.7rem;
  background: var(--border-default, #334155);
  border-radius: var(--radius-full);
  padding: 0 0.4rem;
  line-height: 1.4rem;
}

.reasoning-trace__chevron {
  font-size: 0.7rem;
  opacity: 0.6;
}

/* Body */
.reasoning-trace__body {
  border-top: 1px solid var(--border-default, #334155);
  max-height: 18rem;
  overflow-y: auto;
  padding: var(--spacing-1) var(--spacing-0);
}

/* Entries */
.reasoning-trace__entry {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-2);
  padding: 0.2rem 0.75rem;
  line-height: 1.5;
  border-left: 2px solid transparent;
}

.reasoning-trace__entry--step_start {
  border-left-color: var(--color-electric-400, #818cf8);
}

.reasoning-trace__entry--step_complete {
  border-left-color: var(--color-green-400, #4ade80);
}

.reasoning-trace__entry--tool_call {
  border-left-color: var(--color-yellow-400, #facc15);
}

.reasoning-trace__entry--tool_result {
  border-left-color: var(--color-blue-400, #60a5fa);
}

.reasoning-trace__entry--llm_chunk {
  border-left-color: var(--color-purple-400, #c084fc);
  font-family: monospace;
  white-space: pre-wrap;
  word-break: break-all;
}

.reasoning-trace__entry--plan {
  border-left-color: var(--color-orange-400, #fb923c);
}

.reasoning-trace__entry-icon {
  color: var(--text-muted, #94a3b8);
  width: 0.9rem;
  text-align: center;
  flex-shrink: 0;
  margin-top: 0.1rem;
}

.reasoning-trace__entry-body {
  flex: 1;
  min-width: 0;
}

.reasoning-trace__entry-label {
  color: var(--text-primary, #e2e8f0);
  overflow-wrap: anywhere;
}

.reasoning-trace__entry-detail {
  display: block;
  color: var(--text-muted, #94a3b8);
  font-size: 0.7rem;
  overflow-wrap: anywhere;
}

.reasoning-trace__entry-duration {
  color: var(--text-muted, #94a3b8);
  flex-shrink: 0;
  font-size: 0.7rem;
  margin-left: auto;
  padding-left: var(--spacing-1);
}

.reasoning-trace__entry-status {
  flex-shrink: 0;
  font-size: 0.7rem;
  padding-left: var(--spacing-1);
}

.reasoning-trace__entry-status--ok {
  color: var(--color-green-400, #4ade80);
}

.reasoning-trace__entry-status--error {
  color: var(--color-red-400, #f87171);
}

/* Collapse transition */
.trace-collapse-enter-active,
.trace-collapse-leave-active {
  transition: max-height var(--duration-200) var(--ease-out), opacity var(--duration-200) var(--ease-out);
  max-height: 18rem;
  overflow: hidden;
}

.trace-collapse-enter-from,
.trace-collapse-leave-to {
  max-height: 0;
  opacity: 0;
}
</style>
