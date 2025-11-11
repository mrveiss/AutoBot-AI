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
      @keyup.enter="$event.target.click()"
      @keyup.space="$event.target.click()"
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
.terminal-output {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
  font-size: 13px;
  line-height: 1.4;
  white-space: pre-wrap;
  word-break: break-all;
  background-color: #000;
  color: #ffffff;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
}

.terminal-line {
  margin: 0;
  padding: 0;
  min-height: 1.4em;
}

.line-error {
  color: #ff6b6b;
}

.line-warning {
  color: #ffc107;
}

.line-success {
  color: #28a745;
}

.line-command {
  color: #87ceeb;
}

.line-system {
  color: #9370db;
}

.line-system_message {
  color: #9370db;
  font-weight: 500;
}

.line-automated_command {
  color: #17a2b8;
  font-weight: 500;
  background-color: rgba(23, 162, 184, 0.1);
  border-left: 3px solid #17a2b8;
  padding-left: 8px;
}

.line-manual_command {
  color: #28a745;
  font-weight: 500;
  background-color: rgba(40, 167, 69, 0.1);
  border-left: 3px solid #28a745;
  padding-left: 8px;
}

.line-workflow_info {
  color: #6f42c1;
  background-color: rgba(111, 66, 193, 0.1);
  border-left: 3px solid #6f42c1;
  padding-left: 8px;
  font-style: italic;
}

.line-command.high {
  border-left: 3px solid #ffc107;
  background-color: rgba(255, 193, 7, 0.1);
}

.line-command.critical {
  border-left: 3px solid #dc3545;
  background-color: rgba(220, 53, 69, 0.1);
}

/* Scrollbar styling */
.terminal-output::-webkit-scrollbar {
  width: 8px;
}

.terminal-output::-webkit-scrollbar-track {
  background: #1e1e1e;
}

.terminal-output::-webkit-scrollbar-thumb {
  background: #555;
  border-radius: 4px;
}

.terminal-output::-webkit-scrollbar-thumb:hover {
  background: #777;
}
</style>