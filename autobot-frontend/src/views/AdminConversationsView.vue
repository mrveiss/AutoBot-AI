<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  AutoBot - AI-Powered Automation Platform
  Author: mrveiss

  Org conversation review (#17832). The org-scoped session list and the transcript
  read were built, gated and audited at the API with no GUI. This screen only calls
  them: the server decides who may list or open (administrative role AND the
  session's org matching the caller's) and audits each transcript open. The route's
  admin gate is presentation; a refusal from the server is shown as a refusal.
-->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  BaseAlert,
  BaseButton,
  BaseDrawer,
  BasePagination,
  BaseSkeleton,
  BaseTable,
  EmptyState,
  PageHeader,
  isHttpError,
  type BaseTableColumn,
} from '@autobot/ui'
import {
  TRANSCRIPT_PAGE_SIZE,
  useOrgConversationReview,
  type OrgSession,
  type OrgSessionsData,
  type TranscriptData,
} from '@/composables/useOrgConversationReview'
import { formatDateTime } from '@/utils/formatHelpers'

const { t } = useI18n()
const { listOrgSessions, openTranscript } = useOrgConversationReview()

type Failure = 'refused' | 'failed'

const loading = ref(true)
const listFailure = ref<Failure | null>(null)
const data = ref<OrgSessionsData | null>(null)

const sessions = computed<OrgSession[]>(() => data.value?.sessions ?? [])
// The server answers an admin with no organization with an empty list and no org_id.
const noOrganization = computed(() => data.value !== null && !data.value.org_id)

const columns = computed<BaseTableColumn[]>(() => [
  { key: 'title', label: t('admin.conversations.colTitle'), wrap: true },
  { key: 'messageCount', label: t('admin.conversations.colMessages'), numeric: true },
  { key: 'lastModified', label: t('admin.conversations.colUpdated') },
  { key: 'id', label: t('admin.conversations.colId'), monospace: true },
])

const rows = computed(() =>
  sessions.value.map((s) => ({
    id: s.id ?? s.chatId ?? '',
    title: s.title || s.name || t('admin.conversations.untitled'),
    messageCount: s.messageCount ?? null,
    lastModified: s.lastModified || s.updatedAt ? formatDateTime(s.lastModified || s.updatedAt) : '',
  })),
)

// 401/403 and the 400 the API returns for a non-admin role are the server's refusal.
function classify(err: unknown): Failure {
  return isHttpError(err) && [400, 401, 403].includes(err.status) ? 'refused' : 'failed'
}

async function load(): Promise<void> {
  loading.value = true
  listFailure.value = null
  try {
    data.value = await listOrgSessions()
  } catch (err) {
    data.value = null
    listFailure.value = classify(err)
  } finally {
    loading.value = false
  }
}

const open = ref(false)
const openRow = ref<{ id: string; title: string } | null>(null)
const transcript = ref<TranscriptData | null>(null)
const transcriptLoading = ref(false)
const transcriptFailure = ref<Failure | 'missing' | null>(null)
const page = ref(1)
const totalPages = computed(() =>
  Math.max(1, Math.ceil((transcript.value?.total_count ?? 0) / TRANSCRIPT_PAGE_SIZE)),
)

async function loadTranscript(): Promise<void> {
  if (!openRow.value) return
  transcriptLoading.value = true
  transcriptFailure.value = null
  try {
    transcript.value = await openTranscript(openRow.value.id, page.value)
  } catch (err) {
    transcript.value = null
    transcriptFailure.value = isHttpError(err) && err.status === 404 ? 'missing' : classify(err)
  } finally {
    transcriptLoading.value = false
  }
}

function openSession(row: Record<string, unknown>): void {
  openRow.value = { id: String(row.id), title: String(row.title) }
  page.value = 1
  transcript.value = null
  open.value = true
  void loadTranscript()
}

function changePage(next: number): void {
  page.value = next
  void loadTranscript()
}

function whenLabel(ts: string | null | undefined): string {
  return ts ? formatDateTime(ts) : ''
}

onMounted(load)
</script>

<template>
  <div class="p-6 space-y-4">
    <PageHeader
      :title="t('admin.conversations.title')"
      :subtitle="t('admin.conversations.subtitle')"
    />

    <BaseAlert variant="info" :message="t('admin.conversations.auditNotice')" />

    <BaseAlert
      v-if="listFailure === 'refused'"
      variant="warning"
      :title="t('admin.conversations.refusedTitle')"
      :message="t('admin.conversations.refusedBody')"
    />
    <BaseAlert
      v-else-if="listFailure === 'failed'"
      variant="error"
      :title="t('admin.conversations.failedTitle')"
      :message="t('admin.conversations.failedBody')"
    >
      <template #actions>
        <BaseButton size="sm" variant="secondary" @click="load">{{ t('common.retry') }}</BaseButton>
      </template>
    </BaseAlert>

    <EmptyState
      v-else-if="noOrganization"
      :title="t('admin.conversations.noOrgTitle')"
      :description="t('admin.conversations.noOrgBody')"
    />

    <BaseTable
      v-else
      :columns="columns"
      :rows="rows"
      :loading="loading"
      :loading-label="t('admin.conversations.loading')"
      :aria-label="t('admin.conversations.title')"
      :empty-title="t('admin.conversations.emptyTitle')"
      :empty-description="t('admin.conversations.emptyBody')"
      :actions-label="t('common.actions')"
    >
      <template #actions="{ row }">
        <BaseButton size="sm" variant="secondary" @click="openSession(row)">
          {{ t('admin.conversations.openTranscript') }}
        </BaseButton>
      </template>
    </BaseTable>

    <BaseDrawer
      v-model="open"
      :title="openRow?.title ?? t('admin.conversations.transcript')"
      :close-label="t('common.close')"
      width="40rem"
    >
      <div class="space-y-3">
        <BaseAlert variant="info" size="compact" :message="t('admin.conversations.openAudited')" />

        <BaseSkeleton v-if="transcriptLoading" shape="line" :lines="5" />

        <BaseAlert
          v-else-if="transcriptFailure === 'refused'"
          variant="warning"
          :title="t('admin.conversations.transcriptRefusedTitle')"
          :message="t('admin.conversations.transcriptRefusedBody')"
        />
        <BaseAlert
          v-else-if="transcriptFailure === 'missing'"
          variant="warning"
          :message="t('admin.conversations.transcriptMissing')"
        />
        <BaseAlert
          v-else-if="transcriptFailure === 'failed'"
          variant="error"
          :title="t('admin.conversations.failedTitle')"
          :message="t('admin.conversations.transcriptFailedBody')"
        >
          <template #actions>
            <BaseButton size="sm" variant="secondary" @click="loadTranscript">
              {{ t('common.retry') }}
            </BaseButton>
          </template>
        </BaseAlert>

        <EmptyState
          v-else-if="!transcript || transcript.messages.length === 0"
          :title="t('admin.conversations.noMessagesTitle')"
          :description="t('admin.conversations.noMessagesBody')"
        />

        <template v-else>
          <ol class="space-y-3 list-none p-0 m-0">
            <li
              v-for="(m, i) in transcript.messages"
              :key="m.id ?? i"
              class="border border-autobot-border rounded-lg bg-autobot-bg-card p-3"
            >
              <div class="flex items-center justify-between gap-2 text-xs text-autobot-text-muted mb-1">
                <span class="font-semibold uppercase tracking-wide text-autobot-text-secondary">
                  {{ m.sender || t('admin.conversations.unknownSender') }}
                </span>
                <time v-if="m.timestamp">{{ whenLabel(m.timestamp) }}</time>
              </div>
              <p class="text-sm text-autobot-text-primary whitespace-pre-wrap break-words m-0">
                {{ m.text }}
              </p>
            </li>
          </ol>
          <BasePagination
            v-if="totalPages > 1"
            :page="page"
            :total-pages="totalPages"
            :disabled="transcriptLoading"
            :labels="{ previous: t('common.previous'), next: t('common.next') }"
            :label="t('admin.conversations.transcriptPages')"
            @update:page="changePage"
          />
        </template>
      </div>
    </BaseDrawer>
  </div>
</template>
