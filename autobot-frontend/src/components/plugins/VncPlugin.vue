<template>
  <div class="vnc-plugin">
    <VncViewer
      :model-value="modelValue"
      :host="host"
      :loading="loading"
      @update:model-value="$emit('update:modelValue', $event)"
    />
    <!-- The backend refuses a control with no host_id (422): no selected host, no controls (#22145). -->
    <VncToolbar
      v-if="host"
      :connected="modelValue"
      :api-base-url="apiBaseUrl ?? getApiBase()"
      :host-id="host.id"
    />
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Wire-in for @autobot/vnc — satisfies GH#6836 wiring gate for autobot-frontend
import { VncViewer, VncToolbar } from '@autobot/vnc'
import type { VncHost } from '@autobot/vnc'
import { getApiBase } from '@/config/ssot-config'

defineProps<{
  modelValue: boolean
  /** The selected host; its `id` is the /secrets host id (or the desktop VM id) every control acts on. */
  host?: VncHost
  loading?: boolean
  /** Base URL for VNC API calls propagated to VncToolbar. Defaults to the canonical API base. */
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
