<template>
  <div class="terminal-input-container">
    <div class="terminal-input-line">
      <span class="prompt" v-html="currentPrompt"></span>
      <input
        ref="terminalInput"
        v-model="currentInput"
        @keydown="handleKeydown"
        @keyup.enter="$emit('send-command')"
        class="terminal-input"
        data-testid="terminal-input"
        :disabled="!canInput"
        autocomplete="off"
        spellcheck="false"
        autofocus
      />
      <button
        class="send-button"
        data-testid="terminal-send"
        @click="$emit('send-command')"
        :disabled="!canInput"
        title="Send Command"
      >
        ⏎
      </button>
      <span class="cursor" :class="{ 'blink': showCursor }">█</span>
    </div>

    <div class="terminal-footer">
      <div class="footer-info">
        <span>Press Ctrl+C to interrupt, Ctrl+D to exit, Tab for completion</span>
      </div>
      <div class="footer-actions">
        <button
          class="footer-button workflow-test"
          @click="$emit('start-example-workflow')"
          title="Start Example Automated Workflow (for testing)"
          v-if="!hasAutomatedWorkflow"
        >
          🤖 Test Workflow
        </button>
        <button
          class="footer-button"
          @click="$emit('download-log')"
          title="Download Session Log"
        >
          💾 Save Log
        </button>
        <button
          class="footer-button"
          @click="$emit('share-session')"
          title="Share Session"
        >
          🔗 Share
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted, onUnmounted, computed, watch } from 'vue'

// Extend Window interface to include custom properties
declare global {
  interface Window {
    terminalFocusInterval?: number | null
  }
}

interface Props {
  currentInput: string
  currentPrompt: string
  canInput: boolean
  showCursor: boolean
  hasAutomatedWorkflow: boolean
  commandHistory: string[]
}

interface Emits {
  (e: 'update:current-input', value: string): void
  (e: 'send-command'): void
  (e: 'history-navigation', direction: 'up' | 'down', index: number): void
  (e: 'interrupt-signal'): void
  (e: 'exit-signal'): void
  (e: 'clear-terminal'): void
  (e: 'start-example-workflow'): void
  (e: 'download-log'): void
  (e: 'share-session'): void
  // Issue #756: Tab completion support
  (e: 'tab-completion', payload: { text: string, cursor: number }): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const terminalInput = ref<HTMLInputElement>()
const historyIndex = ref(-1)

// Update v-model
const currentInput = computed({
  get: () => props.currentInput,
  set: (value: string) => emit('update:current-input', value)
})

// Focus management
const focusInput = () => {
  if (terminalInput.value && props.canInput) {
    terminalInput.value.focus()
    nextTick(() => {
      if (terminalInput.value && document.activeElement !== terminalInput.value) {
        terminalInput.value.focus()
      }
    })
  }
}

// Keyboard handling
const handleKeydown = (event: KeyboardEvent) => {
  switch (event.key) {
    case 'ArrowUp':
      event.preventDefault()
      if (historyIndex.value > 0) {
        historyIndex.value--
        emit('history-navigation', 'up', historyIndex.value)
      }
      break

    case 'ArrowDown':
      event.preventDefault()
      if (historyIndex.value < props.commandHistory.length - 1) {
        historyIndex.value++
        emit('history-navigation', 'down', historyIndex.value)
      } else if (historyIndex.value === props.commandHistory.length - 1) {
        historyIndex.value = props.commandHistory.length
        currentInput.value = ''
      }
      break

    case 'Tab':
      event.preventDefault()
      // Issue #756: Emit tab completion request with current text and cursor position
      {
        const cursorPos = terminalInput.value?.selectionStart ?? currentInput.value.length
        emit('tab-completion', {
          text: currentInput.value,
          cursor: cursorPos
        })
      }
      break

    case 'c':
      if (event.ctrlKey) {
        event.preventDefault()
        emit('interrupt-signal')
      }
      break

    case 'd':
      if (event.ctrlKey && !currentInput.value) {
        event.preventDefault()
        emit('exit-signal')
      }
      break

    case 'l':
      if (event.ctrlKey) {
        event.preventDefault()
        emit('clear-terminal')
      }
      break
  }
}

// Reset history index when command history changes
watch(() => props.commandHistory.length, () => {
  historyIndex.value = props.commandHistory.length
})

// Focus management
onMounted(() => {
  focusInput()

  // Enhanced focus handling for automated testing
  document.addEventListener('click', handleDocumentClick)

  // Periodic focus check for automation scenarios
  const focusInterval = setInterval(() => {
    if (props.canInput && terminalInput.value &&
        document.activeElement !== terminalInput.value &&
        document.querySelector('.terminal-window-standalone')) {
      focusInput()
    }
  }, 1000)

  window.terminalFocusInterval = focusInterval
})

// Define document click handler function for proper cleanup
const handleDocumentClick = (event: MouseEvent) => {
  const terminalContainer = document.querySelector('.terminal-window-standalone')
  if (terminalContainer && terminalContainer.contains(event.target as Node) &&
      event.target !== terminalInput.value && props.canInput) {
    nextTick(() => focusInput())
  }
}

onUnmounted(() => {
  if (window.terminalFocusInterval) {
    clearInterval(window.terminalFocusInterval)
    window.terminalFocusInterval = null
  }

  // Clean up document event listener
  document.removeEventListener('click', handleDocumentClick)
})

// Expose methods for parent component
defineExpose({
  focusInput,
  terminalInput
})
</script>

<style scoped>
.terminal-input-container {
  display: flex;
  flex-direction: column;
}

/* Issue #704: Migrated to CSS design tokens */
.terminal-input-line {
  display: flex;
  align-items: center;
  padding: 0 var(--spacing-4) var(--spacing-4) var(--spacing-4);
  background-color: var(--terminal-bg);
}

.prompt {
  color: var(--terminal-green);
  margin-right: var(--spacing-2);
  flex-shrink: 0;
}

.terminal-input {
  background: none;
  border: none;
  color: var(--terminal-foreground);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  outline: none;
  flex: 1;
  min-width: 0;
}

.send-button {
  background: var(--terminal-green-bg);
  border: 1px solid var(--terminal-green-border);
  color: var(--terminal-green);
  padding: var(--spacing-1) var(--spacing-2);
  margin-left: var(--spacing-2);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--text-sm);
  transition: all var(--duration-200) var(--ease-in-out);
}

.send-button:hover:not(:disabled) {
  background: var(--terminal-green-bg-hover);
  border-color: var(--terminal-green-border-hover);
}

.send-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.cursor {
  color: var(--terminal-green);
  font-weight: var(--font-bold);
  margin-left: 2px;
}

.cursor.blink {
  animation: blink 1s infinite;
}

.terminal-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: var(--terminal-header-bg);
  padding: var(--spacing-1-5) var(--spacing-4);
  border-top: 1px solid var(--terminal-border);
  font-size: var(--text-xs);
}

.footer-info {
  color: var(--terminal-muted);
}

.footer-actions {
  display: flex;
  gap: var(--spacing-2);
}

.footer-button {
  background-color: var(--terminal-button-bg);
  border: 1px solid var(--terminal-button-border);
  color: var(--terminal-button-text);
  padding: 3px var(--spacing-2);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 10px;
  transition: background-color var(--duration-200) var(--ease-in-out);
}

.footer-button:hover {
  background-color: var(--terminal-button-bg-hover);
}

.footer-button.workflow-test {
  background-color: var(--color-info);
  border-color: var(--color-info-hover);
  color: var(--text-on-primary);
  font-weight: var(--font-semibold);
}

.footer-button.workflow-test:hover {
  background-color: var(--color-info-hover);
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

/* Responsive */
@media (max-width: 768px) {
  .terminal-input-line {
    padding: 0 12px 12px 12px;
  }

  .footer-info {
    display: none; /* Hide on mobile */
  }
}
</style>
