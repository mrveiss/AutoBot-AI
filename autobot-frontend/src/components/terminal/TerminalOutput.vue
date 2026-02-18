<template>
  <div class="terminal-output-wrapper">
    <!-- Screen reader status announcements -->
    <div role="status" aria-live="polite" aria-atomic="true" class="sr-only">
      {{ screenReaderStatus }}
    </div>

    <div
      class="terminal-output"
      data-testid="terminal-output"
      ref="terminalOutput"
      role="log"
      aria-live="polite"
      aria-atomic="false"
      aria-relevant="additions"
      aria-label="Terminal command output"
      @click="$emit('focus-input')"
      tabindex="0"
      @keyup.enter="($event.target as HTMLElement)?.click()"
      @keyup.space="($event.target as HTMLElement)?.click()"
    >
      <div
        v-for="(line, index) in outputLines"
        :key="index"
        class="terminal-line"
        :class="getLineClass(line)"
        v-html="formatTerminalLine(line)"
      ></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'

interface OutputLine {
  content: string
  type?: string
  timestamp?: Date
  risk?: string
}

interface Props {
  outputLines: OutputLine[]
}

interface Emits {
  (e: 'focus-input'): void
}

const props = defineProps<Props>()
defineEmits<Emits>()

const terminalOutput = ref<HTMLElement>()

// Screen reader announcements
const screenReaderStatus = ref('')

// Auto-scroll when new lines are added
watch(() => props.outputLines.length, () => {
  nextTick(() => {
    if (terminalOutput.value) {
      terminalOutput.value.scrollTop = terminalOutput.value.scrollHeight
    }
  })
})

// Announce new terminal output to screen readers
watch(() => props.outputLines, (newLines, oldLines) => {
  // Only announce if a new line was added
  if (newLines.length > (oldLines?.length || 0)) {
    const latestLine = newLines[newLines.length - 1]
    if (latestLine) {
      // Strip HTML and ANSI codes for announcement
      const cleanContent = latestLine.content
        .replace(/\x1b\[[0-9;]*m/g, '')  // Remove ANSI codes
        .replace(/<[^>]*>/g, '')          // Remove HTML tags
        .substring(0, 150)                 // Limit to 150 chars

      const lineType = latestLine.type ? ` (${latestLine.type})` : ''
      screenReaderStatus.value = `New terminal output${lineType}: ${cleanContent}`

      // Clear announcement after 2 seconds
      setTimeout(() => {
        screenReaderStatus.value = ''
      }, 2000)
    }
  }
}, { deep: true })

// Format terminal line content
const formatTerminalLine = (line: OutputLine): string => {
  let content = line.content || ''

  // Comprehensive ANSI escape sequence handling
  content = content
    // Remove cursor positioning sequences
    .replace(/\x1b\[([0-9]+;[0-9]+)?[Hf]/g, '')
    // Remove cursor movement sequences
    .replace(/\x1b\[([0-9]+)?[ABCD]/g, '')
    // Remove cursor save/restore
    .replace(/\x1b\[(s|u)/g, '')
    // Remove erase sequences
    .replace(/\x1b\[([0-9]+)?[JK]/g, '')
    // Remove color/formatting sequences (SGR)
    .replace(/\x1b\[([0-9]{1,3}(;[0-9]{1,3})*)?m/g, '')
    // Remove private mode sequences (like bracketed paste)
    .replace(/\x1b\[\?[0-9]+[hl]/g, '')
    // Remove title/window sequences
    .replace(/\x1b\][0-9]+;.*?\x07/g, '')
    // Remove other CSI sequences
    .replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')
    // Clean up carriage returns and newlines
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '')
    // HTML escape for safety
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    // Clean up extra whitespace but preserve intentional spacing
    .replace(/\n+$/, '') // Remove trailing newlines

  return content
}

// Get CSS classes for terminal line
const getLineClass = (line: OutputLine): string[] => {
  const classes = ['terminal-line']

  if (line.type) {
    classes.push(`line-${line.type}`)
  }

  if (line.risk && (line.risk === 'high' || line.risk === 'critical')) {
    classes.push(line.risk)
  }

  return classes
}

// Expose ref for parent component
defineExpose({
  terminalOutput
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.terminal-output {
  flex: 1;
  padding: var(--spacing-4);
  overflow-y: auto;
  font-size: var(--text-sm);
  line-height: var(--leading-normal);
  white-space: pre-wrap;
  word-break: break-all;
  background-color: var(--terminal-bg);
  color: var(--terminal-foreground);
  font-family: var(--font-mono);
}

.terminal-line {
  margin: 0;
  padding: 0;
  min-height: 1.4em;
}

.line-error {
  color: var(--terminal-red);
}

.line-warning {
  color: var(--terminal-yellow);
}

.line-success {
  color: var(--terminal-green);
}

.line-command {
  color: var(--terminal-cyan);
}

.line-system {
  color: var(--terminal-magenta);
}

.line-system_message {
  color: var(--terminal-magenta);
  font-weight: var(--font-medium);
}

.line-automated_command {
  color: var(--color-info);
  font-weight: var(--font-medium);
  background-color: var(--color-info-bg-transparent);
  border-left: 3px solid var(--color-info);
  padding-left: var(--spacing-2);
}

.line-manual_command {
  color: var(--color-success);
  font-weight: var(--font-medium);
  background-color: var(--color-success-bg-transparent);
  border-left: 3px solid var(--color-success);
  padding-left: var(--spacing-2);
}

.line-workflow_info {
  color: var(--color-purple);
  background-color: var(--color-purple-bg-transparent);
  border-left: 3px solid var(--color-purple);
  padding-left: var(--spacing-2);
  font-style: italic;
}

.line-command.high {
  border-left: 3px solid var(--color-warning);
  background-color: var(--color-warning-bg-transparent);
}

.line-command.critical {
  border-left: 3px solid var(--color-error);
  background-color: var(--color-error-bg-transparent);
}

/* Scrollbar styling */
.terminal-output::-webkit-scrollbar {
  width: 8px;
}

.terminal-output::-webkit-scrollbar-track {
  background: var(--terminal-scrollbar-track);
}

.terminal-output::-webkit-scrollbar-thumb {
  background: var(--terminal-scrollbar-thumb);
  border-radius: var(--radius-sm);
}

.terminal-output::-webkit-scrollbar-thumb:hover {
  background: var(--terminal-scrollbar-thumb-hover);
}
</style>
