<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<!-- Author: mrveiss -->
<!--
  SharedLinksAdminView — admin cross-user view of all active shared chat links
  (GH#8996, AC4). Read-only table listing every active, non-expired shared link
  with its owner, session, timestamps, and password-protection state.
-->
<template>
  <div class="shared-links-admin view-container">
    <div class="page-header">
      <div class="page-header-content">
        <h2 class="page-title">Shared Chat Links</h2>
        <p class="page-subtitle">All active public chat links across every user</p>
      </div>
      <div class="header-actions">
        <button class="btn-action-secondary" :disabled="loading" @click="fetchLinks()">
          <Icon name="sync-alt" :spin="loading" />
          Refresh
        </button>
      </div>
    </div>

    <!-- Error banner -->
    <div v-if="error" class="error-banner" role="alert">
      <Icon name="exclamation-circle" />
      <span>{{ error }}</span>
      <button class="btn-dismiss" aria-label="Dismiss" @click="error = null">
        <Icon name="times" />
      </button>
    </div>

    <!-- Loading state -->
    <div v-if="loading && links.length === 0" class="loading-state">
      <Icon name="sync-alt" :spin="true" /> Loading shared links…
    </div>

    <!-- Empty state -->
    <div v-else-if="!loading && links.length === 0" class="empty-state">
      <Icon name="link" class="empty-icon" />
      <p>No active shared links.</p>
    </div>

    <!-- Links table -->
    <div v-else class="table-wrap">
      <table class="links-table">
        <caption class="sr-only">Active shared chat links across all users</caption>
        <thead>
          <tr>
            <th scope="col">Owner</th>
            <th scope="col">Session</th>
            <th scope="col">Created</th>
            <th scope="col">Expires</th>
            <th scope="col">Password</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="link in links" :key="link.id">
            <td>{{ link.owner }}</td>
            <td><code>{{ link.session_id }}</code></td>
            <td>{{ formatDate(link.created_at) }}</td>
            <td>{{ link.expires_at ? formatDate(link.expires_at) : 'Never' }}</td>
            <td>
              <span :class="['badge', link.has_password ? 'badge-on' : 'badge-off']">
                {{ link.has_password ? 'Protected' : 'Open' }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
      <p class="count-hint">{{ count }} active link{{ count === 1 ? '' : 's' }}.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import Icon from '@/components/ui/Icon.vue'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('SharedLinksAdminView')

interface SharedLinkAdminItem {
  id: string
  token: string
  session_id: string
  owner: string
  has_password: boolean
  expires_at: string | null
  created_at: string
}

// Envelope from create_success_response: { success, data: { links, count }, message, timestamp }
interface SharedLinksAdminResponse {
  success: boolean
  data: { links: SharedLinkAdminItem[]; count: number }
  message: string
}

const links = ref<SharedLinkAdminItem[]>([])
const count = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

async function fetchLinks(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    // ApiClient.get() returns parsed JSON directly — no .data/.json() envelope.
    const response: SharedLinksAdminResponse = await apiClient.get(
      `${getApiBase()}/chat/shared-links/admin`
    )
    links.value = response.data?.links ?? []
    count.value = response.data?.count ?? links.value.length
  } catch (e) {
    const message = e instanceof Error ? e.message : 'Failed to load shared links'
    error.value = message
    logger.error('Failed to fetch shared links', e)
  } finally {
    loading.value = false
  }
}

onMounted(() => fetchLinks())
</script>

<style scoped>
.shared-links-admin {
  padding: 1.5rem;
}

.error-banner {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  margin-bottom: 1rem;
  border-radius: 0.5rem;
  background: rgba(239, 68, 68, 0.12);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: #fca5a5;
}

.error-banner .btn-dismiss {
  margin-left: auto;
  background: none;
  border: none;
  cursor: pointer;
  color: inherit;
  padding: 0;
  line-height: 1;
}

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  padding: 3rem 1rem;
  color: var(--text-secondary, rgba(255, 255, 255, 0.5));
}

.empty-icon {
  font-size: 2rem;
  opacity: 0.4;
}

.table-wrap {
  overflow-x: auto;
}

.links-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.links-table th,
.links-table td {
  text-align: left;
  padding: 0.6rem 0.75rem;
  border-bottom: 1px solid var(--border-color, rgba(255, 255, 255, 0.1));
}

.links-table th {
  color: var(--text-secondary, rgba(255, 255, 255, 0.6));
  font-weight: 600;
}

.links-table code {
  font-size: 0.8rem;
}

.badge {
  display: inline-block;
  padding: 0.1rem 0.5rem;
  border-radius: 9999px;
  font-size: 0.75rem;
}

.badge-on {
  background: rgba(34, 197, 94, 0.15);
  color: #86efac;
}

.badge-off {
  background: rgba(148, 163, 184, 0.15);
  color: #cbd5e1;
}

.count-hint {
  margin-top: 1rem;
  font-size: 0.8rem;
  color: var(--text-secondary, rgba(255, 255, 255, 0.4));
  text-align: right;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>
