<template>
  <SshTerminal v-bind="$props" :auth-token="authToken" v-on="$attrs" />
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Wire-in for @autobot/terminal — satisfies GH#6836 wiring gate for autobot-frontend
import { computed } from 'vue'
import { SshTerminal } from '@autobot/terminal'
import { useUserStore } from '@/stores/useUserStore'

defineProps<{
  hostId: string
  chatSessionId?: string | null
}>()

// #14991: SshTerminal has no store of its own -- the JWT lives in this app's
// useUserStore. Passed as a prop rather than read inside the shared package,
// which other host apps (e.g. autobot-slm-frontend) resolve differently.
const authToken = computed(() => useUserStore().authState.token ?? null)
</script>
