<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!--
  ImageAnalysisResult — what the multimodal service said about one image (#20644).
  Shows the description and labels when the reply carries them, the confidence and time, and the raw
  reply on request; a reply with neither description nor labels says so instead of showing nothing.
-->
<template>
  <BaseCard :title="t('visionCapture.result.title')" data-testid="vision-result">
    <template #actions>
      <BaseBadge :label="t('visionCapture.result.confidence', { value: Math.round(result.confidence * 100) })" />
    </template>
    <p v-if="description" class="image-result__description">{{ description }}</p>
    <div v-if="labels.length" class="image-result__labels">
      <BaseBadge v-for="label in labels" :key="label" variant="info" tone="outline" :label="label" />
    </div>
    <p v-if="!description && !labels.length" class="image-result__muted">{{ t('visionCapture.result.nothing') }}</p>
    <p class="image-result__muted">{{ t('visionCapture.result.time', { seconds: result.processing_time.toFixed(2) }) }}</p>
    <BaseButton variant="ghost" size="xs" @click="showRaw = !showRaw">
      {{ showRaw ? t('visionCapture.result.hideRaw') : t('visionCapture.result.showRaw') }}
    </BaseButton>
    <pre v-if="showRaw" class="image-result__raw">{{ JSON.stringify(result, null, 2) }}</pre>
  </BaseCard>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseBadge, BaseButton, BaseCard } from '@autobot/ui'
import type { MultiModalResponse } from '@/types/visionMultimodal'

const props = defineProps<{ result: MultiModalResponse }>()
const { t } = useI18n()
const showRaw = ref(false)

const data = computed(() => (props.result.result_data ?? {}) as Record<string, unknown>)
const description = computed(() => (typeof data.value.description === 'string' ? data.value.description : ''))
const labels = computed(() => (Array.isArray(data.value.labels) ? data.value.labels.map(String) : []))
</script>

<style scoped>
.image-result__description {
  margin: 0 0 var(--aui-space-3);
  color: var(--aui-color-text);
  white-space: pre-wrap;
}

.image-result__labels {
  display: flex;
  flex-wrap: wrap;
  gap: var(--aui-space-2);
  margin-bottom: var(--aui-space-3);
}

.image-result__muted {
  margin: 0 0 var(--aui-space-2);
  color: var(--aui-color-text-muted);
  font-size: var(--aui-text-sm);
}

.image-result__raw {
  overflow: auto;
  max-height: 20rem;
  font-size: var(--aui-text-sm);
}
</style>
