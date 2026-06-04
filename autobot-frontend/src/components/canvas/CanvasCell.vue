<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss | Author: mrveiss -->
<template>
  <div
    data-testid="cell-root"
    :class="[
      'relative group rounded-md p-3 mb-2 transition-colors',
      isAgentCell
        ? 'border-l-2 bg-[var(--color-agent-draft-bg)] border-[var(--color-agent-draft-border)]'
        : 'border border-border-default bg-bg-card',
    ]"
    @click="onCellClick"
    @keydown.alt.enter.prevent="isAgentCell && cell.streamState === 'complete' ? $emit('accept') : undefined"
    @keydown.esc.prevent="isAgentCell && cell.streamState === 'complete' ? $emit('discard') : undefined"
    @keydown.enter.exact.prevent="isAgentCell && cell.streamState === 'complete' ? $emit('edit') : undefined"
    :tabindex="0"
    :aria-label="`${isAgentCell ? 'Agent' : 'User'} cell: ${cell.streamState}`"
  >
    <!-- Agent badge (color + icon shape) -->
    <span
      v-if="isAgentCell"
      data-testid="agent-badge"
      aria-label="Agent-authored cell"
      class="absolute top-2 right-2 text-xs select-none"
      role="img"
    >🤖</span>

    <!-- Contextual toolbar slot -->
    <slot name="toolbar" />

    <!-- Rich artifact rendering (Phase 2) -->
    <ChartCell
      v-if="chartPayload"
      :rich-payload="chartPayload.spec"
      data-testid="chart-cell"
    />
    <CodeCell
      v-else-if="codePayload"
      :rich-payload="codePayload"
      data-testid="code-cell"
    />

    <!-- Phase 2 placeholder for empty/null richPayload -->
    <div
      v-else-if="cell.contentType !== 'markdown'"
      data-testid="phase2-placeholder"
      class="text-text-secondary text-sm italic py-4 text-center"
    >
      Rich render pending (Phase 2)
    </div>

    <!-- Skeleton shimmer state -->
    <div
      v-else-if="cell.streamState === 'skeleton'"
      data-testid="cell-skeleton"
      :class="[
        'space-y-2',
        !prefersReducedMotion && 'animate-pulse',
      ]"
      aria-busy="true"
      aria-label="Loading…"
    >
      <div class="h-3 bg-bg-tertiary rounded w-3/4" />
      <div class="h-3 bg-bg-tertiary rounded w-1/2" />
      <div class="h-3 bg-bg-tertiary rounded w-5/6" />
    </div>

    <!-- Partial stream: content + blinking cursor -->
    <div v-else-if="cell.streamState === 'partial'">
      <!-- eslint-disable-next-line vue/no-v-html -->
      <div class="message-text prose prose-sm max-w-none" v-html="renderedContent" />
      <span
        data-testid="cell-cursor"
        class="inline-block w-0.5 h-4 bg-current animate-[blink_1s_step-end_infinite] ml-0.5"
        aria-hidden="true"
      />
      <p class="text-text-secondary text-xs mt-1" aria-live="polite">Writing…</p>
    </div>

    <!-- Error state content -->
    <div v-else-if="cell.streamState === 'error'">
      <!-- eslint-disable-next-line vue/no-v-html -->
      <div class="message-text prose prose-sm max-w-none opacity-60" v-html="renderedContent" />
      <p class="text-autobot-error text-xs mt-1">⚠ Stream error</p>
    </div>

    <!-- Complete markdown -->
    <div v-else>
      <!-- eslint-disable-next-line vue/no-v-html -->
      <div class="message-text prose prose-sm max-w-none" v-html="renderedContent" />
    </div>

    <!-- Streaming controls (partial) -->
    <div v-if="cell.streamState === 'partial' && isAgentCell" class="mt-2 flex gap-2">
      <button
        data-testid="btn-cancel-stream"
        aria-label="Cancel stream"
        class="px-2 py-1 text-xs rounded border border-border-default hover:bg-bg-hover"
        @click.stop="$emit('cancel')"
      >
        Cancel
      </button>
    </div>

    <!-- Complete agent controls -->
    <div
      v-if="cell.streamState === 'complete' && isAgentCell"
      data-testid="cell-controls"
      class="mt-2 flex gap-2 flex-wrap"
    >
      <button
        data-testid="btn-accept"
        aria-label="Accept agent cell (⌥Enter)"
        class="px-2 py-1 text-xs rounded bg-autobot-success text-white hover:opacity-90"
        @click.stop="$emit('accept')"
      >
        ✓ Accept
      </button>
      <button
        data-testid="btn-edit"
        aria-label="Edit agent cell (Enter)"
        class="px-2 py-1 text-xs rounded border border-border-default hover:bg-bg-hover"
        @click.stop="$emit('edit')"
      >
        ✎ Edit
      </button>
      <button
        data-testid="btn-discard"
        aria-label="Discard agent cell (Esc)"
        class="px-2 py-1 text-xs rounded border border-border-error text-error hover:bg-error-bg"
        @click.stop="$emit('discard')"
      >
        ✕ Discard
      </button>
    </div>

    <!-- Error controls -->
    <div v-if="cell.streamState === 'error' && isAgentCell" class="mt-2 flex gap-2">
      <button
        data-testid="btn-keep-error"
        aria-label="Keep cell on error"
        class="px-2 py-1 text-xs rounded border border-border-default hover:bg-bg-hover"
        @click.stop="$emit('keep')"
      >Keep</button>
      <button
        data-testid="btn-retry"
        aria-label="Retry stream"
        class="px-2 py-1 text-xs rounded border border-border-default hover:bg-bg-hover"
        @click.stop="$emit('retry')"
      >Retry</button>
      <button
        data-testid="btn-discard-error"
        aria-label="Discard errored cell"
        class="px-2 py-1 text-xs rounded border border-border-error text-error hover:bg-error-bg"
        @click.stop="$emit('discard')"
      >Discard</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { CanvasCell, ChartPayload, CodePayload } from '@/types/canvas'
import ChartCell from '@/components/artifact-cells/ChartCell.vue'
import CodeCell from './CodeCell.vue'

const props = defineProps<{ cell: CanvasCell }>()

const emit = defineEmits<{
  accept: []
  edit: []
  discard: []
  cancel: []
  keep: []
  retry: []
  'conflict-click': [cell: CanvasCell]
}>()

const isAgentCell = computed(() => props.cell.owner === 'agent')

const chartPayload = computed<ChartPayload | null>(() => {
  const p = props.cell.richPayload
  return p?.payloadType === 'vega-lite' ? (p as ChartPayload) : null
})

const codePayload = computed<CodePayload | null>(() => {
  const p = props.cell.richPayload
  return p?.payloadType === 'code' ? (p as CodePayload) : null
})

const prefersReducedMotion = typeof window !== 'undefined'
  ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
  : false

function formatMarkdown(text: string): string {
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/^#{1,6} (.+)$/gm, (_, t) => `<strong>${t}</strong>`)
    .replace(/\n/g, '<br>')
}

const renderedContent = computed(() => formatMarkdown(props.cell.content))

function onCellClick() {
  if (props.cell.streamState === 'partial' && props.cell.owner === 'agent') {
    emit('conflict-click', props.cell)
  }
}
</script>
