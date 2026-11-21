<template>
  <BaseTooltip v-if="hasData" :text="tooltip" placement="bottom">
    <template #default="{ describedby }">
      <div
        class="ctx-indicator"
        :class="{ 'ctx-indicator--summarizing': isSummarizing }"
        tabindex="0"
        :aria-describedby="describedby"
      >
        <!-- Token count text -->
        <span class="ctx-indicator__text" :class="`ctx-indicator__text--${variant}`">
          {{ isSummarizing ? t('chat.contextWindow.summarizing') : `${formattedUsed} / ${formattedMax}` }}
        </span>
        <BaseProgress
          class="ctx-indicator__bar"
          size="sm"
          :variant="variant"
          :value="usagePercent"
          :label="t('chat.contextWindow.ariaLabel', { used: formattedUsed, max: formattedMax })"
        />
      </div>
    </template>
  </BaseTooltip>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseProgress, BaseTooltip } from '@autobot/ui'
import type { SemanticVariant } from '@autobot/ui'

interface Props {
  tokensUsed: number
  contextWindow: number
  usagePercent: number
  isWarning: boolean
  isCritical: boolean
  hasData: boolean
  isSummarizing?: boolean // GH#9043: context overflow protection status
}

const props = defineProps<Props>()
const { t } = useI18n()

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}

/** Summarizing wins over the usage band; otherwise warning and critical map onto the kit variants. */
const variant = computed<SemanticVariant>(() => {
  if (props.isSummarizing) return 'info'
  if (props.isCritical) return 'error'
  return props.isWarning ? 'warning' : 'success'
})

const formattedUsed = computed(() => formatTokens(props.tokensUsed))
const formattedMax = computed(() => formatTokens(props.contextWindow))

const tooltip = computed(() =>
  t('chat.contextWindow.tooltip', {
    used: props.tokensUsed.toLocaleString(),
    max: props.contextWindow.toLocaleString(),
    percent: props.usagePercent.toFixed(1),
  }),
)
</script>

<style scoped>
.ctx-indicator {
  display: flex;
  align-items: center;
  gap: var(--aui-space-2);
  min-inline-size: 0;
  user-select: none;
}

.ctx-indicator__bar {
  inline-size: 3rem;
  flex-shrink: 0;
}

.ctx-indicator__text {
  flex-shrink: 0;
  white-space: nowrap;
  font-family: var(--aui-font-mono);
  font-size: var(--aui-text-xs);
  color: var(--aui-color-text-muted);
}

.ctx-indicator__text--warning {
  color: var(--aui-color-warning);
}
.ctx-indicator__text--error {
  color: var(--aui-color-error);
}
.ctx-indicator__text--info {
  color: var(--aui-color-info);
}

.ctx-indicator--summarizing .ctx-indicator__bar {
  animation: ctx-pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

@keyframes ctx-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}
</style>
