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

// Emits
const emit = defineEmits<{
  ready: [terminal: Terminal]
  data: [data: string]
  resize: [cols: number, rows: number]
  disposed: []
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

    // Handle terminal data input
    terminal.value.onData((data) => {
      logger.debug('onData fired:', {
        data: data.replace(/\r/g, '\\r').replace(/\n/g, '\\n'),
        readOnly: props.readOnly,
        disableStdin: terminal.value?.options.disableStdin
      })

      if (!props.readOnly) {
        emit('data', data)
      } else {
      }
    })

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

// Expose methods for parent components
defineExpose({
  write,
  writeln,
  clear,
  reset,
  fit,
  focus,
  blur,
  getTerminal
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
