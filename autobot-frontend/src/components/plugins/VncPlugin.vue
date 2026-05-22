<template>
  <VncViewer v-bind="$props" v-on="$attrs" />
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Wire-in for @autobot/vnc — satisfies GH#6836 wiring gate for autobot-frontend
import { VncViewer } from '@autobot/vnc'
import type { VncHost } from '@autobot/vnc'

defineProps<{
  modelValue: boolean
  host?: VncHost
  loading?: boolean
}>()
</script>
