<template>
  <div class="base-xterm-container" ref="containerRef">
    <div ref="terminalRef" class="xterm-wrapper"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, shallowRef, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import '@xterm/xterm/css/xterm.css'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('BaseXTerminal')

// Props
interface Props {
  sessionId: string
  autoConnect?: boolean
  theme?: 'dark' | 'light'
  readOnly?: boolean
  fontSize?: number
  fontFamily?: string
}

const props = withDefaults(defineProps<Props>(), {
  autoConnect: true,
  theme: 'dark',
  readOnly: false,
  fontSize: 14,
  fontFamily: 'Monaco, Menlo, Ubuntu Mono, monospace'
})

// Emits - Issue #749: Added tabCompletion emit
const emit = defineEmits<{
  ready: [terminal: Terminal]
  data: [data: string]
  resize: [cols: number, rows: number]
  disposed: []
  tabCompletion: [payload: { text: string; cursor: number }]
}>()

// Refs
const containerRef = ref<HTMLElement>()
const terminalRef = ref<HTMLElement>()
// CRITICAL: Use shallowRef for xterm.js objects to prevent Vue's reactivity
// from proxying the internal state. Deep reactivity causes "Cannot read
// properties of undefined (reading 'dimensions')" errors when Vue's proxy
// intercepts xterm's internal property access.
const terminal = shallowRef<Terminal>()
const fitAddon = shallowRef<FitAddon>()
const webLinksAddon = shallowRef<WebLinksAddon>()
// Track whether addons have been successfully loaded to prevent dispose errors
const addonsLoaded = ref(false)

// Issue #749: State for tracking current line buffer for tab completion
const currentLineBuffer = ref('')
const cursorPosition = ref(0)

// Theme configurations
const themes = {
  dark: {
    background: '#1a1b26',
    foreground: '#a9b1d6',
    cursor: '#c0caf5',
    cursorAccent: '#1a1b26',
    selection: '#33467C',
    black: '#32344a',
    red: '#f7768e',
    green: '#9ece6a',
    yellow: '#e0af68',
    blue: '#7aa2f7',
    magenta: '#ad8ee6',
    cyan: '#449dab',
    white: '#787c99',
    brightBlack: '#444b6a',
    brightRed: '#ff7a93',
    brightGreen: '#b9f27c',
    brightYellow: '#ff9e64',
    brightBlue: '#7da6ff',
    brightMagenta: '#bb9af7',
    brightCyan: '#0db9d7',
    brightWhite: '#acb0d0'
  },
  light: {
    background: '#ffffff',
    foreground: '#3760bf',
    cursor: '#3760bf',
    cursorAccent: '#ffffff',
    selection: '#b4dcfe',
    black: '#000000',
    red: '#e82424',
    green: '#587539',
    yellow: '#8c6c3e',
    blue: '#2e7de9',
    magenta: '#9854f1',
    cyan: '#007197',
    white: '#6172b0',
    brightBlack: '#a1a6c5',
    brightRed: '#f52a65',
    brightGreen: '#587539',
    brightYellow: '#8c6c3e',
    brightBlue: '#2e7de9',
    brightMagenta: '#9854f1',
    brightCyan: '#007197',
    brightWhite: '#3760bf'
  }
}

// Issue #749: Handle data input and track line buffer for tab completion
const handleTerminalData = (data: string) => {
  logger.debug('onData fired:', {
    data: data.replace(/\r/g, '\\r').replace(/\n/g, '\\n'),
    readOnly: props.readOnly,
    disableStdin: terminal.value?.options.disableStdin
  })

  if (props.readOnly) {
    return
  }

  // Issue #749: Check for Tab key (character code 9)
  if (data === '\t') {
    logger.debug('[TAB] Tab key pressed, requesting completion')
    emit('tabCompletion', {
      text: currentLineBuffer.value,
      cursor: cursorPosition.value
    })
    return
  }

  // Issue #749: Track line buffer for tab completion
  updateLineBuffer(data)

  // Emit data for normal processing
  emit('data', data)
}

/**
 * Issue #749: Handle Enter key press - resets the line buffer.
 * Extracted from updateLineBuffer for readability.
 */
const handleEnterKey = (): void => {
  currentLineBuffer.value = ''
  cursorPosition.value = 0
}

/**
 * Issue #749: Handle Backspace key (character code 127 or \x7f).
 * Removes character before cursor position.
 * Extracted from updateLineBuffer for readability.
 */
const handleBackspace = (): void => {
  if (cursorPosition.value > 0) {
    const before = currentLineBuffer.value.slice(0, cursorPosition.value - 1)
    const after = currentLineBuffer.value.slice(cursorPosition.value)
    currentLineBuffer.value = before + after
    cursorPosition.value--
  }
}

/**
 * Issue #749: Handle Delete key (escape sequence \x1b[3~).
 * Removes character at cursor position.
 * Extracted from updateLineBuffer for readability.
 */
const handleDeleteKey = (): void => {
  if (cursorPosition.value < currentLineBuffer.value.length) {
    const before = currentLineBuffer.value.slice(0, cursorPosition.value)
    const after = currentLineBuffer.value.slice(cursorPosition.value + 1)
    currentLineBuffer.value = before + after
  }
}

/**
 * Issue #749: Handle arrow keys and Home/End navigation.
 * Updates cursor position based on the escape sequence.
 * Extracted from updateLineBuffer for readability.
 * @param sequence - The escape sequence suffix (e.g., 'D' for left arrow)
 */
const handleArrowKeys = (sequence: string): void => {
  switch (sequence) {
    case 'D': // Left arrow
      if (cursorPosition.value > 0) {
        cursorPosition.value--
      }
      break
    case 'C': // Right arrow
      if (cursorPosition.value < currentLineBuffer.value.length) {
        cursorPosition.value++
      }
      break
    case 'H': // Home
      cursorPosition.value = 0
      break
    case 'F': // End
      cursorPosition.value = currentLineBuffer.value.length
      break
  }
}

/**
 * Issue #749: Handle Ctrl+W - delete word backward.
 * Removes the word before the cursor position.
 * Extracted from updateLineBuffer for readability.
 */
const handleCtrlW = (): void => {
  const before = currentLineBuffer.value.slice(0, cursorPosition.value)
  const after = currentLineBuffer.value.slice(cursorPosition.value)
  const match = before.match(/\S*\s*$/)
  if (match) {
    const deleteLen = match[0].length
    currentLineBuffer.value = before.slice(0, before.length - deleteLen) + after
    cursorPosition.value -= deleteLen
  }
}

/**
 * Issue #749: Insert a printable character at the cursor position.
 * Extracted from updateLineBuffer for readability.
 * @param char - The character to insert
 */
const insertPrintableChar = (char: string): void => {
  const before = currentLineBuffer.value.slice(0, cursorPosition.value)
  const after = currentLineBuffer.value.slice(cursorPosition.value)
  currentLineBuffer.value = before + char + after
  cursorPosition.value++
}

/**
 * Issue #749: Update line buffer based on input character.
 * Dispatches to helper functions for specific key handling.
 * Refactored to comply with 50-line function limit per CLAUDE.md.
 */
const updateLineBuffer = (data: string): void => {
  // Handle Enter key - reset line buffer
  if (data === '\r' || data === '\n') {
    handleEnterKey()
    return
  }

  // Handle Backspace (character code 127 or \x7f)
  if (data === '\x7f' || data === '\b') {
    handleBackspace()
    return
  }

  // Handle Delete key (escape sequence)
  if (data === '\x1b[3~') {
    handleDeleteKey()
    return
  }

  // Handle arrow keys for cursor movement
  if (data.startsWith('\x1b[')) {
    handleArrowKeys(data.slice(2))
    return
  }

  // Handle Ctrl+C, Ctrl+D, Ctrl+U - reset line buffer
  if (data === '\x03' || data === '\x04' || data === '\x15') {
    handleEnterKey()
    return
  }

  // Handle Ctrl+W - delete word backward
  if (data === '\x17') {
    handleCtrlW()
    return
  }

  // Normal printable character - insert at cursor position
  if (data.length === 1 && data.charCodeAt(0) >= 32) {
    insertPrintableChar(data)
  }
}

// Issue #749: Apply completion to the terminal
const applyCompletion = (prefix: string, completion: string) => {
  if (!terminal.value) {
    return
  }

  // Calculate how much of the prefix is already typed
  // The completion should replace the partial word being typed
  const prefixLen = prefix.length

  // Calculate characters to remove (the prefix that was already typed)
  // We need to backspace over the existing prefix
  const backspaces = '\x7f'.repeat(prefixLen)

  // Write backspaces to remove the prefix, then write the completion
  terminal.value.write(backspaces + completion)

  // Update line buffer with the completion
  const lastSpaceIdx = currentLineBuffer.value.lastIndexOf(' ')
  const beforePrefix = lastSpaceIdx >= 0 ? currentLineBuffer.value.slice(0, lastSpaceIdx + 1) : ''
  currentLineBuffer.value = beforePrefix + completion
  cursorPosition.value = currentLineBuffer.value.length

  logger.debug('[TAB] Applied completion:', { prefix, completion, newBuffer: currentLineBuffer.value })
}

// Issue #749: Show multiple completions as terminal output
const showCompletions = (completions: string[]) => {
  if (!terminal.value || completions.length === 0) {
    return
  }

  // Write newline, then completions, then restore prompt and current input
  const completionText = '\r\n' + completions.join('  ') + '\r\n'
  terminal.value.write(completionText)

  logger.debug('[TAB] Displayed completions:', completions)
}

// Issue #749: Handle completion response from backend
const handleCompletionResponse = (data: { completions: string[]; prefix: string; common_prefix?: string }) => {
  const completions = data.completions || []
  const prefix = data.prefix || ''
  const commonPrefix = data.common_prefix || ''

  if (completions.length === 0) {
    // No completions - do nothing (could optionally beep)
    logger.debug('[TAB] No completions found')
    return
  }

  if (completions.length === 1) {
    // Single completion - apply it directly
    applyCompletion(prefix, completions[0])
  } else if (commonPrefix && commonPrefix.length > prefix.length) {
    // Multiple completions with common prefix longer than current input
    // Apply the common prefix
    applyCompletion(prefix, commonPrefix)
  } else {
    // Multiple completions with no additional common prefix
    // Show all options
    showCompletions(completions)
  }
}

// Initialize terminal
const initTerminal = async () => {
  if (!terminalRef.value) {
    logger.error('Terminal ref not available')
    return
  }

  try {
    // Create terminal instance
    terminal.value = new Terminal({
      cursorBlink: true,
      cursorStyle: 'block',
      fontSize: props.fontSize,
      fontFamily: props.fontFamily,
      theme: themes[props.theme],
      allowTransparency: false,
      scrollback: 10000,
      tabStopWidth: 4,
      convertEol: true,
      disableStdin: props.readOnly
    })

    // Load addons
    fitAddon.value = new FitAddon()
    webLinksAddon.value = new WebLinksAddon()
    terminal.value.loadAddon(fitAddon.value)
    terminal.value.loadAddon(webLinksAddon.value)
    // Mark addons as successfully loaded
    addonsLoaded.value = true

    // Open terminal in DOM
    terminal.value.open(terminalRef.value)

    // Fit terminal to container
    await nextTick()
    fitAddon.value.fit()

    // Issue #749: Handle terminal data input with tab completion support
    terminal.value.onData(handleTerminalData)

    // Handle terminal resize
    terminal.value.onResize(({ cols, rows }) => {
      emit('resize', cols, rows)
    })

    // Emit ready event
    emit('ready', terminal.value)

    logger.debug('Terminal initialized', {
      sessionId: props.sessionId,
      cols: terminal.value.cols,
      rows: terminal.value.rows
    })
  } catch (error) {
    logger.error('Failed to initialize terminal:', error)
  }
}

// Cleanup terminal
const disposeTerminal = () => {
  if (terminal.value) {
    try {
      // IMPORTANT: Only dispose if addons were successfully loaded.
      // xterm.js Terminal.dispose() internally disposes all loaded addons.
      // If addons weren't loaded (e.g., init failed early), calling dispose()
      // will throw "Could not dispose an addon that has not been loaded".
      //
      // We track addon loading state to prevent this error.
      if (addonsLoaded.value) {
        terminal.value.dispose()
      } else {
        // If addons weren't loaded, just detach from DOM without dispose
        logger.warn('Terminal addons not loaded, skipping full dispose')
      }

      // Clear all refs after disposal attempt
      terminal.value = undefined
      fitAddon.value = undefined
      webLinksAddon.value = undefined
      addonsLoaded.value = false

      emit('disposed')
      logger.debug('Terminal disposed successfully')
    } catch (error) {
      // Log as warning since this is often expected during rapid navigation
      logger.warn('Error disposing terminal (may be expected during navigation):', error)
      // Continue cleanup despite error - clear refs to prevent memory leaks
      terminal.value = undefined
      fitAddon.value = undefined
      webLinksAddon.value = undefined
      addonsLoaded.value = false
    }
  }
}

// Public methods exposed via defineExpose
const write = (data: string) => {
  if (terminal.value) {
    terminal.value.write(data)
  }
}

const writeln = (data: string) => {
  if (terminal.value) {
    terminal.value.writeln(data)
  }
}

const clear = () => {
  if (terminal.value) {
    terminal.value.clear()
  }
}

const reset = () => {
  if (terminal.value) {
    terminal.value.reset()
  }
  // Issue #749: Also reset line buffer state
  currentLineBuffer.value = ''
  cursorPosition.value = 0
}

const fit = () => {
  if (fitAddon.value) {
    fitAddon.value.fit()
  }
}

const focus = () => {
  if (terminal.value) {
    terminal.value.focus()
  }
}

const blur = () => {
  if (terminal.value) {
    terminal.value.blur()
  }
}

const getTerminal = () => terminal.value

// Issue #749: Get current line buffer (useful for debugging)
const getLineBuffer = () => ({
  text: currentLineBuffer.value,
  cursor: cursorPosition.value
})

// Issue #749: Reset line buffer (e.g., after command execution)
const resetLineBuffer = () => {
  currentLineBuffer.value = ''
  cursorPosition.value = 0
}

// Expose methods for parent components
defineExpose({
  write,
  writeln,
  clear,
  reset,
  fit,
  focus,
  blur,
  getTerminal,
  // Issue #749: Tab completion methods
  getLineBuffer,
  resetLineBuffer,
  applyCompletion,
  showCompletions,
  handleCompletionResponse
})

// Watch for theme changes
watch(() => props.theme, (newTheme) => {
  if (terminal.value) {
    terminal.value.options.theme = themes[newTheme]
  }
})

// Watch for readOnly changes
watch(() => props.readOnly, (readOnly) => {
  if (terminal.value) {

    // Update disableStdin option
    terminal.value.options.disableStdin = readOnly

    // When becoming writable, ensure focus
    if (!readOnly) {
      nextTick(() => {
        terminal.value?.focus()
      })
    } else {
      terminal.value.blur()
    }
  }
})

// Handle window resize
const handleResize = () => {
  if (fitAddon.value) {
    fitAddon.value.fit()
  }
}

// Visibility observer for tab switching
let visibilityObserver: IntersectionObserver | null = null

// Lifecycle
onMounted(async () => {
  await initTerminal()

  // Add resize listener
  window.addEventListener('resize', handleResize)

  // Initial fit after mount
  setTimeout(() => {
    if (fitAddon.value) {
      fitAddon.value.fit()
    }
  }, 100)

  // CRITICAL FIX: Detect when terminal becomes visible (e.g., tab switch)
  // and refit to proper container dimensions
  if (containerRef.value) {
    visibilityObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting && entry.intersectionRatio > 0) {
            // Container is now visible - refit terminal
            logger.debug('Container became visible - refitting terminal')
            setTimeout(() => {
              if (fitAddon.value) {
                fitAddon.value.fit()
                logger.debug('Terminal refitted:', {
                  cols: terminal.value?.cols,
                  rows: terminal.value?.rows
                })
              }
            }, 50)
          }
        })
      },
      {
        threshold: [0, 0.1] // Trigger when even 10% visible
      }
    )

    visibilityObserver.observe(containerRef.value)
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)

  // Disconnect visibility observer
  if (visibilityObserver) {
    visibilityObserver.disconnect()
    visibilityObserver = null
  }

  disposeTerminal()
})
</script>

<style scoped>
/**
 * Issue #704: CSS Design System - Using design tokens
 * Note: Terminal theme colors (lines 58-104) use hardcoded hex values intentionally
 * because xterm.js theme config requires literal color values, not CSS variables.
 * The Tokyo Night color scheme is a standard terminal palette.
 */

.base-xterm-container {
  width: 100%;
  height: 100%;
  overflow: hidden;
  background-color: var(--terminal-bg, #1a1b26);
}

.xterm-wrapper {
  width: 100%;
  height: 100%;
  padding: var(--spacing-2, 8px);
}

/* Ensure xterm.js styles are properly scoped */
:deep(.xterm) {
  height: 100%;
  padding: 0;
}

:deep(.xterm-viewport) {
  overflow-y: auto;
}

:deep(.xterm-screen) {
  width: 100%;
}
</style>
