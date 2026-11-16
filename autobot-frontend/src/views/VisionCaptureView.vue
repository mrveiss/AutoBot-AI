<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!--
  VisionCaptureView — Vision, moved here from the SLM console (#20644).
  Take a still from the camera or from a shared screen, or choose an image file; analyse it with the
  multimodal service; reopen any of the last 10 analyses of this visit. Server-desktop analysis stays
  on Vision Automation; this screen only analyses the image the user gives it.
-->
<template>
  <div class="vision-capture">
    <PageHeader :title="t('visionCapture.title')" :subtitle="t('visionCapture.subtitle')" />

    <BaseCard :title="t('visionCapture.sourceTitle')">
      <BaseTabs v-model="source" :items="sourceTabs" :label="t('visionCapture.sourceLabel')">
        <template #panel-upload>
          <input ref="fileInput" type="file" accept="image/*" hidden data-testid="vision-file" @change="onFile" />
          <BaseButton @click="fileInput?.click()">{{ t('visionCapture.chooseFile') }}</BaseButton>
        </template>
        <template #panel-camera>
          <CaptureSourcePanel source="camera" :busy="screen.capturing.value" @capture="screen.capture" />
        </template>
        <template #panel-screen>
          <CaptureSourcePanel source="screen" :busy="screen.capturing.value" @capture="screen.capture" />
        </template>
      </BaseTabs>
    </BaseCard>

    <BaseAlert v-if="screen.error.value" variant="error" :message="screen.error.value" data-testid="vision-error" />

    <BaseCard v-if="screen.previewUrl.value" :title="t('visionCapture.analyzeTitle')">
      <template #actions>
        <BaseButton variant="ghost" size="sm" @click="screen.choose(null)">{{ t('visionCapture.clear') }}</BaseButton>
      </template>
      <img :src="screen.previewUrl.value" :alt="t('visionCapture.previewAlt')" class="vision-capture__preview" />
      <div class="vision-capture__options">
        <BaseSelectMenu v-model="screen.intent.value" :options="intentOptions" :label="t('visionCapture.intent')" />
        <BaseInput
          v-if="screen.intent.value === 'visual_qa'"
          v-model="screen.question.value"
          :label="t('visionCapture.question')"
          :placeholder="t('visionCapture.questionPlaceholder')"
        />
      </div>
      <BaseButton :loading="screen.analyzing.value" data-testid="vision-analyze" @click="screen.analyze()">
        {{ t('visionCapture.analyze') }}
      </BaseButton>
    </BaseCard>
    <EmptyState v-else :title="t('visionCapture.noImage')" :description="t('visionCapture.noImageDetail')" compact />

    <ImageAnalysisResult v-if="screen.result.value" :result="screen.result.value" />

    <BaseCard :title="t('visionCapture.historyTitle')">
      <EmptyState v-if="!screen.history.value.length" :title="t('visionCapture.historyEmpty')" compact />
      <ul v-else class="vision-capture__history" data-testid="vision-history">
        <li v-for="entry in screen.history.value" :key="entry.id">
          <button type="button" class="vision-capture__history-item" @click="screen.reopen(entry)">
            <img :src="entry.previewUrl" alt="" class="vision-capture__thumb" />
            <span>{{ formatDateTime(entry.at) }}</span>
            <span>{{ intentLabel(entry.intent) }}</span>
          </button>
        </li>
      </ul>
    </BaseCard>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  BaseAlert, BaseButton, BaseCard, BaseInput, BaseSelectMenu, BaseTabs, EmptyState, PageHeader, formatDateTime,
} from '@autobot/ui'
import ImageAnalysisResult from '@/components/vision/ImageAnalysisResult.vue'
import CaptureSourcePanel from '@/components/vision/CaptureSourcePanel.vue'
import { useVisionCaptureScreen } from '@/composables/useVisionCaptureScreen'

const { t } = useI18n()
const screen = useVisionCaptureScreen()
const fileInput = ref<HTMLInputElement | null>(null)
const source = ref('upload')

const CAPTURE_SOURCES = ['camera', 'screen'] as const
const INTENTS = ['analysis', 'visual_qa', 'automation', 'content_generation'] as const
const INTENT_KEYS: Record<string, string> = {
  analysis: 'chat.vision.intentAnalysis',
  visual_qa: 'chat.vision.intentVisualQA',
  automation: 'chat.vision.intentAutomation',
  content_generation: 'chat.vision.intentContentGeneration',
}

const sourceTabs = computed(() =>
  ['upload', ...CAPTURE_SOURCES].map((value) => ({ value, label: t(`visionCapture.source.${value}`) })),
)
const intentOptions = computed(() => INTENTS.map((value) => ({ value, label: intentLabel(value) })))

function intentLabel(intent: string): string {
  return INTENT_KEYS[intent] ? t(INTENT_KEYS[intent]) : intent
}

function onFile(event: Event): void {
  const input = event.target as HTMLInputElement
  screen.choose(input.files?.[0] ?? null)
  input.value = ''
}
</script>

<style scoped>
.vision-capture {
  display: flex;
  flex-direction: column;
  gap: var(--aui-space-4);
  padding: var(--aui-space-6);
}

.vision-capture__preview {
  display: block;
  max-width: 100%;
  max-height: 24rem;
  margin-bottom: var(--aui-space-3);
}

.vision-capture__options {
  display: flex;
  flex-wrap: wrap;
  gap: var(--aui-space-3);
  margin-bottom: var(--aui-space-3);
}

.vision-capture__history {
  display: flex;
  flex-direction: column;
  gap: var(--aui-space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.vision-capture__history-item {
  display: flex;
  align-items: center;
  gap: var(--aui-space-3);
  width: 100%;
  padding: var(--aui-space-2);
  border: 1px solid var(--aui-color-border);
  background: transparent;
  color: var(--aui-color-text);
  text-align: start;
  cursor: pointer;
}

.vision-capture__thumb {
  width: 3rem;
  height: 3rem;
  object-fit: cover;
}
</style>
