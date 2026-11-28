<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  KnowledgeEntryDialog — view or edit one Manage entry (#18244). The edit form is local to this
  dialog and leaves it only as the `save` payload. Saving needs the full server content
  (`canSave`, #17530); without it the dialog says why and offers no save.
-->
<template>
  <BaseModal
    :model-value="modelValue"
    :close-label="$t('ui.modal.closeDialog')"
    :title="mode === 'view' ? $t('knowledge.entries.viewEntry') : $t('knowledge.entries.editEntry')"
    size="lg"
    scrollable
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-if="entry && mode === 'view'">
      <dl class="mb-4 mt-0 grid grid-cols-[repeat(auto-fit,minmax(12rem,1fr))] gap-3">
        <div>
          <dt class="text-xs text-[var(--muted)]">{{ $t('knowledge.entries.titleLabel') }}</dt>
          <dd class="m-0 text-[var(--text)]">{{ formatManPageTitle(entry.title, entry.metadata?.factType, $t) || $t('knowledge.entries.untitled') }}</dd>
        </div>
        <div>
          <dt class="text-xs text-[var(--muted)]">{{ $t('knowledge.entries.categoryViewLabel') }}</dt>
          <dd class="m-0 text-[var(--text)]"><BaseBadge :label="entry.category" /></dd>
        </div>
        <div>
          <dt class="text-xs text-[var(--muted)]">{{ $t('knowledge.entries.typeViewLabel') }}</dt>
          <dd class="m-0 text-[var(--text)]"><BaseBadge :label="entry.type" /></dd>
        </div>
        <div>
          <dt class="text-xs text-[var(--muted)]">{{ $t('knowledge.entries.sourceLabel') }}</dt>
          <dd class="m-0 text-[var(--text)]">{{ entry.source }}</dd>
        </div>
        <div>
          <dt class="text-xs text-[var(--muted)]">{{ $t('knowledge.entries.createdLabel') }}</dt>
          <dd class="m-0 text-[var(--text)]">{{ formatDateTime(entry.createdAt) }}</dd>
        </div>
        <div>
          <dt class="text-xs text-[var(--muted)]">{{ $t('knowledge.entries.updatedLabel') }}</dt>
          <dd class="m-0 text-[var(--text)]">{{ formatDateTime(entry.updatedAt) }}</dd>
        </div>
        <div v-if="entry.tags.length > 0">
          <dt class="text-xs text-[var(--muted)]">{{ $t('knowledge.entries.tagsLabel') }}</dt>
          <dd class="m-0 flex flex-wrap gap-1"><BaseBadge v-for="tag in entry.tags" :key="tag" :label="tag" size="sm" /></dd>
        </div>
      </dl>
      <h4 class="mb-2 mt-0 text-[var(--text)]">{{ $t('knowledge.entries.content') }}</h4>
      <div class="content-viewer max-h-96 overflow-y-auto rounded-md border border-[var(--border)] bg-[var(--surface2)] p-3 text-[var(--text)]" v-html="formatContent(entry.content)"></div>
    </div>

    <form v-else-if="entry" class="flex flex-col gap-4" @submit.prevent="onSave">
      <BaseAlert v-if="!canSave" variant="warning">{{ $t('knowledge.entries.contentNotLoaded') }}</BaseAlert>
      <BaseInput v-model="form.title" :label="$t('knowledge.entries.editTitle')" />
      <div class="grid grid-cols-2 gap-3">
        <BaseSelectMenu
          v-model="form.category"
          :label="$t('knowledge.entries.editCategory')"
          :options="categoryOptions"
        />
        <BaseInput v-model="form.source" :label="$t('knowledge.entries.editSource')" />
      </div>
      <BaseInput
        v-model="form.tagsInput"
        :label="$t('knowledge.entries.editTags')"
        :placeholder="$t('knowledge.entries.editTagsPlaceholder')"
      />
      <BaseFormField :label="$t('knowledge.entries.editContent')">
        <template #default="{ id, describedBy }">
          <textarea :id="id" v-model="form.content" class="w-full rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-[var(--text)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]" rows="10" :aria-describedby="describedBy" />
        </template>
      </BaseFormField>
    </form>

    <template #actions>
      <BaseButton v-if="mode === 'view'" variant="outline" @click="emit('export')">
        <Icon name="download" aria-hidden="true" />{{ $t('knowledge.entries.exportBtn') }}
      </BaseButton>
      <BaseButton v-if="mode === 'view'" variant="primary" @click="emit('edit')">
        <Icon name="edit" aria-hidden="true" />{{ $t('knowledge.entries.editBtn') }}
      </BaseButton>
      <BaseButton v-if="mode === 'edit'" variant="secondary" @click="emit('cancel')">
        {{ $t('knowledge.entries.cancel') }}
      </BaseButton>
      <BaseButton v-if="mode === 'edit'" variant="primary" :disabled="!canSave" @click="onSave">
        {{ $t('knowledge.entries.saveChanges') }}
      </BaseButton>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { BaseAlert, BaseBadge, BaseButton, BaseFormField, BaseInput, BaseModal, BaseSelectMenu } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import type { KnowledgeCategory, KnowledgeDocument } from '@/stores/useKnowledgeStore'
import type { EntryEdit } from '@/composables/knowledge/useKnowledgeEntryDialog'
import { formatDateTime, formatManPageTitle } from '@/utils/formatHelpers'
import { escapeHtml, sanitizeKnowledgeHtml } from '@/utils/sanitize'

const props = defineProps<{
  modelValue: boolean
  mode: 'view' | 'edit'
  entry: KnowledgeDocument | null
  categories: KnowledgeCategory[]
  canSave: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [open: boolean]
  edit: []
  cancel: []
  export: []
  save: [edit: EntryEdit]
}>()

const form = reactive({ title: '', category: '', source: '', content: '', tagsInput: '' })
const categoryOptions = computed(() => props.categories.map((c) => ({ value: c.name, label: c.name })))

// The form starts from the document each time the dialog enters edit mode.
watch(
  () => [props.mode, props.entry] as const,
  ([mode, entry]) => {
    if (mode !== 'edit' || !entry) return
    Object.assign(form, {
      title: entry.title || '',
      category: entry.category,
      source: entry.source,
      content: entry.content,
      tagsInput: entry.tags.join(', '),
    })
  },
  { immediate: true },
)

function onSave(): void {
  if (!props.canSave) return
  const tags = form.tagsInput.split(',').map((tag) => tag.trim()).filter((tag) => tag.length > 0)
  emit('save', { title: form.title, category: form.category, source: form.source, content: form.content, tags })
}

function formatContent(content: string): string {
  // #19118: escape, format, then sanitise (#2847 sanitiser) - stored content is untrusted
  return sanitizeKnowledgeHtml(
    escapeHtml(content)
      .replace(/\n/g, '<br>')
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/`(.*?)`/g, '<code>$1</code>'),
  )
}
</script>
