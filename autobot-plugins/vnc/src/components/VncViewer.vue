<template>
  <div class="vnc-viewer">
    <!-- Loading state -->
    <div v-if="loading" class="vnc-state-overlay">
      <div class="vnc-spinner"></div>
      <p class="vnc-state-text">Connecting to {{ host?.name }}...</p>
    </div>

    <!-- Idle state -->
    <div v-else-if="!modelValue" class="vnc-state-overlay">
      <svg class="vnc-idle-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
      </svg>
      <p class="vnc-state-text">Select a host and connect to start viewing</p>
      <div v-if="host" class="vnc-host-info">
        <p class="vnc-host-desc">{{ host.description }}</p>
        <code class="vnc-host-addr">{{ host.host }}:{{ host.port }}</code>
      </div>
    </div>

    <!-- External host (no embed proxy) -->
    <div v-else-if="!canEmbed" class="vnc-state-overlay">
      <svg class="vnc-idle-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
      </svg>
      <p class="vnc-state-text">This host requires a separate browser tab</p>
      <a :href="vncUrl" target="_blank" rel="noopener" class="vnc-open-btn">Open noVNC in New Tab</a>
    </div>

    <!-- Embedded iframe -->
    <iframe
      v-else
      id="vnc-frame"
      :src="vncUrl"
      class="vnc-frame"
      allow="fullscreen"
      @load="onIframeLoad"
    ></iframe>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss

import { computed } from 'vue'
import type { VncHost } from '../types'

const props = defineProps<{
  /** Whether the viewer is in connected/active state (v-model). */
  modelValue: boolean
  host?: VncHost
  loading?: boolean
}>()

defineEmits<{ 'update:modelValue': [value: boolean] }>()

/** URL to load in the iframe. Proxied main host uses relative path; others use direct URL. */
const vncUrl = computed(() => {
  if (!props.host) return ''
  if (props.host.proxied ?? props.host.id === 'main') {
    return `/tools/novnc/vnc.html?autoconnect=true&resize=scale`
  }
  return `http://${props.host.host}:${props.host.port}/vnc.html?autoconnect=true&resize=scale`
})

const canEmbed = computed(() => props.host?.proxied ?? props.host?.id === 'main')

const onIframeLoad = () => {
  // iframe loaded successfully — nothing needed
}

defineExpose({ vncUrl })
</script>

<style scoped>
.vnc-viewer {
  width: 100%;
  height: 100%;
  background: #111827;
  position: relative;
  display: flex;
  align-items: stretch;
}

.vnc-frame {
  width: 100%;
  height: 100%;
  border: none;
}

.vnc-state-overlay {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  padding: 32px;
  text-align: center;
  color: #9ca3af;
}

.vnc-idle-icon {
  width: 64px;
  height: 64px;
  color: #4b5563;
  margin-bottom: 16px;
}

.vnc-state-text {
  font-size: 14px;
  color: #6b7280;
  margin-top: 8px;
}

.vnc-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #374151;
  border-top-color: #60a5fa;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-bottom: 16px;
}

@keyframes spin { to { transform: rotate(360deg); } }

.vnc-host-info {
  margin-top: 16px;
  padding: 16px;
  background: #1f2937;
  border-radius: 8px;
}

.vnc-host-desc { font-size: 13px; color: #9ca3af; }
.vnc-host-addr { display: block; font-size: 11px; color: #6b7280; margin-top: 8px; font-family: monospace; }

.vnc-open-btn {
  margin-top: 16px;
  padding: 8px 16px;
  background: #2563eb;
  color: #fff;
  border-radius: 6px;
  text-decoration: none;
  font-size: 14px;
  transition: background 150ms;
}

.vnc-open-btn:hover { background: #1d4ed8; }
</style>
