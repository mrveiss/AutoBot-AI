<template>
  <BaseTooltip v-if="hasData" :text="tooltip" placement="bottom">
    <template #default="{ describedby }">
      <div class="ctx-indicator flex min-w-0 select-none items-center gap-2" tabindex="0" :aria-describedby="describedby">
        <!-- Token count text -->
        <span class="shrink-0 whitespace-nowrap font-mono text-xs" :class="textClass">
          {{ isSummarizing ? t('chat.contextWindow.summarizing') : `${formattedUsed} / ${formattedMax}` }}
        </span>
        <BaseProgress
          class="w-12 shrink-0"
          :class="{ 'animate-pulse': isSummarizing }"
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

const TEXT_CLASS: Record<string, string> = {
  warning: 'text-[var(--aui-color-warning)]',
  error: 'text-[var(--aui-color-error)]',
  info: 'text-[var(--aui-color-info)]',
}
const textClass = computed(() => TEXT_CLASS[variant.value] ?? 'text-[var(--aui-color-text-muted)]')

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
