<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  VoiceModeControls -- the voice UI header's mode controls (#22349): the conversation-mode select on the kit
  `BaseSelectMenu`, the language badge (#1334) and, for the two transports that have one, the connection dot with
  its tooltip. Presentational; shared by the voice panel and the voice overlay. The caller applies the mode.
-->
<template>
  <div class="flex items-center gap-2">
    <BaseSelectMenu
      :model-value="mode"
      :options="options"
      :label="$t('chat.voice.conversationMode')"
      size="sm"
      variant="subtle"
      data-testid="voice-mode"
      @update:model-value="emit('update:mode', $event as ConversationMode)"
    />
    <BaseTooltip :text="$t('chat.voice.languageLabel')">
      <template #default="{ describedby }">
        <BaseBadge variant="info" size="sm" :aria-describedby="describedby" data-testid="voice-language">
          <template #icon><Icon name="globe" /></template>
          {{ language.toUpperCase() }}
        </BaseBadge>
      </template>
    </BaseTooltip>
    <BaseTooltip v-if="connection" :text="connectionText">
      <template #default="{ describedby }">
        <span
          class="voice-mode__dot"
          :class="{ 'voice-mode__dot--connected': connection.connected }"
          role="img"
          :aria-label="$t('chat.voice.connectionLabel', { status: connectionText })"
          :aria-describedby="describedby"
          data-testid="voice-connection"
        ></span>
      </template>
    </BaseTooltip>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseBadge, BaseSelectMenu, BaseTooltip } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import type { ConversationMode } from '@/composables/useVoiceConversation'
import type { VoiceConnection } from '@/composables/chat/useVoiceConversationView'

const props = defineProps<{ mode: ConversationMode; language: string; connection: VoiceConnection | null }>()
const emit = defineEmits<{ 'update:mode': [mode: ConversationMode] }>()

const { t } = useI18n()
const MODES: { value: ConversationMode; key: string }[] = [
  { value: 'walkie-talkie', key: 'walkieTalkie' },
  { value: 'hands-free', key: 'handsFree' },
  { value: 'full-duplex', key: 'fullDuplex' },
  { value: 'realtime-webrtc', key: 'realtimeWebrtc' },
]
const options = computed(() => MODES.map((m) => ({ value: m.value, label: t(`chat.voice.${m.key}`) })))
const connectionText = computed(() => (props.connection?.connected ? t('chat.voice.connected') : t('chat.voice.disconnected')))
</script>

<style scoped>
.voice-mode__dot {
  display: inline-block;
  width: 0.5rem;
  height: 0.5rem;
  border-radius: var(--aui-radius-full);
  background: color-mix(in srgb, var(--aui-color-error) 60%, transparent);
  transition: background-color var(--aui-transition);
}
.voice-mode__dot--connected {
  background: var(--aui-color-success);
}
</style>
