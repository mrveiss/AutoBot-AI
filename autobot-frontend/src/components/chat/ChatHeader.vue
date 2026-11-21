<template>
  <PageHeader class="shrink-0" size="xl">
    <!-- Left: Mobile sidebar toggle + session avatar -->
    <template #leading>
      <!-- Mobile hamburger to open chat sidebar (#1804) -->
      <ChatHeaderIconButton
        class="lg:hidden shrink-0"
        :label="$t('chat.sidebar.expandSidebar')"
        icon="bars"
        @click="$emit('toggle-mobile-sidebar')"
      />

      <div class="flex size-11 shrink-0 items-center justify-center rounded-[10px] border border-[var(--tile-b)] bg-[var(--tile)] text-[var(--stroke)]" aria-hidden="true">
        <Icon name="robot" size="lg" />
      </div>
    </template>
    <template #title>{{ currentSessionTitle }}</template>
    <!-- Above the title, as in the mockup. Knowledge on/off has no shared source (it is a local ref in ChatInput), so it is not shown. -->
    <template #eyebrow>
      <BaseTooltip :text="$t('chat.header.overseerTip')" placement="bottom">
        <template #default="{ describedby }">
          <span tabindex="0" :aria-describedby="describedby">{{ overseerEnabled ? $t('chat.header.overseerOn') : $t('chat.header.overseerOff') }}</span>
        </template>
      </BaseTooltip>
      <template v-if="startedAt"> · <i18n-t keypath="chat.header.startedAt" tag="span"><template #time><span class="font-mono">{{ startedTime }}</span></template></i18n-t></template>
      <template v-else> · {{ sessionInfo }}</template>
    </template>

    <!-- Right: Actions + connection status -->
    <template #actions>
      <!-- Minimal mode: say what is hidden and how to get it back (#18243) -->
      <div class="only-min items-center gap-2 text-sm text-[var(--aui-color-text-muted)]">
        <span>{{ $t('chat.header.essentialsNote') }}</span>
        <BaseButton variant="link" size="sm" @click="showAllFeatures">
          {{ $t('chat.header.showAllFeatures') }}
        </BaseButton>
      </div>

      <!-- GH#8990: context window usage indicator (hidden on mobile to save space) -->
      <ContextWindowIndicator
        v-if="contextWindowProps?.hasData"
        class="adv hidden sm:flex"
        v-bind="contextWindowProps"
      />
      <span
        v-else-if="contextWindowProps?.loadError"
        class="adv hidden sm:inline text-xs text-[var(--aui-color-warning)]"
        role="status"
        :title="contextWindowProps.loadError"
      >
        {{ $t('chat.contextWindow.unavailable') }}
      </span>

      <!-- Custom Actions Slot -->
      <slot name="actions"></slot>

      <!-- Session Actions -->
      <template v-if="currentSessionId">
        <ChatHeaderIconButton
          adv
          :label="$t('chat.exportChat')"
          icon="download"
          @click="$emit('export-session')"
        />
        <ChatHeaderIconButton
          adv
          :label="$t('chat.openSettings')"
          icon="cog"
          @click="$emit('open-settings')"
        />
        <ChatHeaderIconButton
          :label="$t('chat.clearChat')"
          icon="trash"
          @click="$emit('clear-session')"
        />
      </template>

      <!-- Connection status: a plain pill; the tooltip says what Connected means -->
      <BaseTooltip :text="connectionTip" placement="left">
        <template #default="{ describedby }">
          <BaseBadge
            :variant="connectionVariant"
            size="sm"
            rounded
            :aria-describedby="describedby"
            role="status"
            tabindex="0"
          >
            {{ connectionStatus }}
          </BaseBadge>
        </template>
      </BaseTooltip>
    </template>
  </PageHeader>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { BaseBadge, BaseButton, BaseTooltip, PageHeader } from '@autobot/ui'
import type { SemanticVariant } from '@autobot/ui'
import ContextWindowIndicator from './ContextWindowIndicator.vue'
import ChatHeaderIconButton from './ChatHeaderIconButton.vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { formatLocalTime } from '@/utils/formatHelpers'
import { useUiMode, useUiModeAnnouncer } from '@/composables/useUiMode'

interface ContextWindowProps {
  tokensUsed: number
  contextWindow: number
  usagePercent: number
  isWarning: boolean
  isCritical: boolean
  hasData: boolean
  loadError?: string | null
}

interface Props {
  currentSessionId: string | null
  currentSessionTitle: string
  sessionInfo: string
  connectionStatus: string
  isConnected: boolean
  contextWindowProps?: ContextWindowProps
  /** Whether Overseer mode is on for this chat (the ChatInterface ref ChatInput also reads). */
  overseerEnabled?: boolean
  /** When the chat started (the session's creation time, else its first message), if known. */
  startedAt?: Date | string | null
}

interface Emits {
  (e: 'export-session'): void
  (e: 'clear-session'): void
  (e: 'toggle-mobile-sidebar'): void
  (e: 'open-settings'): void
}

const props = defineProps<Props>()
defineEmits<Emits>()

const { t } = useI18n()
const { setMode } = useUiMode()
const announceMode = useUiModeAnnouncer()

function showAllFeatures(): void {
  setMode('full')
  announceMode('full')
}

const connectionVariant = computed<SemanticVariant>(() => {
  if (!props.isConnected) return 'error'
  return props.connectionStatus === 'Connecting' ? 'warning' : 'success'
})

const startedTime = computed(() => (props.startedAt ? formatLocalTime(props.startedAt) : ''))

const connectionTip = computed(() =>
  props.isConnected && props.connectionStatus !== 'Connecting' ? t('chat.header.connectedTip') : props.connectionStatus,
)
</script>
