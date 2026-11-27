<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  KnowledgeUploadUrl — "Import from URL" of Knowledge · Manage · Upload (#18244).
-->
<template>
  <BaseCard :title="$t('knowledge.upload.importFromUrl')">
    <div class="flex flex-col gap-3">
      <BaseInput v-model="entry.url" type="url" :label="$t('knowledge.upload.urlLabel')" :placeholder="$t('knowledge.upload.urlPlaceholder')" @keyup.enter="submit" />

      <div class="grid grid-cols-[repeat(auto-fit,minmax(14rem,1fr))] gap-3">
        <BaseSelectMenu v-model="category" :label="$t('knowledge.upload.category')" :placeholder="$t('knowledge.upload.selectCategory')" :options="categoryOptions" />
        <BaseInput v-model="entry.tagsInput" :label="$t('knowledge.upload.tags')" :placeholder="$t('knowledge.upload.tagsPlaceholder')" />
      </div>

      <BaseButton variant="primary" class="self-start" :disabled="!isValidUrl(entry.url) || feedback.isSubmitting.value" @click="submit">
        <Icon name="download" aria-hidden="true" />{{ $t('knowledge.upload.importContent') }}
      </BaseButton>
    </div>
  </BaseCard>
</template>

<script setup lang="ts">
import { computed, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseButton, BaseCard, BaseInput, BaseSelectMenu } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import { useKnowledgeController } from '@/models/controllers'
import { parseTags } from '@/utils/tagHelpers'
import { resetFormFields } from '@/utils/formHelpers'
import { isValidUrl } from '@/composables/useNotificationConfig'
import type { UploadFeedback } from '@/composables/knowledge/useKnowledgeUploadFeedback'

const props = defineProps<{ feedback: UploadFeedback }>()

const PROGRESS_CEILING = 90
const PROGRESS_STEP = 10
const PROGRESS_TICK_MS = 200

const { t } = useI18n()
const store = useKnowledgeStore()
const controller = useKnowledgeController()

const entry = reactive({ url: '', category: '', tagsInput: '' })
const category = computed({ get: () => entry.category || undefined, set: (value) => { entry.category = value ?? '' } })
const categoryOptions = computed(() => store.categories.map((c) => ({ value: c.name, label: c.name })))

async function submit(): Promise<void> {
  if (!isValidUrl(entry.url)) return
  const { feedback } = props
  feedback.begin()
  feedback.startProgress(t('knowledge.upload.importingFromUrl'), t('knowledge.upload.fetchingContent'))
  const ticker = feedback.simulateProgress(PROGRESS_CEILING, PROGRESS_STEP, PROGRESS_TICK_MS)
  try {
    await controller.addUrlDocument(entry.url, entry.category || 'Web Content', parseTags(entry.tagsInput))
    clearInterval(ticker)
    feedback.completeProgress(t('knowledge.upload.importComplete'))
    feedback.showSuccess(t('knowledge.upload.successUrlImported'), feedback.hideProgress)
    resetFormFields(entry)
  } catch (error: unknown) {
    clearInterval(ticker)
    feedback.showError((error as Error).message || t('knowledge.upload.errorImportUrl'))
    feedback.hideProgress()
  } finally {
    feedback.end()
  }
}
</script>
