<template>
  <div
    v-if="hasData"
    class="ctx-indicator"
    :class="{
      'ctx-indicator--warning': isWarning && !isCritical,
      'ctx-indicator--critical': isCritical,
    }"
    :title="tooltip"
    role="meter"
    :aria-valuenow="usagePercent"
    :aria-valuemin="0"
    :aria-valuemax="100"
    :aria-label="$t('chat.contextWindow.ariaLabel', { used: formattedUsed, max: formattedMax })"
  >
    <!-- Token count text -->
    <span class="ctx-indicator__text">
      {{ formattedUsed }} / {{ formattedMax }}
    </span>
    <!-- Progress bar -->
    <div class="ctx-indicator__bar-track" aria-hidden="true">
      <div
        class="ctx-indicator__bar-fill"
        :style="{ width: `${usagePercent}%` }"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

interface Props {
  tokensUsed: number
  contextWindow: number
  usagePercent: number
  isWarning: boolean
  isCritical: boolean
  hasData: boolean
}

const props = defineProps<Props>()
const { t } = useI18n()

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}

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
@reference "../../assets/tailwind.css";

.ctx-indicator {
  @apply flex items-center gap-1.5 px-2 py-1 rounded-md text-xs select-none;
  color: var(--text-tertiary);
  background: var(--bg-tertiary);
  min-width: 0;
}

.ctx-indicator__text {
  @apply font-mono whitespace-nowrap shrink-0;
}

.ctx-indicator__bar-track {
  @apply rounded-full overflow-hidden shrink-0;
  width: 48px;
  height: 4px;
  background: var(--border-light);
}

.ctx-indicator__bar-fill {
  height: 4px;
  border-radius: 9999px;
  background: var(--color-success);
  transition: width 0.4s ease, background 0.3s ease;
}

.ctx-indicator--warning .ctx-indicator__text {
  color: var(--color-warning);
}
.ctx-indicator--warning .ctx-indicator__bar-fill {
  background: var(--color-warning);
}

.ctx-indicator--critical .ctx-indicator__text {
  color: var(--color-error);
}
.ctx-indicator--critical .ctx-indicator__bar-fill {
  background: var(--color-error);
}
</style>
