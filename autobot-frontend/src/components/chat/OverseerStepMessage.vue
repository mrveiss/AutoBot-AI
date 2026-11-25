<template>
  <div class="overseer-step" :class="stepStatusClass">
    <!-- Step Header -->
    <div class="step-header">
      <div class="step-indicator">
        <span class="step-badge">{{ $t('chat.overseer.stepOf', { current: step.step_number, total: step.total_steps }) }}</span>
        <span class="step-status" :class="step.status">
          <Icon :name="statusIcon" />
          {{ statusText }}
        </span>
      </div>
      <span v-if="step.execution_time" class="step-time">
        <Icon name="clock" />
        {{ formatDuration(step.execution_time, { style: 'secondsCompact' }) }}
      </span>
    </div>

    <!-- Step Description -->
    <div class="step-description">
      <Icon name="tasks" />
      {{ step.description }}
    </div>

    <!-- Command Section -->
    <div v-if="step.command" class="command-section">
      <!-- Command Line -->
      <div class="command-line">
        <span class="command-prompt">$</span>
        <code class="command-text">{{ step.command }}</code>
        <button
          class="copy-btn"
          @click="copyCommand"
          :title="$t('chat.overseer.copyCommand')"
          :aria-label="$t('chat.overseer.copyCommand')"
        >
          <Icon name="copy" />
        </button>
      </div>

      <!-- Part 1: Command Explanation (always visible) -->
      <div v-if="step.command_explanation" class="command-explanation">
        <div class="explanation-header">
          <Icon name="info-circle" />
          <span>{{ $t('chat.overseer.whatCommandDoes') }}</span>
        </div>
        <p class="explanation-summary">{{ step.command_explanation.summary }}</p>

        <!-- Command Breakdown -->
        <div v-if="step.command_explanation.breakdown?.length" class="command-breakdown">
          <div
            v-for="(part, idx) in step.command_explanation.breakdown"
            :key="idx"
            class="breakdown-item"
          >
            <code class="breakdown-part">{{ part.part }}</code>
            <span class="breakdown-explanation">{{ part.explanation }}</span>
          </div>
        </div>

        <!-- Security Notes -->
        <div v-if="step.command_explanation.security_notes" class="security-notes">
          <Icon name="shield-alt" />
          <span>{{ step.command_explanation.security_notes }}</span>
        </div>
      </div>
    </div>

    <!-- Output Section -->
    <div v-if="step.output || step.is_streaming" class="output-section">
      <!-- Streaming Indicator -->
      <div v-if="step.is_streaming && !step.stream_complete" class="streaming-indicator">
        <div class="streaming-dots">
          <span></span>
          <span></span>
          <span></span>
        </div>
        <span>{{ $t('chat.overseer.running') }}</span>
      </div>

      <!-- Output Content -->
      <div class="output-content">
        <div class="output-header">
          <Icon name="terminal" />
          <span>{{ $t('chat.overseer.output') }}</span>
          <span v-if="step.return_code !== undefined" class="return-code" :class="{ error: step.return_code !== 0 }">
            {{ $t('chat.overseer.exitCode', { code: step.return_code }) }}
          </span>
        </div>
        <pre class="output-text">{{ step.output }}</pre>
      </div>

      <!-- Part 2: Output Explanation (always visible when complete) -->
      <div v-if="step.output_explanation && step.stream_complete" class="output-explanation">
        <div class="explanation-header">
          <Icon name="chart-bar" />
          <span>{{ $t('chat.overseer.whatLookingAt') }}</span>
        </div>
        <p class="explanation-summary">{{ step.output_explanation.summary }}</p>

        <!-- Key Findings -->
        <ul v-if="step.output_explanation.key_findings?.length" class="key-findings">
          <li v-for="(finding, idx) in step.output_explanation.key_findings" :key="idx">
            <Icon name="check-circle" />
            {{ finding }}
          </li>
        </ul>

        <!-- Detailed Explanation -->
        <div v-if="step.output_explanation.details" class="details-section">
          <p>{{ step.output_explanation.details }}</p>
        </div>

        <!-- Next Steps -->
        <div v-if="step.output_explanation.next_steps?.length" class="next-steps">
          <div class="next-steps-header">
            <Icon name="arrow-right" />
            <span>{{ $t('chat.overseer.suggestedNextSteps') }}</span>
          </div>
          <ul>
            <li v-for="(nextStep, idx) in step.output_explanation.next_steps" :key="idx">
              {{ nextStep }}
            </li>
          </ul>
        </div>
      </div>
    </div>

    <!-- Error Display -->
    <div v-if="step.error" class="step-error">
      <Icon name="exclamation-triangle" />
      <span>{{ step.error }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * OverseerStepMessage Component
 *
 * Displays a single step from the Overseer Agent with:
 * - Step progress indicator
 * - Command with Part 1 explanation (what it does)
 * - Streaming output for long-running commands
 * - Output with Part 2 explanation (what we're looking at)
 *
 * @author mrveiss
 * @copyright 2025 mrveiss
 */

import type { IconName } from '@/components/ui/Icon.vue'
import { formatDuration } from '@/utils/formatHelpers'
import Icon from '@/components/ui/Icon.vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useClipboard } from '@/composables/useClipboard'
import type { OverseerStep } from '@/composables/useOverseerAgent'
import type { OverseerStepStatus } from '@/types/_generated/workflow'

const props = defineProps<{
  step: OverseerStep
}>()

const { t } = useI18n()
const { copy } = useClipboard()

// Computed
// Record<OverseerStepStatus, boolean>: the compiler flags a status the backend adds next (#19623)
const stepStatusClass = computed<Record<OverseerStepStatus, boolean>>(() => ({
  pending: props.step.status === 'pending',
  running: props.step.status === 'running',
  streaming: props.step.status === 'streaming',
  waiting_explanation: props.step.status === 'waiting_explanation',
  explaining: props.step.status === 'explaining',
  completed: props.step.status === 'completed',
  failed: props.step.status === 'failed'
}))

const statusIcon = computed(() => {
  const icons: Record<string, IconName> = {
    pending: 'clock',
    // #9724: was an FA class string, which <Icon> rendered as an empty SVG
    running: 'spinner',
    streaming: 'stream',
    waiting_explanation: 'clock',
    explaining: 'brain',
    completed: 'check-circle',
    failed: 'times-circle'
  }
  return icons[props.step.status] || 'question'
})

const statusText = computed(() => {
  const key = `chat.overseer.status.${props.step.status}`
  return t(key)
})

// Methods
const copyCommand = () => {
  if (props.step.command) {
    copy(props.step.command)
  }
}

</script>

<style scoped>
/* Mockup: a step is a card; terminal output is a sunken mono region. Every tint derives
   from one accent per section, so no per-section colour is repeated. */
.overseer-step {
  --step-accent: var(--aui-color-info);
  margin-block-end: var(--aui-space-4);
  padding: var(--aui-space-4);
  border: 1px solid var(--aui-color-border);
  border-radius: var(--aui-radius-lg);
  background: var(--aui-color-surface-raised);
}
.overseer-step.running,
.overseer-step.streaming { border-color: var(--aui-color-info); box-shadow: 0 0 0 1px var(--aui-color-info); }
.overseer-step.completed { border-color: color-mix(in srgb, var(--aui-color-success) 50%, transparent); }
.overseer-step.failed { border-color: color-mix(in srgb, var(--aui-color-error) 50%, transparent); }

.step-header { display: flex; align-items: center; justify-content: space-between; margin-block-end: var(--aui-space-3); padding-block-end: var(--aui-space-2); border-block-end: 1px solid var(--aui-color-border); }
.step-indicator { display: flex; align-items: center; gap: var(--aui-space-3); }
.step-badge { padding: var(--aui-space-1) var(--aui-space-2); border-radius: var(--aui-radius-sm); background: color-mix(in srgb, var(--aui-color-primary) 15%, transparent); color: var(--aui-color-primary); font-size: var(--aui-text-xs); font-weight: var(--aui-font-weight-semibold); }
.step-status { display: flex; align-items: center; gap: var(--aui-space-1); font-size: var(--aui-text-sm); }
.step-status.pending { color: var(--aui-color-text-muted); }
.step-status.running,
.step-status.streaming,
.step-status.explaining { color: var(--aui-color-info); }
.step-status.waiting_explanation { color: var(--aui-color-warning); }
.step-status.completed { color: var(--aui-color-success); }
.step-status.failed { color: var(--aui-color-error); }
.step-time { display: flex; align-items: center; gap: var(--aui-space-1); color: var(--aui-color-text-muted); font-size: var(--aui-text-xs); }
.step-description { display: flex; align-items: center; gap: var(--aui-space-2); margin-block-end: var(--aui-space-4); color: var(--aui-color-text-muted); }
.step-description :deep(svg) { color: var(--aui-color-primary); }

.command-section,
.output-section { margin-block-end: var(--aui-space-4); }
.command-line { display: flex; align-items: center; gap: var(--aui-space-2); padding: var(--aui-space-2) var(--aui-space-3); border: 1px solid var(--aui-color-border); border-radius: var(--aui-radius-lg) var(--aui-radius-lg) 0 0; background: var(--aui-color-surface-sunken); }
.command-prompt { color: var(--aui-color-success); font-family: var(--aui-font-mono); font-weight: var(--aui-font-weight-semibold); }
.command-text { flex: 1; font-family: var(--aui-font-mono); font-size: var(--aui-text-sm); }
.copy-btn { padding: var(--aui-space-1); border: 0; border-radius: var(--aui-radius-sm); background: transparent; color: var(--aui-color-text-muted); cursor: pointer; }
.copy-btn:hover { color: var(--aui-color-text); }
.copy-btn:focus-visible { outline: var(--aui-focus-ring-width) solid var(--aui-color-focus-ring); }

.command-explanation,
.output-explanation { padding: var(--aui-space-3) var(--aui-space-4); border-inline-start: 4px solid var(--step-accent); background: color-mix(in srgb, var(--step-accent) 10%, transparent); }
.command-explanation { border-radius: 0 0 var(--aui-radius-lg) var(--aui-radius-lg); }
.output-explanation { --step-accent: var(--aui-color-success); margin-block-start: var(--aui-space-3); border-radius: var(--aui-radius-lg); }
.explanation-header { display: flex; align-items: center; gap: var(--aui-space-2); margin-block-end: var(--aui-space-2); color: var(--step-accent); font-weight: var(--aui-font-weight-semibold); }
.explanation-summary { margin-block-end: var(--aui-space-3); color: var(--aui-color-text-muted); font-size: var(--aui-text-sm); }
.command-breakdown,
.key-findings { display: flex; flex-direction: column; gap: var(--aui-space-2); margin-block-end: var(--aui-space-3); }
.breakdown-item,
.key-findings li { display: flex; align-items: flex-start; gap: var(--aui-space-2); font-size: var(--aui-text-sm); }
.breakdown-part { padding: 0 var(--aui-space-2); border-radius: var(--aui-radius-sm); background: var(--aui-color-surface-sunken); font-family: var(--aui-font-mono); font-size: var(--aui-text-xs); white-space: nowrap; }
.breakdown-explanation,
.details-section { color: var(--aui-color-text-muted); }
.key-findings :deep(svg) { color: var(--aui-color-success); }
.security-notes,
.step-error { display: flex; align-items: center; gap: var(--aui-space-2); margin-block-start: var(--aui-space-2); padding: var(--aui-space-2) var(--aui-space-3); border-radius: var(--aui-radius-md); font-size: var(--aui-text-sm); }
.security-notes { background: color-mix(in srgb, var(--aui-color-warning) 12%, transparent); color: var(--aui-color-warning); }
.step-error { margin-block-start: var(--aui-space-3); background: color-mix(in srgb, var(--aui-color-error) 12%, transparent); color: var(--aui-color-error); }
.next-steps { margin-block-start: var(--aui-space-3); }
.next-steps-header { display: flex; align-items: center; gap: var(--aui-space-2); color: var(--aui-color-info); font-size: var(--aui-text-sm); }
.next-steps ul { margin-inline-start: var(--aui-space-4); color: var(--aui-color-text-muted); font-size: var(--aui-text-sm); list-style: disc inside; }

.streaming-indicator { display: flex; align-items: center; gap: var(--aui-space-2); margin-block-end: var(--aui-space-2); color: var(--aui-color-info); font-size: var(--aui-text-sm); }
.streaming-dots { display: flex; gap: var(--aui-space-1); }
.streaming-dots span { inline-size: var(--aui-space-2); block-size: var(--aui-space-2); border-radius: var(--aui-radius-full); background: var(--aui-color-info); animation: step-pulse 1.2s ease-in-out infinite; }
.streaming-dots span:nth-child(2) { animation-delay: 0.2s; }
.streaming-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes step-pulse { 50% { opacity: 0.3; } }
@media (prefers-reduced-motion: reduce) { .streaming-dots span { animation: none; } }

.output-content { overflow: hidden; border: 1px solid var(--aui-color-border); border-radius: var(--aui-radius-lg); background: var(--aui-color-surface-sunken); }
.output-header { display: flex; align-items: center; gap: var(--aui-space-2); padding: var(--aui-space-2) var(--aui-space-3); border-block-end: 1px solid var(--aui-color-border); background: var(--aui-color-surface-raised); }
.output-header :deep(svg) { color: var(--aui-color-success); }
.return-code { margin-inline-start: auto; padding: 0 var(--aui-space-2); border-radius: var(--aui-radius-sm); background: color-mix(in srgb, var(--aui-color-success) 15%, transparent); color: var(--aui-color-success); font-size: var(--aui-text-xs); }
.return-code.error { background: color-mix(in srgb, var(--aui-color-error) 15%, transparent); color: var(--aui-color-error); }
.output-text { max-block-size: 24rem; margin: 0; padding: var(--aui-space-3); overflow: auto; font-family: var(--aui-font-mono); font-size: var(--aui-text-sm); white-space: pre-wrap; }
</style>
