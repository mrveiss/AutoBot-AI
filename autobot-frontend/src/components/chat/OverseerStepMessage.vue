<template>
  <div class="overseer-step" :class="stepStatusClass">
    <!-- Step Header -->
    <div class="step-header">
      <div class="step-indicator">
        <span class="step-badge">Step {{ step.step_number }} of {{ step.total_steps }}</span>
        <span class="step-status" :class="step.status">
          <i :class="statusIcon" aria-hidden="true"></i>
          {{ statusText }}
        </span>
      </div>
      <span v-if="step.execution_time" class="step-time">
        <i class="fas fa-clock" aria-hidden="true"></i>
        {{ formatDuration(step.execution_time) }}
      </span>
    </div>

    <!-- Step Description -->
    <div class="step-description">
      <i class="fas fa-tasks" aria-hidden="true"></i>
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
          title="Copy command"
          aria-label="Copy command"
        >
          <i class="fas fa-copy" aria-hidden="true"></i>
        </button>
      </div>

      <!-- Part 1: Command Explanation (always visible) -->
      <div v-if="step.command_explanation" class="command-explanation">
        <div class="explanation-header">
          <i class="fas fa-info-circle" aria-hidden="true"></i>
          <span>What this command does:</span>
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
          <i class="fas fa-shield-alt" aria-hidden="true"></i>
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
        <span>Running...</span>
      </div>

      <!-- Output Content -->
      <div class="output-content">
        <div class="output-header">
          <i class="fas fa-terminal" aria-hidden="true"></i>
          <span>Output</span>
          <span v-if="step.return_code !== undefined" class="return-code" :class="{ error: step.return_code !== 0 }">
            Exit: {{ step.return_code }}
          </span>
        </div>
        <pre class="output-text">{{ step.output }}</pre>
      </div>

      <!-- Part 2: Output Explanation (always visible when complete) -->
      <div v-if="step.output_explanation && step.stream_complete" class="output-explanation">
        <div class="explanation-header">
          <i class="fas fa-chart-bar" aria-hidden="true"></i>
          <span>What we're looking at:</span>
        </div>
        <p class="explanation-summary">{{ step.output_explanation.summary }}</p>

        <!-- Key Findings -->
        <ul v-if="step.output_explanation.key_findings?.length" class="key-findings">
          <li v-for="(finding, idx) in step.output_explanation.key_findings" :key="idx">
            <i class="fas fa-check-circle" aria-hidden="true"></i>
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
            <i class="fas fa-arrow-right" aria-hidden="true"></i>
            <span>Suggested next steps:</span>
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
      <i class="fas fa-exclamation-triangle" aria-hidden="true"></i>
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

import { computed } from 'vue'
import { useClipboard } from '@/composables/useClipboard'
import type { OverseerStep } from '@/composables/useOverseerAgent'

const props = defineProps<{
  step: OverseerStep
}>()

const { copy } = useClipboard()

// Computed
const stepStatusClass = computed(() => ({
  pending: props.step.status === 'pending',
  running: props.step.status === 'running',
  streaming: props.step.status === 'streaming',
  explaining: props.step.status === 'explaining',
  completed: props.step.status === 'completed',
  failed: props.step.status === 'failed'
}))

const statusIcon = computed(() => {
  const icons: Record<string, string> = {
    pending: 'fas fa-clock',
    running: 'fas fa-spinner fa-spin',
    streaming: 'fas fa-stream',
    explaining: 'fas fa-brain',
    completed: 'fas fa-check-circle',
    failed: 'fas fa-times-circle'
  }
  return icons[props.step.status] || 'fas fa-question'
})

const statusText = computed(() => {
  const texts: Record<string, string> = {
    pending: 'Pending',
    running: 'Running',
    streaming: 'Streaming',
    explaining: 'Explaining',
    completed: 'Completed',
    failed: 'Failed'
  }
  return texts[props.step.status] || props.step.status
})

// Methods
const copyCommand = () => {
  if (props.step.command) {
    copy(props.step.command)
  }
}

const formatDuration = (seconds: number): string => {
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const mins = Math.floor(seconds / 60)
  const secs = Math.round(seconds % 60)
  return `${mins}m ${secs}s`
}
</script>

<style scoped>
.overseer-step {
  @apply bg-autobot-bg-secondary border border-autobot-border rounded-lg p-4 mb-4;
  transition: all 0.3s ease;
}

.overseer-step.running,
.overseer-step.streaming {
  @apply border-blue-500;
  box-shadow: 0 0 10px rgba(59, 130, 246, 0.3);
}

.overseer-step.completed {
  @apply border-green-600;
}

.overseer-step.failed {
  @apply border-red-600;
}

/* Step Header */
.step-header {
  @apply flex items-center justify-between mb-3 pb-2 border-b border-autobot-border;
}

.step-indicator {
  @apply flex items-center gap-3;
}

.step-badge {
  @apply bg-indigo-600 text-white text-xs font-semibold px-2 py-1 rounded;
}

.step-status {
  @apply flex items-center gap-1.5 text-sm;
}

.step-status.pending { @apply text-autobot-text-muted; }
.step-status.running { @apply text-blue-400; }
.step-status.streaming { @apply text-cyan-400; }
.step-status.explaining { @apply text-purple-400; }
.step-status.completed { @apply text-green-400; }
.step-status.failed { @apply text-red-400; }

.step-time {
  @apply text-autobot-text-muted text-xs flex items-center gap-1;
}

/* Step Description */
.step-description {
  @apply flex items-center gap-2 text-autobot-text-secondary mb-4;
}

.step-description i {
  @apply text-indigo-400;
}

/* Command Section */
.command-section {
  @apply mb-4;
}

.command-line {
  @apply flex items-center gap-2 bg-autobot-bg-primary rounded-t-lg px-3 py-2 border border-autobot-border;
}

.command-prompt {
  @apply text-green-400 font-mono font-bold;
}

.command-text {
  @apply flex-1 text-autobot-text-primary font-mono text-sm;
  word-break: break-all;
}

.copy-btn {
  @apply text-autobot-text-muted hover:text-autobot-text-secondary p-1 rounded transition-colors;
}

/* Command Explanation (Part 1) */
.command-explanation {
  @apply bg-indigo-900/30 border-l-4 border-indigo-500 px-4 py-3 rounded-b-lg;
}

.explanation-header {
  @apply flex items-center gap-2 text-indigo-300 font-semibold mb-2;
}

.explanation-summary {
  @apply text-autobot-text-secondary text-sm mb-3;
}

.command-breakdown {
  @apply space-y-1.5 mb-3;
}

.breakdown-item {
  @apply flex items-start gap-2 text-sm;
}

.breakdown-part {
  @apply bg-autobot-bg-secondary text-cyan-300 px-1.5 py-0.5 rounded font-mono text-xs whitespace-nowrap;
}

.breakdown-explanation {
  @apply text-autobot-text-muted;
}

.security-notes {
  @apply flex items-center gap-2 text-amber-400 text-sm bg-amber-900/30 px-3 py-2 rounded mt-2;
}

/* Output Section */
.output-section {
  @apply mt-4;
}

.streaming-indicator {
  @apply flex items-center gap-2 text-cyan-400 text-sm mb-2;
}

.streaming-dots {
  @apply flex gap-1;
}

.streaming-dots span {
  @apply w-1.5 h-1.5 bg-cyan-400 rounded-full animate-pulse;
}

.streaming-dots span:nth-child(2) { animation-delay: 0.2s; }
.streaming-dots span:nth-child(3) { animation-delay: 0.4s; }

.output-content {
  @apply bg-autobot-bg-primary border border-autobot-border rounded-lg overflow-hidden;
}

.output-header {
  @apply flex items-center gap-2 px-3 py-2 bg-autobot-bg-secondary border-b border-autobot-border;
}

.output-header i {
  @apply text-green-400;
}

.output-header span {
  @apply text-autobot-text-muted text-sm;
}

.return-code {
  @apply ml-auto text-xs px-2 py-0.5 rounded;
  @apply bg-green-900/50 text-green-400;
}

.return-code.error {
  @apply bg-red-900/50 text-red-400;
}

.output-text {
  @apply p-3 text-autobot-text-primary font-mono text-sm whitespace-pre-wrap overflow-x-auto max-h-96;
}

/* Output Explanation (Part 2) */
.output-explanation {
  @apply bg-teal-900/30 border-l-4 border-teal-500 px-4 py-3 rounded-lg mt-3;
}

.output-explanation .explanation-header {
  @apply text-teal-300;
}

.key-findings {
  @apply space-y-1.5 mb-3;
}

.key-findings li {
  @apply flex items-start gap-2 text-sm text-autobot-text-secondary;
}

.key-findings li i {
  @apply text-teal-400 mt-0.5;
}

.details-section {
  @apply text-autobot-text-muted text-sm mb-3;
}

.next-steps {
  @apply bg-teal-900/40 px-3 py-2 rounded;
}

.next-steps-header {
  @apply flex items-center gap-2 text-teal-300 text-sm font-semibold mb-1;
}

.next-steps ul {
  @apply list-disc list-inside text-sm text-autobot-text-muted ml-4;
}

/* Error Display */
.step-error {
  @apply flex items-center gap-2 text-red-400 bg-red-900/30 px-3 py-2 rounded mt-3;
}
</style>
