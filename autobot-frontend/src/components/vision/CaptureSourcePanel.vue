<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!--
  CaptureSourcePanel — the capture button for one source, camera or shared screen (#20644).
  A source this browser cannot use is disabled, with the reason shown rather than a button that fails.
-->
<template>
  <div>
    <BaseButton :loading="busy" :disabled="!supported" :data-testid="`vision-capture-${source}`" @click="emit('capture', source)">
      {{ t(`visionCapture.capture.${source}`) }}
    </BaseButton>
    <p v-if="!supported" class="mt-2 text-sm text-autobot-text-muted">{{ t('visionCapture.unsupported') }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseButton } from '@autobot/ui'
import { canCapture, type CaptureSource } from '@/composables/useImageCapture'

const props = defineProps<{ source: CaptureSource; busy?: boolean }>()
const emit = defineEmits<{ capture: [source: CaptureSource] }>()
const { t } = useI18n()

const supported = computed(() => canCapture(props.source))
</script>
