<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  KnowledgeEntriesTable — the Manage entries table on the kit BaseTable (#18244, #17562). The
  parent owns the order, the page and the selection (the bulk toolbar needs them); this renders
  the rows it is given, one page at a time, with a header sort the parent reacts to.
-->
<template>
  <BaseTable
    :columns="columns"
    :rows="(documents as unknown as TableRow[])"
    :caption="$t('knowledge.entries.tableCaption')"
    :loading="loading"
    :loading-label="$t('knowledge.entries.loadingEntries')"
    :empty-title="$t('knowledge.entries.noEntriesFound')"
    :empty-description="emptyDescription"
    :actions-label="$t('knowledge.entries.thActions')"
    :sort-key="sortKey"
    :sort-order="sortOrder"
    :page="page"
    :page-size="pageSize"
    :pagination-labels="{ previous: $t('knowledge.entries.previousPage'), next: $t('knowledge.entries.nextPage') }"
    :pagination-label="$t('knowledge.entries.paginationLabel')"
    :pagination-summary="summary"
    @sort="(key, order) => emit('sort', key, order)"
    @update:page="emit('update:page', $event)"
  >
    <template #cell-select="{ row }">
      <input
        type="checkbox"
        class="accent-[var(--accent)]"
        :checked="isSelected(doc(row))"
        :aria-label="$t('knowledge.entries.selectEntry', { title: doc(row).title || $t('knowledge.entries.untitled') })"
        @change="emit('toggle', doc(row))"
      />
    </template>
    <template #cell-title="{ row }">
      <button type="button" class="entry-title cursor-pointer border-0 bg-transparent p-0 text-start text-[var(--accent)] hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]" @click="emit('preview', doc(row))">
        {{ formatManPageTitle(doc(row).title, doc(row).metadata?.factType, $t) || $t('knowledge.entries.untitled') }}
      </button>
      <BaseBadge
        v-if="verificationOf(doc(row))"
        :variant="VERIFICATION_VARIANT[verificationOf(doc(row))!] ?? 'neutral'"
        size="sm"
        :label="verificationLabel(doc(row))"
      />
    </template>
    <template #cell-category="{ row }"><BaseBadge :label="doc(row).category" /></template>
    <template #cell-type="{ row }">
      <span class="inline-flex items-center gap-1">
        <Icon :name="getDocumentTypeIcon(doc(row).type)" aria-hidden="true" />{{ doc(row).type }}
      </span>
    </template>
    <template #cell-tags="{ row }">
      <span class="inline-flex items-center gap-1">
        <BaseBadge v-for="tag in doc(row).tags.slice(0, MAX_TAGS)" :key="tag" :label="tag" size="sm" />
        <span v-if="doc(row).tags.length > MAX_TAGS">+{{ doc(row).tags.length - MAX_TAGS }}</span>
      </span>
    </template>
    <template #actions="{ row }">
      <BaseButton variant="ghost" size="xs" :aria-label="$t('knowledge.entries.viewBtn')" @click="emit('view', doc(row))">
        <Icon name="eye" aria-hidden="true" />
      </BaseButton>
      <BaseButton variant="ghost" size="xs" :aria-label="$t('knowledge.entries.editBtn')" @click="emit('edit', doc(row))">
        <Icon name="edit" aria-hidden="true" />
      </BaseButton>
      <BaseButton variant="ghost" size="xs" :aria-label="$t('knowledge.entries.deleteBtn')" @click="emit('delete', doc(row))">
        <Icon name="trash" aria-hidden="true" />
      </BaseButton>
    </template>
  </BaseTable>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseBadge, BaseButton, BaseTable } from '@autobot/ui'
import type { BaseTableColumn, SortOrder, TableRow } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import type { KnowledgeDocument } from '@/stores/useKnowledgeStore'
import { formatDate, formatManPageTitle } from '@/utils/formatHelpers'
import { getDocumentTypeIconName as getDocumentTypeIcon } from '@/utils/iconMappings'

const props = defineProps<{
  documents: KnowledgeDocument[]
  loading: boolean
  page: number
  pageSize: number
  sortKey: string
  sortOrder: SortOrder
  emptyDescription: string
  total: number
  isSelected: (doc: KnowledgeDocument) => boolean
}>()

const emit = defineEmits<{
  sort: [key: string, order: SortOrder]
  'update:page': [page: number]
  toggle: [doc: KnowledgeDocument]
  preview: [doc: KnowledgeDocument]
  view: [doc: KnowledgeDocument]
  edit: [doc: KnowledgeDocument]
  delete: [doc: KnowledgeDocument]
}>()

const { t } = useI18n()
const MAX_TAGS = 3
const VERIFICATION_VARIANT: Record<string, 'success' | 'warning' | 'error' | 'neutral'> = {
  verified: 'success',
  pending_review: 'warning',
  rejected: 'error',
  unverified: 'neutral',
}

const columns = computed<BaseTableColumn[]>(() => [
  { key: 'select', label: t('knowledge.entries.thSelect'), hideable: false },
  { key: 'title', label: t('knowledge.entries.thTitle'), sortable: true, wrap: true, hideable: false },
  { key: 'category', label: t('knowledge.entries.thCategory'), sortable: true },
  { key: 'type', label: t('knowledge.entries.thType') },
  { key: 'tags', label: t('knowledge.entries.thTags') },
  { key: 'updatedAt', label: t('knowledge.entries.thUpdated'), sortable: true, monospace: true, formatter: (v) => formatDate(v as Date) },
])

const doc = (row: TableRow) => row as unknown as KnowledgeDocument
const verificationOf = (d: KnowledgeDocument): string | undefined =>
  (d.metadata as Record<string, unknown> | undefined)?.verification_status as string | undefined
const verificationLabel = (d: KnowledgeDocument): string =>
  ({
    verified: t('knowledge.entries.verified'),
    pending_review: t('knowledge.entries.pendingReview'),
    unverified: t('knowledge.entries.unverified'),
    rejected: t('knowledge.entries.rejected'),
  })[verificationOf(d) ?? ''] ?? t('knowledge.entries.unknown')

const summary = (current: number, total: number) =>
  t('knowledge.entries.pageInfo', { current, total, count: props.total })
</script>
