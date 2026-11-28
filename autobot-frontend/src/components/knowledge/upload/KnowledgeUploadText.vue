<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  KnowledgeUploadText — "Text entry" of Knowledge · Manage · Upload (#747, #18244): a title,
  free text, category, tags and the hierarchical access fields (#685).
-->
<template>
  <BaseCard :title="$t('knowledge.upload.textEntry')">
    <div class="flex flex-col gap-3">
      <BaseInput v-model="entry.title" :label="$t('knowledge.upload.titleLabel')" :placeholder="$t('knowledge.upload.titlePlaceholder')" />

      <BaseFormField :label="$t('knowledge.upload.contentLabel')" :hint="$t('knowledge.upload.charCount', { count: entry.content.length })">
        <template #default="{ id, describedBy }">
          <textarea
            :id="id"
            v-model="entry.content"
            class="w-full rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-[var(--text)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]"
            rows="6"
            required
            :placeholder="$t('knowledge.upload.contentPlaceholder')"
            :aria-describedby="describedBy"
          />
        </template>
      </BaseFormField>

      <div class="grid grid-cols-[repeat(auto-fit,minmax(14rem,1fr))] gap-3">
        <BaseSelectMenu v-model="category" :label="$t('knowledge.upload.category')" :placeholder="$t('knowledge.upload.selectCategory')" :options="categoryOptions" />
        <BaseInput v-model="entry.tagsInput" :label="$t('knowledge.upload.tags')" :placeholder="$t('knowledge.upload.tagsPlaceholder')" @keyup.enter="submit" />
      </div>

      <!-- Issue #685: hierarchical access controls -->
      <div class="grid grid-cols-[repeat(auto-fit,minmax(14rem,1fr))] gap-3">
        <BaseSelectMenu v-model="entry.accessLevel" :label="$t('knowledge.upload.accessLevel')" :options="accessOptions" />
        <BaseSelectMenu v-model="entry.visibility" :label="$t('knowledge.upload.visibility')" :options="visibilityOptions" />
      </div>
      <p class="m-0 text-xs text-[var(--muted)]">{{ $t('knowledge.upload.accessHint') }} {{ $t('knowledge.upload.visibilityHint') }}</p>

      <BaseButton variant="primary" class="self-start" :disabled="!entry.content.trim() || feedback.isSubmitting.value" @click="submit">
        <Icon name="plus" aria-hidden="true" />{{ $t('knowledge.upload.addToKnowledgeBase') }}
      </BaseButton>
    </div>
  </BaseCard>
</template>

<script setup lang="ts">
import { computed, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseButton, BaseCard, BaseFormField, BaseInput, BaseSelectMenu } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import { useKnowledgeController } from '@/models/controllers'
import { parseTags } from '@/utils/tagHelpers'
import { resetFormFields } from '@/utils/formHelpers'
import { accessLevelErrorKey } from '@/composables/knowledge/knowledgeUploadFileUtils'
import type { UploadFeedback } from '@/composables/knowledge/useKnowledgeUploadFeedback'

const props = defineProps<{ feedback: UploadFeedback }>()

const { t } = useI18n()
const store = useKnowledgeStore()
const controller = useKnowledgeController()

const entry = reactive({ title: '', content: '', category: '', tagsInput: '', accessLevel: 'user', visibility: 'private' })
// An empty select value means "no category chosen"; the controller then applies the default (#21921).
const category = computed({ get: () => entry.category || undefined, set: (value) => { entry.category = value ?? '' } })

const categoryOptions = computed(() => store.categories.map((c) => ({ value: c.name, label: c.name })))
const accessOptions = computed(() => [
  { value: 'user', label: t('knowledge.upload.accessUser') },
  { value: 'system', label: t('knowledge.upload.accessSystem') },
  { value: 'general', label: t('knowledge.upload.accessGeneral') },
  { value: 'autobot', label: t('knowledge.upload.accessAutobot') },
])
const visibilityOptions = computed(() => [
  { value: 'private', label: t('knowledge.upload.visPrivate') },
  { value: 'shared', label: t('knowledge.upload.visShared') },
  { value: 'group', label: t('knowledge.upload.visGroup') },
  { value: 'organization', label: t('knowledge.upload.visOrganization') },
  { value: 'system', label: t('knowledge.upload.visSystem') },
])

async function submit(): Promise<void> {
  if (!entry.content.trim()) return
  // The org / team / shared-with fields are not collected in this form yet.
  const errorKey = accessLevelErrorKey(entry.visibility, {})
  if (errorKey) return props.feedback.showError(t(errorKey))

  props.feedback.begin()
  try {
    await controller.addTextDocument(entry.content, entry.title, entry.category, parseTags(entry.tagsInput), {
      access_level: entry.accessLevel,
      visibility: entry.visibility,
    })
    props.feedback.showSuccess(t('knowledge.upload.successTextAdded'))
    resetFormFields(entry)
  } catch (error: unknown) {
    props.feedback.showError((error as Error).message || t('knowledge.upload.errorAddText'))
  } finally {
    props.feedback.end()
  }
}
</script>
