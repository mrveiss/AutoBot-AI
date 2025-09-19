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
      // TODO: Implement tab completion
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
const handleDocumentClick = (event) => {
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

.terminal-input-line {
  display: flex;
  align-items: center;
  padding: 0 16px 16px 16px;
  background-color: #000;
}

.prompt {
  color: #00ff00;
  margin-right: 8px;
  flex-shrink: 0;
}

.terminal-input {
  background: none;
  border: none;
  color: #fff;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 13px;
  outline: none;
  flex: 1;
  min-width: 0;
}

.send-button {
  background: rgba(0, 255, 0, 0.1);
  border: 1px solid rgba(0, 255, 0, 0.3);
  color: #00ff00;
  padding: 4px 8px;
  margin-left: 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.send-button:hover:not(:disabled) {
  background: rgba(0, 255, 0, 0.2);
  border-color: rgba(0, 255, 0, 0.5);
}

.send-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.cursor {
  color: #00ff00;
  font-weight: bold;
  margin-left: 2px;
}

.cursor.blink {
  animation: blink 1s infinite;
}

.terminal-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: #2d2d2d;
  padding: 6px 16px;
  border-top: 1px solid #333;
  font-size: 11px;
}

.footer-info {
  color: #888;
}

.footer-actions {
  display: flex;
  gap: 8px;
}

.footer-button {
  background-color: #444;
  border: 1px solid #666;
  color: #ccc;
  padding: 3px 8px;
  border-radius: 3px;
  cursor: pointer;
  font-size: 10px;
  transition: background-color 0.2s;
}

.footer-button:hover {
  background-color: #555;
}

.footer-button.workflow-test {
  background-color: #17a2b8;
  border-color: #138496;
  color: white;
  font-weight: 600;
}

.footer-button.workflow-test:hover {
  background-color: #138496;
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