<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  GH#10533: "My Reviews" — work items an agent (or human) handed to the current
  user for review (status in_review, reviewer_user_id == me). The landing queue
  for the agent→human review loop (FR-HYBRID-05). Clicking opens WorkItemDetail
  where the in_review → Approve/Request-Changes transitions live.
-->
<template>
  <div class="review-inbox">
    <LlcBreadcrumb :items="breadcrumb" />

    <header class="inbox-header">
      <h2 class="inbox-title">{{ $t('nav.llcReviewInbox') }}</h2>
      <span class="inbox-count">{{ items.length }}</span>
    </header>

    <div v-if="loading" class="inbox-state">{{ $t('common.loading') }}</div>
    <div v-else-if="!items.length" class="inbox-state">{{ $t('nav.llcReviewInboxEmpty') }}</div>

    <ul v-else class="review-list">
      <li v-for="item in items" :key="item.id">
        <button type="button" class="review-row" @click="detailItem = item">
          <span class="review-identifier">{{ item.identifier }}</span>
          <span class="review-title">{{ item.title }}</span>
          <span class="review-type">{{ item.type }}</span>
        </button>
      </li>
    </ul>

    <WorkItemDetail
      v-if="detailItem"
      :item="detailItem"
      :company-id="companyId"
      @close="detailItem = null"
      @updated="onItemUpdated"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useApiClient } from '@/plugins/api'
import { useUserStore } from '@/stores/useUserStore'
import { createLogger } from '@/utils/debugUtils'
import LlcBreadcrumb, { type BreadcrumbItem } from '@/components/llc/LlcBreadcrumb.vue'
import WorkItemDetail from './WorkItemDetail.vue'
import type { WorkItem } from './workItemTypes'

const route = useRoute()
const api = useApiClient()
const userStore = useUserStore()
const logger = createLogger('ReviewInboxView')

const companyId = computed(() => route.params.companyId as string)
const items = ref<WorkItem[]>([])
const loading = ref(false)
const detailItem = ref<WorkItem | null>(null)

const breadcrumb = computed<BreadcrumbItem[]>(() => [{ label: 'Company OS' }, { label: 'My Reviews' }])

async function load(): Promise<void> {
  const uid = userStore.currentUser?.id
  if (!uid) return
  loading.value = true
  try {
    items.value = await api.get<WorkItem[]>(
      `/api/llc/work-items?company_id=${companyId.value}&reviewer=${uid}&status=in_review`,
    )
  } catch (err) {
    logger.error('Failed to load review inbox', err)
    items.value = []
  } finally {
    loading.value = false
  }
}

function onItemUpdated(updated: WorkItem): void {
  // A reviewed item leaving in_review drops off the queue.
  if (updated.status !== 'in_review') {
    items.value = items.value.filter((i) => i.id !== updated.id)
    detailItem.value = null
  }
}

onMounted(load)
</script>

<style scoped>
.review-inbox {
  padding: 1.5rem;
}
.inbox-header {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  margin-bottom: 1rem;
}
.inbox-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--color-text-primary, #111827);
  margin: 0;
}
.inbox-count {
  font-size: 0.8125rem;
  color: var(--color-text-secondary, #9ca3af);
}
.inbox-state {
  padding: 2rem 0;
  color: var(--color-text-secondary, #9ca3af);
}
.review-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.review-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  text-align: left;
  border: 1px solid var(--border-default, #e5e7eb);
  border-radius: var(--radius-md, 8px);
  background: var(--bg-surface, #fff);
  cursor: pointer;
}
.review-row:hover {
  border-color: var(--color-accent, #c4651a);
}
.review-identifier {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-secondary, #6b7280);
}
.review-title {
  flex: 1;
  font-size: 0.9375rem;
  color: var(--color-text-primary, #111827);
}
.review-type {
  font-size: 0.6875rem;
  text-transform: uppercase;
  color: var(--color-text-secondary, #9ca3af);
}
</style>
