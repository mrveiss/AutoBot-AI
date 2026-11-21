<template>
  <PageHeader class="shrink-0">
    <!-- Left: Mobile sidebar toggle + session avatar -->
    <template #leading>
      <!-- Mobile hamburger to open chat sidebar (#1804) -->
      <ChatHeaderIconButton
        class="lg:hidden shrink-0"
        :label="$t('chat.sidebar.expandSidebar')"
        icon="bars"
        @click="$emit('toggle-mobile-sidebar')"
      />

      <div class="flex size-8 shrink-0 items-center justify-center rounded-md bg-[var(--aui-color-primary)] text-[var(--aui-color-primary-contrast)]" aria-hidden="true">
        <Icon name="robot" />
      </div>
    </template>
    <template #title>{{ currentSessionTitle }}</template>
    <template #subtitle><span class="hidden sm:inline">{{ sessionInfo }}</span></template>

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
          :label="$t('chat.openSettings')"
          icon="cog"
          @click="$emit('open-settings')"
        />
        <ChatHeaderIconButton
          adv
          :label="$t('chat.exportChat')"
          icon="download"
          @click="$emit('export-session')"
        />
        <ChatHeaderIconButton
          :label="$t('chat.clearChat')"
          icon="trash"
          @click="$emit('clear-session')"
        />
      </template>

      <!-- Connection Status — icon only on mobile, full label on sm+ -->
      <BaseTooltip :text="connectionStatus" placement="bottom">
        <template #default="{ describedby }">
          <BaseBadge
            :variant="connectionVariant"
            :aria-describedby="describedby"
            role="status"
            tabindex="0"
          >
            <template #icon><Icon :name="connectionStatusIcon" /></template>
            <span class="hidden sm:inline">{{ connectionStatus }}</span>
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
}

interface Emits {
  (e: 'export-session'): void
  (e: 'clear-session'): void
  (e: 'toggle-mobile-sidebar'): void
  (e: 'open-settings'): void
}

const props = defineProps<Props>()
defineEmits<Emits>()

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

const connectionStatusIcon = computed(() => {
  if (!props.isConnected) return 'exclamation-circle'
  if (props.connectionStatus === 'Connecting') return 'spinner'
  return 'check-circle'
})
</script>
