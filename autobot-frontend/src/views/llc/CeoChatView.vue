<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0
  AutoBot - AI-Powered Automation Platform
  Author: mrveiss

  CEO Chat (#11690): 1:1 with the general assistant. Renders the shared
  ChatInterface and scopes the conversation to this company by setting
  chatStore.activeChatContext = { company_id } while mounted — the backend then
  teaches + executes the company's LLC tools (create_task / update_goal /
  request_approval / record_decision) on the normal /chat streaming path, so the
  streaming, tool-call rendering and composer are identical to /chat. The scope
  is cleared on unmount, leaving the general /chat unaffected.
-->
<template>
  <div class="h-full">
    <div v-if="!companyId" class="flex h-full items-center justify-center text-autobot-text-muted">
      {{ $t('llc.ceoChat.selectCompany') }}
    </div>
    <ChatInterface v-else :key="companyId" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute } from 'vue-router'
import ChatInterface from '@/components/chat/ChatInterface.vue'
import { useChatStore } from '@/stores/useChatStore'

const route = useRoute()
const props = defineProps<{ companyId?: string }>()
const companyId = computed(() => (route.params.companyId as string) ?? props.companyId ?? '')

const chatStore = useChatStore()

function applyScope(id: string) {
  chatStore.setActiveChatContext(id ? { company_id: id } : {})
}

onMounted(() => applyScope(companyId.value))
// Re-scope if the route switches companies without remounting.
watch(companyId, (id) => applyScope(id))
onBeforeUnmount(() => chatStore.setActiveChatContext({}))
</script>
