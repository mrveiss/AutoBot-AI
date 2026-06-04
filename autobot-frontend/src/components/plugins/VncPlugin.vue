<template>
  <div class="vnc-plugin">
    <VncViewer
      :model-value="modelValue"
      :host="host"
      :loading="loading"
      @update:model-value="$emit('update:modelValue', $event)"
    />
    <VncToolbar
      :connected="modelValue"
      :api-base-url="apiBaseUrl"
    />
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Wire-in for @autobot/vnc — satisfies GH#6836 wiring gate for autobot-frontend
import { VncViewer, VncToolbar } from '@autobot/vnc'
import type { VncHost } from '@autobot/vnc'

defineProps<{
  modelValue: boolean
  host?: VncHost
  loading?: boolean
  /** Base URL for VNC API calls propagated to VncToolbar. Defaults to /api in plugin. */
  apiBaseUrl?: string
}>()

defineEmits<{
  'update:modelValue': [value: boolean]
}>()
</script>

<style scoped>
.vnc-plugin {
  display: flex;
  flex-direction: column;
  height: 100%;
}
</style>
