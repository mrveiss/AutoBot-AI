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
    <p v-if="description" class="mb-3 whitespace-pre-wrap text-autobot-text-primary">{{ description }}</p>
    <div v-if="labels.length" class="mb-3 flex flex-wrap gap-2">
      <BaseBadge v-for="label in labels" :key="label" variant="info" tone="outline" :label="label" />
    </div>
    <p v-if="!description && !labels.length" class="mb-2 text-sm text-autobot-text-muted">{{ t('visionCapture.result.nothing') }}</p>
    <p class="mb-2 text-sm text-autobot-text-muted">{{ t('visionCapture.result.time', { seconds: result.processing_time.toFixed(2) }) }}</p>
    <BaseButton variant="ghost" size="xs" @click="showRaw = !showRaw">
      {{ showRaw ? t('visionCapture.result.hideRaw') : t('visionCapture.result.showRaw') }}
    </BaseButton>
    <pre v-if="showRaw" class="max-h-80 overflow-auto text-sm">{{ JSON.stringify(result, null, 2) }}</pre>
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
