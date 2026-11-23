<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ChatUnassignedGroup -- the sidebar group of chats that carry no company (#21997). Each row opens the
  chat and lets a person pick a company and assign it; this only reports the intent, and nothing is
  assigned until the person presses Assign.
-->
<template>
  <section v-if="sessions.length > 0" data-testid="unassigned-group">
    <h3 class="mx-2.5 mb-1.5 mt-4 text-[0.6875rem] font-semibold uppercase tracking-[0.06em] text-[var(--aui-color-text-muted)]">
      {{ $t('chat.sidebar.unassigned') }}
    </h3>
    <p class="mx-2.5 mb-2 text-xs text-[var(--aui-color-text-muted)]">{{ $t('chat.sidebar.unassignedHint') }}</p>
    <div v-for="session in sessions" :key="session.id" class="flex flex-col gap-1 px-1 pb-2" data-testid="unassigned-row">
      <BaseButton variant="ghost" size="sm" class="justify-start" @click="emit('open', session)">
        {{ titleOf(session) }}
      </BaseButton>
      <div v-if="options.length > 0" class="flex items-center gap-1">
        <BaseSelectMenu
          :model-value="choice[session.id]"
          :options="options"
          size="sm"
          :label="$t('chat.sidebar.assignCompanyLabel', { title: titleOf(session) })"
          :placeholder="$t('chat.sidebar.assignCompanyPlaceholder')"
          @update:model-value="(v: string) => (choice[session.id] = v)"
        />
        <BaseButton
          variant="secondary"
          size="sm"
          :disabled="!choice[session.id]"
          data-testid="unassigned-assign"
          @click="emit('assign', session.id, choice[session.id])"
        >
          {{ $t('chat.sidebar.assignCompany') }}
        </BaseButton>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive } from 'vue'
import { BaseButton, BaseSelectMenu } from '@autobot/ui'
import type { ChatSession } from '@/stores/useChatStore'

const props = defineProps<{
  sessions: ChatSession[]
  companies: { id: string; name: string }[]
  titleOf: (session: ChatSession) => string
}>()

const emit = defineEmits<{
  open: [session: ChatSession]
  assign: [sessionId: string, companyId: string]
}>()

const choice = reactive<Record<string, string>>({})
const options = computed(() => props.companies.map((c) => ({ value: c.id, label: c.name })))
</script>
