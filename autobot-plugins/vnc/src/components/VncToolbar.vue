<template>
  <div v-if="connected" class="vnc-toolbar">
    <span class="vnc-toolbar-label">Desktop Actions</span>
    <div class="vnc-toolbar-actions">
      <button @click="handleScreenshot" :disabled="controls.loading.value" class="vnc-btn" title="Take Screenshot">
        📷 Screenshot
      </button>
      <button @click="showTypeDialog = true" class="vnc-btn" title="Type Text">
        ⌨ Type Text
      </button>
      <button @click="handleCtrlAltDel" :disabled="controls.loading.value" class="vnc-btn" title="Send Ctrl+Alt+Del">
        Ctrl+Alt+Del
      </button>
      <button @click="handlePaste" :disabled="controls.loading.value" class="vnc-btn" title="Paste Clipboard">
        📋 Paste
      </button>
      <button @click="handleFullscreen" class="vnc-btn" title="Toggle Fullscreen">
        {{ isFullscreen ? '⊡' : '⛶' }} Fullscreen
      </button>
    </div>

    <!-- Error feedback -->
    <p v-if="lastError" class="vnc-toolbar-error">{{ lastError }}</p>

    <!-- Type text dialog -->
    <Teleport to="body">
      <div v-if="showTypeDialog" class="vnc-dialog-backdrop" @click.self="showTypeDialog = false">
        <div class="vnc-dialog">
          <div class="vnc-dialog-header">
            <span>Type Text on Desktop</span>
            <button @click="showTypeDialog = false" class="vnc-dialog-close">×</button>
          </div>
          <div class="vnc-dialog-body">
            <textarea
              v-model="textToType"
              placeholder="Enter text to type on the desktop..."
              rows="4"
              class="vnc-dialog-textarea"
            ></textarea>
          </div>
          <div class="vnc-dialog-footer">
            <button @click="handleTypeText" :disabled="!textToType.trim()" class="vnc-btn-primary">Type</button>
            <button @click="showTypeDialog = false" class="vnc-btn-secondary">Cancel</button>
          </div>
        </div>
      </div>

      <!-- Screenshot modal -->
      <div v-if="screenshotData" class="vnc-dialog-backdrop" @click.self="screenshotData = null">
        <div class="vnc-screenshot-modal">
          <div class="vnc-dialog-header">
            <span>Desktop Screenshot</span>
            <button @click="screenshotData = null" class="vnc-dialog-close">×</button>
          </div>
          <div class="vnc-screenshot-body">
            <img :src="screenshotData" alt="Desktop Screenshot" class="vnc-screenshot-img" />
          </div>
          <div class="vnc-dialog-footer">
            <button @click="downloadScreenshot" class="vnc-btn-primary">Download</button>
            <button @click="screenshotData = null" class="vnc-btn-secondary">Close</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss

import { ref, onMounted, onUnmounted } from 'vue'
import { useVncControls } from '../composables/useVncControls'
import { createLogger } from '../utils'

const logger = createLogger('VncToolbar')

const props = defineProps<{
  /** Whether VNC is currently connected */
  connected: boolean
  /** Base URL for VNC API calls — defaults to /api */
  apiBaseUrl?: string
  /** iframe element id to fullscreen */
  frameId?: string
}>()

const emit = defineEmits<{
  error: [message: string]
}>()

const controls = useVncControls(props.apiBaseUrl ?? '/api')
const lastError = ref<string | null>(null)
const isFullscreen = ref(false)
const showTypeDialog = ref(false)
const textToType = ref('')
const screenshotData = ref<string | null>(null)

const setError = (msg: string | null) => { lastError.value = msg; if (msg) emit('error', msg) }

async function handleScreenshot() {
  setError(null)
  const result = await controls.captureScreenshot()
  if (result.status === 'success' && result.image_data) {
    screenshotData.value = `data:image/png;base64,${result.image_data}`
  } else {
    logger.error('Screenshot failed:', result.message)
    setError(result.message)
  }
}

async function handleTypeText() {
  if (!textToType.value.trim()) return
  const result = await controls.keyboardType(textToType.value)
  if (result.status === 'success') { textToType.value = ''; showTypeDialog.value = false }
  else { logger.error('Type text failed:', result.message); setError(result.message) }
}

async function handleCtrlAltDel() {
  const result = await controls.sendCtrlAltDel()
  if (result.status !== 'success') { logger.error('Ctrl+Alt+Del failed:', result.message); setError(result.message) }
}

async function handlePaste() {
  try {
    const text = await navigator.clipboard.readText()
    const result = await controls.syncClipboard(text)
    if (result.status !== 'success') { logger.error('Clipboard sync failed:', result.message); setError(result.message) }
  } catch (err) {
    logger.error('Clipboard read failed:', err)
    setError('Failed to read clipboard')
  }
}

function handleFullscreen() {
  const frame = document.getElementById(props.frameId ?? 'vnc-frame')
  if (!frame) return
  if (!document.fullscreenElement) { frame.requestFullscreen(); isFullscreen.value = true }
  else { document.exitFullscreen(); isFullscreen.value = false }
}

function downloadScreenshot() {
  if (!screenshotData.value) return
  const a = document.createElement('a')
  a.href = screenshotData.value
  a.download = `desktop-screenshot-${Date.now()}.png`
  a.click()
}

function handleFullscreenChange() { isFullscreen.value = !!document.fullscreenElement }

onMounted(() => document.addEventListener('fullscreenchange', handleFullscreenChange))
onUnmounted(() => document.removeEventListener('fullscreenchange', handleFullscreenChange))
</script>

<style scoped>
.vnc-toolbar {
  padding: 12px 16px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.vnc-toolbar-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: #111827;
  margin-bottom: 8px;
}

.vnc-toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.vnc-btn {
  padding: 6px 12px;
  font-size: 13px;
  background: #dbeafe;
  color: #1d4ed8;
  border: 1px solid #93c5fd;
  border-radius: 4px;
  cursor: pointer;
  transition: background 150ms;
}

.vnc-btn:hover:not(:disabled) { background: #bfdbfe; }
.vnc-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.vnc-toolbar-error {
  margin-top: 8px;
  font-size: 12px;
  color: #dc2626;
}

/* Dialog */
.vnc-dialog-backdrop {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0,0,0,0.5);
}

.vnc-dialog {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.3);
  width: 100%;
  max-width: 28rem;
}

.vnc-screenshot-modal {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.3);
  max-width: 56rem;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
}

.vnc-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  border-bottom: 1px solid #e5e7eb;
  font-weight: 600;
  font-size: 15px;
  color: #111827;
}

.vnc-dialog-close {
  font-size: 20px;
  color: #6b7280;
  background: none;
  border: none;
  cursor: pointer;
  line-height: 1;
}

.vnc-dialog-close:hover { color: #374151; }

.vnc-dialog-body, .vnc-screenshot-body {
  padding: 24px;
  overflow: auto;
}

.vnc-dialog-textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  resize: vertical;
  font-size: 14px;
}

.vnc-dialog-textarea:focus { outline: none; border-color: #60a5fa; box-shadow: 0 0 0 2px rgba(96,165,250,0.3); }

.vnc-screenshot-img { max-width: 100%; height: auto; border-radius: 6px; }

.vnc-dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 24px;
  border-top: 1px solid #e5e7eb;
}

.vnc-btn-primary { padding: 8px 16px; background: #2563eb; color: #fff; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; transition: background 150ms; }
.vnc-btn-primary:hover:not(:disabled) { background: #1d4ed8; }
.vnc-btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.vnc-btn-secondary { padding: 8px 16px; background: #e5e7eb; color: #374151; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; transition: background 150ms; }
.vnc-btn-secondary:hover { background: #d1d5db; }
</style>
