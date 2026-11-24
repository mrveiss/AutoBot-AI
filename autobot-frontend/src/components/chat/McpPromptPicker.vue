<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  McpPromptPicker -- insert an MCP prompt template into the composer (MVA-2167, #18243). A named icon button
  opens a kit modal: pick a source bridge, pick a prompt, fill its parameters, insert. The state and the
  requests are `useMcpPrompts`; this is the view, on the kit and tokens, with every string a locale key.
-->
<template>
  <div class="inline-flex">
    <ChatHeaderIconButton
      placement="top"
      :label="$t('chat.input.selectPromptTemplate')"
      icon="list-alt"
      :disabled="disabled"
      :expanded="showModal"
      @click="showModal = true"
    />

    <BaseModal
      v-model="showModal"
      :title="$t('chat.mcpPrompts.title')"
      :close-label="$t('ui.modal.closeDialog')"
      size="md"
      @close="closeModal"
    >
      <div v-if="loading" class="flex items-center justify-center gap-3 p-6 text-[var(--aui-color-text-muted)]" role="status">
        <BaseSpinner size="sm" />
        <span>{{ $t('chat.mcpPrompts.loading') }}</span>
      </div>

      <BaseAlert v-else-if="error" variant="error" :message="$t(error)">
        <template #actions><BaseButton size="sm" variant="outline" @click="loadPrompts">{{ $t('common.retry') }}</BaseButton></template>
      </BaseAlert>

      <div v-else-if="!selectedPrompt" class="flex flex-col gap-3">
        <label class="flex items-center gap-2 text-sm text-[var(--aui-color-text-muted)]">
          <span>{{ $t('chat.mcpPrompts.source') }}</span>
          <select v-model="activeBridge" class="h-8 rounded-[var(--aui-radius-md)] border border-[var(--aui-input-border)] bg-[var(--aui-input-bg)] px-2 text-sm text-[var(--aui-color-text)]">
            <option v-for="bridge in MCP_BRIDGES" :key="bridge" :value="bridge">{{ $t(`chat.mcpPrompts.bridges.${bridge}`) }}</option>
          </select>
        </label>
        <EmptyState v-if="currentPrompts.length === 0" :description="$t('chat.mcpPrompts.empty', { bridge: $t(`chat.mcpPrompts.bridges.${activeBridge}`) })" compact>
          <template #icon><Icon name="file-alt" size="xl" /></template>
        </EmptyState>
        <ul v-else class="m-0 flex list-none flex-col gap-2 p-0">
          <li v-for="prompt in currentPrompts" :key="prompt.name">
            <button
              type="button"
              class="flex w-full cursor-pointer flex-col items-start gap-1 rounded-[var(--aui-radius-md)] border border-[var(--aui-color-border)] bg-[var(--aui-color-surface)] p-3 text-start text-[var(--aui-color-text)] hover:border-[var(--aui-color-border-strong)] hover:bg-[var(--aui-color-surface-raised)] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[var(--aui-color-focus-ring)]"
              @click="selectPrompt(prompt)"
            >
              <span class="font-mono text-sm font-medium">{{ prompt.name }}</span>
              <span v-if="prompt.description" class="text-sm text-[var(--aui-color-text-muted)]">{{ prompt.description }}</span>
              <span v-if="prompt.arguments?.length" class="flex flex-wrap items-center gap-1 text-xs text-[var(--aui-color-text-muted)]">
                <span>{{ $t('chat.mcpPrompts.parameters') }}</span>
                <BaseBadge v-for="arg in prompt.arguments" :key="arg.name" size="xs" monospace>{{ arg.name }}{{ arg.required ? '*' : '' }}</BaseBadge>
              </span>
            </button>
          </li>
        </ul>
      </div>

      <form v-else class="flex flex-col gap-3" @submit.prevent="insertPrompt">
        <div class="flex items-center gap-3">
          <BaseButton variant="ghost" size="sm" @click="reset">
            <template #icon-left><Icon name="arrow-left" /></template>
            {{ $t('common.back') }}
          </BaseButton>
          <h4 class="m-0 font-mono text-base">{{ selectedPrompt.name }}</h4>
        </div>
        <p v-if="selectedPrompt.description" class="m-0 text-sm text-[var(--aui-color-text-muted)]">{{ selectedPrompt.description }}</p>
        <BaseInput
          v-for="arg in selectedPrompt.arguments"
          :key="arg.name"
          v-model="formValues[arg.name]"
          :label="arg.name"
          :required="arg.required"
          :helper-text="arg.description"
          :placeholder="arg.description || arg.name"
        />
        <BaseAlert v-if="formError" variant="error" :message="$t(formError.key, formError.params ?? {})" />
      </form>

      <template #actions>
        <BaseButton variant="ghost" @click="closeModal">{{ $t('common.cancel') }}</BaseButton>
        <BaseButton v-if="selectedPrompt" variant="primary" :loading="insertLoading" @click="insertPrompt">
          {{ $t('chat.mcpPrompts.insert') }}
        </BaseButton>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { BaseAlert, BaseBadge, BaseButton, BaseInput, BaseModal, BaseSpinner, EmptyState } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import ChatHeaderIconButton from './ChatHeaderIconButton.vue'
import { MCP_BRIDGES, useMcpPrompts } from '@/composables/chat/useMcpPrompts'

defineProps<{ disabled?: boolean }>()
const emit = defineEmits<{ (e: 'insert', text: string): void }>()

const showModal = ref(false)
const {
  activeBridge, loading, error, selectedPrompt, formValues, formError, insertLoading, currentPrompts,
  promptsByBridge, loadPrompts, selectPrompt, renderSelected, reset,
} = useMcpPrompts()

// Load on first open (and again while the first bridge is still empty), as before.
watch(showModal, (show: boolean) => {
  if (show && promptsByBridge.value.git.length === 0) void loadPrompts()
})

function closeModal(): void {
  showModal.value = false
  reset()
}

async function insertPrompt(): Promise<void> {
  const text = await renderSelected()
  if (text === null) return
  emit('insert', text)
  closeModal()
}
</script>
