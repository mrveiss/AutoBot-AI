<template>
  <div class="base-xterm-container" ref="containerRef">
    <div ref="terminalRef" class="xterm-wrapper"></div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss

import { ref, shallowRef, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import '@xterm/xterm/css/xterm.css'
import { createLogger } from '../utils'

const logger = createLogger('BaseXTerminal')

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
  fontFamily: 'Monaco, Menlo, Ubuntu Mono, monospace',
})

const emit = defineEmits<{
  ready: [terminal: Terminal]
  data: [data: string]
  resize: [cols: number, rows: number]
  disposed: []
  tabCompletion: [payload: { text: string; cursor: number }]
  historyNavigate: [payload: { direction: 'up' | 'down'; lineBuffer: string }]
  reverseSearch: [payload: { active: boolean; query: string }]
  commandExecuted: [command: string]
}>()

const containerRef = ref<HTMLElement>()
const terminalRef = ref<HTMLElement>()
// CRITICAL: shallowRef prevents Vue proxy from intercepting xterm internals
const terminal = shallowRef<Terminal>()
const fitAddon = shallowRef<FitAddon>()
const webLinksAddon = shallowRef<WebLinksAddon>()
const addonsLoaded = ref(false)

const currentLineBuffer = ref('')
const cursorPosition = ref(0)
const reverseSearchMode = ref(false)
const reverseSearchQuery = ref('')

const themes = {
  dark: {
    background: '#1a1b26', foreground: '#a9b1d6', cursor: '#c0caf5', cursorAccent: '#1a1b26',
    selection: '#33467C', black: '#32344a', red: '#f7768e', green: '#9ece6a', yellow: '#e0af68',
    blue: '#7aa2f7', magenta: '#ad8ee6', cyan: '#449dab', white: '#787c99',
    brightBlack: '#444b6a', brightRed: '#ff7a93', brightGreen: '#b9f27c', brightYellow: '#ff9e64',
    brightBlue: '#7da6ff', brightMagenta: '#bb9af7', brightCyan: '#0db9d7', brightWhite: '#acb0d0',
  },
  light: {
    background: '#ffffff', foreground: '#3760bf', cursor: '#3760bf', cursorAccent: '#ffffff',
    selection: '#b4dcfe', black: '#000000', red: '#e82424', green: '#587539', yellow: '#8c6c3e',
    blue: '#2e7de9', magenta: '#9854f1', cyan: '#007197', white: '#6172b0',
    brightBlack: '#a1a6c5', brightRed: '#f52a65', brightGreen: '#587539', brightYellow: '#8c6c3e',
    brightBlue: '#2e7de9', brightMagenta: '#9854f1', brightCyan: '#007197', brightWhite: '#3760bf',
  },
}

const handleEnterKey = () => { currentLineBuffer.value = ''; cursorPosition.value = 0 }
const handleBackspace = () => {
  if (cursorPosition.value > 0) {
    currentLineBuffer.value = currentLineBuffer.value.slice(0, cursorPosition.value - 1) + currentLineBuffer.value.slice(cursorPosition.value)
    cursorPosition.value--
  }
}
const handleDeleteKey = () => {
  if (cursorPosition.value < currentLineBuffer.value.length) {
    currentLineBuffer.value = currentLineBuffer.value.slice(0, cursorPosition.value) + currentLineBuffer.value.slice(cursorPosition.value + 1)
  }
}
const handleArrowKeys = (seq: string) => {
  if (seq === 'D' && cursorPosition.value > 0) cursorPosition.value--
  else if (seq === 'C' && cursorPosition.value < currentLineBuffer.value.length) cursorPosition.value++
  else if (seq === 'H') cursorPosition.value = 0
  else if (seq === 'F') cursorPosition.value = currentLineBuffer.value.length
}
const handleCtrlW = () => {
  const before = currentLineBuffer.value.slice(0, cursorPosition.value)
  const after = currentLineBuffer.value.slice(cursorPosition.value)
  const match = before.match(/\S*\s*$/)
  if (match) {
    currentLineBuffer.value = before.slice(0, before.length - match[0].length) + after
    cursorPosition.value -= match[0].length
  }
}
const insertPrintableChar = (char: string) => {
  currentLineBuffer.value = currentLineBuffer.value.slice(0, cursorPosition.value) + char + currentLineBuffer.value.slice(cursorPosition.value)
  cursorPosition.value++
}
const updateLineBuffer = (data: string) => {
  if (data === '\r' || data === '\n') { handleEnterKey(); return }
  if (data === '\x7f' || data === '\b') { handleBackspace(); return }
  if (data === '\x1b[3~') { handleDeleteKey(); return }
  if (data.startsWith('\x1b[') && !data.includes('A') && !data.includes('B')) { handleArrowKeys(data.slice(2)); return }
  if (data === '\x03' || data === '\x04' || data === '\x15') { handleEnterKey(); return }
  if (data === '\x17') { handleCtrlW(); return }
  if (data.length === 1 && data.charCodeAt(0) >= 32) insertPrintableChar(data)
}

const handleTerminalData = (data: string) => {
  if (props.readOnly) return
  if (data === '\x12') {
    reverseSearchMode.value = !reverseSearchMode.value
    reverseSearchQuery.value = ''
    emit('reverseSearch', { active: reverseSearchMode.value, query: '' })
    return
  }
  if (reverseSearchMode.value) {
    if (data === '\x1b' || data === '\x03') { reverseSearchMode.value = false; emit('reverseSearch', { active: false, query: '' }); return }
    if (data === '\r' || data === '\n') { reverseSearchMode.value = false; emit('reverseSearch', { active: false, query: reverseSearchQuery.value }) }
    else if (data === '\x7f' || data === '\b') { reverseSearchQuery.value = reverseSearchQuery.value.slice(0, -1); emit('reverseSearch', { active: true, query: reverseSearchQuery.value }); return }
    else if (data.length === 1 && data.charCodeAt(0) >= 32) { reverseSearchQuery.value += data; emit('reverseSearch', { active: true, query: reverseSearchQuery.value }); return }
    return
  }
  if (data === '\x1b[A') { emit('historyNavigate', { direction: 'up', lineBuffer: currentLineBuffer.value }); return }
  if (data === '\x1b[B') { emit('historyNavigate', { direction: 'down', lineBuffer: currentLineBuffer.value }); return }
  if (data === '\t') { emit('tabCompletion', { text: currentLineBuffer.value, cursor: cursorPosition.value }); return }
  const command = (data === '\r' || data === '\n') ? currentLineBuffer.value.trim() : ''
  updateLineBuffer(data)
  if (command) emit('commandExecuted', command)
  emit('data', data)
}

const initTerminal = async () => {
  if (!terminalRef.value) { logger.error('Terminal ref not available'); return }
  try {
    terminal.value = new Terminal({
      cursorBlink: true, cursorStyle: 'block', fontSize: props.fontSize, fontFamily: props.fontFamily,
      theme: themes[props.theme], allowTransparency: false, scrollback: 10000, tabStopWidth: 4,
      convertEol: true, disableStdin: props.readOnly,
    })
    fitAddon.value = new FitAddon()
    webLinksAddon.value = new WebLinksAddon()
    terminal.value.loadAddon(fitAddon.value)
    terminal.value.loadAddon(webLinksAddon.value)
    addonsLoaded.value = true
    terminal.value.open(terminalRef.value)
    await nextTick()
    fitAddon.value.fit()
    terminal.value.onData(handleTerminalData)
    terminal.value.onResize(({ cols, rows }: { cols: number; rows: number }) => emit('resize', cols, rows))
    emit('ready', terminal.value)
    logger.debug('Terminal initialized', { sessionId: props.sessionId })
  } catch (error) {
    logger.error('Failed to initialize terminal:', error)
  }
}

const disposeTerminal = () => {
  if (terminal.value) {
    try {
      if (addonsLoaded.value) terminal.value.dispose()
      else logger.warn('Terminal addons not loaded, skipping full dispose')
    } catch (error) {
      logger.warn('Error disposing terminal:', error)
    } finally {
      terminal.value = undefined; fitAddon.value = undefined; webLinksAddon.value = undefined; addonsLoaded.value = false
      emit('disposed')
    }
  }
}

const write = (data: string) => terminal.value?.write(data)
const writeln = (data: string) => terminal.value?.writeln(data)
const clear = () => terminal.value?.clear()
const reset = () => { terminal.value?.reset(); currentLineBuffer.value = ''; cursorPosition.value = 0; reverseSearchMode.value = false; reverseSearchQuery.value = '' }
const fit = () => fitAddon.value?.fit()
const focus = () => terminal.value?.focus()
const blur = () => terminal.value?.blur()
const getTerminal = () => terminal.value
const getLineBuffer = () => ({ text: currentLineBuffer.value, cursor: cursorPosition.value })
const resetLineBuffer = () => { currentLineBuffer.value = ''; cursorPosition.value = 0 }
const setLineBuffer = (text: string, cursor?: number) => { currentLineBuffer.value = text; cursorPosition.value = cursor !== undefined ? cursor : text.length }
const applyCompletion = (prefix: string, completion: string) => {
  if (!terminal.value) return
  terminal.value.write('\x7f'.repeat(prefix.length) + completion)
  const lastSpace = currentLineBuffer.value.lastIndexOf(' ')
  currentLineBuffer.value = (lastSpace >= 0 ? currentLineBuffer.value.slice(0, lastSpace + 1) : '') + completion
  cursorPosition.value = currentLineBuffer.value.length
}
const showCompletions = (completions: string[]) => {
  if (!terminal.value || completions.length === 0) return
  terminal.value.write('\r\n' + completions.join('  ') + '\r\n')
}
const handleCompletionResponse = (data: { completions: string[]; prefix: string; common_prefix?: string }) => {
  const { completions, prefix, common_prefix: commonPrefix = '' } = data
  if (completions.length === 0) return
  if (completions.length === 1) applyCompletion(prefix, completions[0])
  else if (commonPrefix && commonPrefix.length > prefix.length) applyCompletion(prefix, commonPrefix)
  else showCompletions(completions)
}
const replaceLineWithHistoryCommand = (command: string) => {
  if (!terminal.value) return
  terminal.value.write('\x1b[D'.repeat(cursorPosition.value) + '\x1b[K' + command)
  currentLineBuffer.value = command; cursorPosition.value = command.length
}
const showReverseSearchPrompt = (query: string, match: string) => {
  if (!terminal.value) return
  terminal.value.write('\r\x1b[K' + `\r(reverse-i-search)\`${query}': ${match}`)
}
const exitReverseSearch = () => { reverseSearchMode.value = false; reverseSearchQuery.value = '' }

defineExpose({
  write, writeln, clear, reset, fit, focus, blur, getTerminal,
  getLineBuffer, resetLineBuffer, setLineBuffer, applyCompletion, showCompletions,
  handleCompletionResponse, replaceLineWithHistoryCommand, showReverseSearchPrompt, exitReverseSearch,
})

watch(() => props.theme, (t) => { if (terminal.value) terminal.value.options.theme = themes[t] })
watch(() => props.readOnly, (ro) => {
  if (terminal.value) {
    terminal.value.options.disableStdin = ro
    if (!ro) nextTick(() => terminal.value?.focus())
    else terminal.value.blur()
  }
})

const handleResize = () => { fitAddon.value?.fit() }
let visibilityObserver: IntersectionObserver | null = null

onMounted(async () => {
  await initTerminal()
  window.addEventListener('resize', handleResize)
  setTimeout(() => fitAddon.value?.fit(), 100)
  if (containerRef.value) {
    visibilityObserver = new IntersectionObserver((entries) => {
      entries.forEach((e) => { if (e.isIntersecting && e.intersectionRatio > 0) setTimeout(() => fitAddon.value?.fit(), 50) })
    }, { threshold: [0, 0.1] })
    visibilityObserver.observe(containerRef.value)
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (visibilityObserver) { visibilityObserver.disconnect(); visibilityObserver = null }
  disposeTerminal()
})
</script>

<style scoped>
.base-xterm-container { width: 100%; height: 100%; overflow: hidden; background-color: #1a1b26; }
.xterm-wrapper { width: 100%; height: 100%; padding: 8px; }
:deep(.xterm) { height: 100%; padding: 0; }
:deep(.xterm-viewport) { overflow-y: auto; }
:deep(.xterm-screen) { width: 100%; }
</style>
