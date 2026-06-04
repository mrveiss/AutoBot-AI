<template>
  <SshTerminal v-bind="$props" v-on="$attrs" />
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Wire-in for @autobot/terminal — satisfies GH#6836 wiring gate for autobot-frontend
import { SshTerminal } from '@autobot/terminal'

defineProps<{
  hostId: string
  chatSessionId?: string | null
}>()
</script>
