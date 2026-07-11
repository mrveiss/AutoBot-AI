<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0
  AutoBot - AI-Powered Automation Platform
  Author: mrveiss

  CEO Chat (#11690): 1:1 with the general assistant. Renders the shared
  ChatInterface and scopes the conversation to this company by (a) setting
  chatStore.activeChatContext = { company_id } so the backend teaches + executes
  the company's LLC tools on the normal /chat streaming path, and (b) switching
  to a per-company session so each company's history is ISOLATED from /chat and
  from other companies. The previous (/chat) session is restored on leave, and
  the scope is cleared — so the general assistant is never touched.
-->
<template>
  <div class="h-full">
    <div v-if="!companyId" class="flex h-full items-center justify-center text-autobot-text-muted">
      {{ $t('llc.ceoChat.selectCompany') }}
    </div>
    <ChatInterface v-else />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute } from 'vue-router'
import ChatInterface from '@/components/chat/ChatInterface.vue'
import { useChatStore } from '@/stores/useChatStore'
import { useChatController } from '@/models/controllers'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('CeoChatView')
const route = useRoute()
const props = defineProps<{ companyId?: string }>()
const companyId = computed(() => (route.params.companyId as string) ?? props.companyId ?? '')

const chatStore = useChatStore()
const controller = useChatController()

// Per-company CEO session ids for this SPA lifetime — isolates each company's
// CEO conversation from /chat and from other companies. Not persisted across a
// page reload (a fresh CEO session is minted next visit), which avoids
// duplicate-by-title races while still guaranteeing isolation.
const ceoSessions = new Map<string, string>()
let prevSessionId: string | null = null
let scoped = false

async function enterScope(id: string) {
  if (!id) return
  // Remember the general /chat session so we can restore it on leave.
  prevSessionId = chatStore.currentSessionId
  chatStore.setActiveChatContext({ company_id: id })
  scoped = true
  try {
    const mapped = ceoSessions.get(id)
    if (mapped && chatStore.sessions.some((s) => s.id === mapped)) {
      await controller.switchToSession(mapped)
    } else {
      const sid = await controller.createNewSession(`CEO · ${id}`)
      ceoSessions.set(id, sid)
    }
  } catch (err) {
    logger.error('Failed to open company CEO session', err)
  }
}

async function leaveScope() {
  if (!scoped) return
  scoped = false
  chatStore.setActiveChatContext({})
  // Restore the general /chat session so CEO history never bleeds into /chat.
  if (prevSessionId && chatStore.sessions.some((s) => s.id === prevSessionId)) {
    try {
      await controller.switchToSession(prevSessionId)
    } catch (err) {
      logger.error('Failed to restore prior chat session', err)
    }
  }
  prevSessionId = null
}

onMounted(() => enterScope(companyId.value))
watch(companyId, async (id) => {
  await leaveScope()
  await enterScope(id)
})
onBeforeUnmount(() => {
  void leaveScope()
})
</script>
