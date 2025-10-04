<template>
  <div class="base-xterm-container" ref="containerRef">
    <div ref="terminalRef" class="xterm-wrapper"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import '@xterm/xterm/css/xterm.css'

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
const terminal = ref<Terminal>()
const fitAddon = ref<FitAddon>()

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
    console.error('[BaseXTerminal] Terminal ref not available')
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
    terminal.value.loadAddon(fitAddon.value)
    terminal.value.loadAddon(new WebLinksAddon())

    // Open terminal in DOM
    terminal.value.open(terminalRef.value)

    // Fit terminal to container
    await nextTick()
    fitAddon.value.fit()

    // Handle terminal data input
    terminal.value.onData((data) => {
      if (!props.readOnly) {
        emit('data', data)
      }
    })

    // Handle terminal resize
    terminal.value.onResize(({ cols, rows }) => {
      emit('resize', cols, rows)
    })

    // Emit ready event
    emit('ready', terminal.value)

    console.log('[BaseXTerminal] Terminal initialized', {
      sessionId: props.sessionId,
      cols: terminal.value.cols,
      rows: terminal.value.rows
    })
  } catch (error) {
    console.error('[BaseXTerminal] Failed to initialize terminal:', error)
  }
}

// Cleanup terminal
const disposeTerminal = () => {
  if (terminal.value) {
    try {
      terminal.value.dispose()
      terminal.value = undefined
      fitAddon.value = undefined
      emit('disposed')
      console.log('[BaseXTerminal] Terminal disposed', { sessionId: props.sessionId })
    } catch (error) {
      console.error('[BaseXTerminal] Error disposing terminal:', error)
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
    terminal.value.options.disableStdin = readOnly
  }
})

// Handle window resize
const handleResize = () => {
  if (fitAddon.value) {
    fitAddon.value.fit()
  }
}

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
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  disposeTerminal()
})
</script>

<style scoped>
.base-xterm-container {
  width: 100%;
  height: 100%;
  overflow: hidden;
  background-color: #1a1b26;
}

.xterm-wrapper {
  width: 100%;
  height: 100%;
  padding: 8px;
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
