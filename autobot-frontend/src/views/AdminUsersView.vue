<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="admin-users-view view-container">
    <div class="page-header">
      <div class="page-header-content">
        <h2 class="page-title">User Management</h2>
        <p class="page-subtitle">Manage users, roles, and account status</p>
      </div>
      <div class="header-actions">
        <button class="btn-action-primary" @click="showCreateModal = true">
          <Icon name="user-plus" />
          Add User
        </button>
        <button class="btn-action-secondary" :disabled="loading" @click="loadUsers">
          <Icon name="sync-alt" :spin="loading" />
          Refresh
        </button>
      </div>
    </div>

    <div v-if="error" class="error-banner">
      <Icon name="exclamation-circle" />
      <span>{{ error }}</span>
      <button class="btn-dismiss" :aria-label="$t('common.dismiss')" @click="error = null"><Icon name="times" /></button>
    </div>

    <!-- Search bar -->
    <div class="search-bar">
      <Icon name="search" class="search-icon" />
      <input
        v-model="searchQuery"
        type="text"
        class="search-input"
        placeholder="Search by username, email, or name…"
        @input="debouncedSearch"
      />
    </div>

    <!-- Users table -->
    <div class="table-section">
      <div v-if="loading && users.length === 0" class="loading-state">
        <Icon name="sync-alt" :spin="true" /> Loading users…
      </div>

      <table v-else class="data-table">
        <thead>
          <tr>
            <th>Username</th>
            <th>Email</th>
            <th>Display Name</th>
            <th>Role</th>
            <th>Voice Bundle</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="user in users" :key="user.id">
            <td class="username-cell">
              <span class="username">{{ user.username }}</span>
              <span v-if="user.is_platform_admin" class="badge badge-admin">admin</span>
            </td>
            <td>{{ user.email }}</td>
            <td>{{ user.display_name || '—' }}</td>
            <td>
              <select
                class="role-select"
                :value="primaryRole(user)"
                @change="onRoleChange(user, ($event.target as HTMLSelectElement).value)"
              >
                <option value="admin">admin</option>
                <option value="user">user</option>
                <option value="readonly">readonly</option>
              </select>
            </td>
            <td class="bundle-cell">
              <span v-if="userBundles[user.id] !== undefined" class="badge badge-bundle">
                {{ userBundles[user.id] ? VOICE_BUNDLE_LABELS[userBundles[user.id]!] : '—' }}
              </span>
              <Icon v-else name="sync-alt" :spin="true" class="bundle-loading" />
            </td>
            <td>
              <span class="badge" :class="user.is_active ? 'badge-active' : 'badge-inactive'">
                {{ user.is_active ? 'active' : 'inactive' }}
              </span>
            </td>
            <td class="actions-cell">
              <button
                v-if="user.is_active"
                class="btn-icon btn-warning"
                title="Deactivate"
                @click="toggleActive(user, false)"
              >
                <Icon name="ban" />
              </button>
              <button
                v-else
                class="btn-icon btn-success"
                title="Activate"
                @click="toggleActive(user, true)"
              >
                <Icon name="check-circle" />
              </button>
              <button
                class="btn-icon btn-info"
                title="Assign Voice Bundle"
                @click="openBundleModal(user)"
              >
                <Icon name="microphone" />
              </button>
              <button
                class="btn-icon btn-danger"
                title="Delete"
                @click="confirmDelete(user)"
              >
                <Icon name="trash" />
              </button>
            </td>
          </tr>
          <tr v-if="!loading && users.length === 0">
            <td colspan="7" class="empty-row">No users found.</td>
          </tr>
        </tbody>
      </table>

      <!-- Pagination -->
      <div v-if="total > pageSize" class="pagination">
        <button
          :disabled="page === 0"
          class="btn-page"
          :aria-label="$t('common.previous')"
          @click="changePage(-1)"
        >
          <Icon name="chevron-left" />
        </button>
        <span class="page-info">{{ page + 1 }} / {{ totalPages }}</span>
        <button
          :disabled="page >= totalPages - 1"
          class="btn-page"
          :aria-label="$t('common.next')"
          @click="changePage(1)"
        >
          <Icon name="chevron-right" />
        </button>
      </div>
    </div>

    <!-- Create User Modal -->
    <div v-if="showCreateModal" class="modal-overlay" @click.self="showCreateModal = false">
      <div class="modal">
        <div class="modal-header">
          <h3>Add User</h3>
          <button
            class="btn-close"
            @click="showCreateModal = false"
            :aria-label="$t('common.close')"
            :title="$t('common.close')"
            type="button"
          ><Icon name="times" /></button>
        </div>
        <form class="modal-body" @submit.prevent="createUser">
          <div class="form-group">
            <label>Email</label>
            <input v-model="newUser.email" type="email" class="form-input" required />
          </div>
          <div class="form-group">
            <label>Username</label>
            <input v-model="newUser.username" type="text" class="form-input" required minlength="3" />
          </div>
          <div class="form-group">
            <label>Password</label>
            <input v-model="newUser.password" type="password" class="form-input" required minlength="8" />
          </div>
          <div class="form-group">
            <label>Display Name</label>
            <input v-model="newUser.display_name" type="text" class="form-input" />
          </div>
          <div v-if="createError" class="error-inline">{{ createError }}</div>
          <div class="modal-footer">
            <button type="button" class="btn-action-secondary" @click="showCreateModal = false">Cancel</button>
            <button type="submit" class="btn-action-primary" :disabled="creating">
              <Icon v-if="creating" name="sync-alt" :spin="true" />
              Create User
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Assign Voice Bundle Modal -->
    <div v-if="bundleTarget" class="modal-overlay" @click.self="closeBundleModal">
      <div class="modal modal-sm">
        <div class="modal-header">
          <h3>Assign Voice Bundle</h3>
          <button
            class="btn-close"
            @click="closeBundleModal"
            :aria-label="$t('common.close')"
            type="button"
          ><Icon name="times" /></button>
        </div>
        <div class="modal-body">
          <p class="bundle-user-name">
            User: <strong>{{ bundleTarget.username }}</strong>
          </p>
          <div class="form-group">
            <label>Voice Bundle</label>
            <select v-model="newBundleName" class="form-input">
              <option :value="null">— Use role default —</option>
              <option v-for="name in VOICE_BUNDLE_NAMES" :key="name" :value="name">
                {{ VOICE_BUNDLE_LABELS[name] }}
              </option>
            </select>
          </div>
          <div v-if="bundleError" class="error-inline">{{ bundleError }}</div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn-action-secondary" @click="closeBundleModal">Cancel</button>
          <button
            type="button"
            class="btn-action-primary"
            :disabled="bundleSaving || bundleModalLoading"
            @click="doAssignBundle"
          >
            <Icon v-if="bundleSaving || bundleModalLoading" name="sync-alt" :spin="true" />
            Save
          </button>
        </div>
      </div>
    </div>

    <!-- Delete Confirm Modal -->
    <div v-if="deleteTarget" class="modal-overlay" @click.self="deleteTarget = null">
      <div class="modal modal-sm">
        <div class="modal-header">
          <h3>Delete User</h3>
        </div>
        <div class="modal-body">
          <p>Delete <strong>{{ deleteTarget.username }}</strong>? This cannot be undone.</p>
        </div>
        <div class="modal-footer">
          <button class="btn-action-secondary" @click="deleteTarget = null">Cancel</button>
          <button class="btn-action-danger" @click="deleteUser">Delete</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getBackendUrl } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import Icon from '@/components/ui/Icon.vue'
import {
  useAdminVoiceBundle,
  VOICE_BUNDLE_NAMES,
  VOICE_BUNDLE_LABELS,
} from '@/composables/useVoiceBundle'
import type { VoiceBundleName } from '@/composables/useVoiceBundle'

const logger = createLogger('AdminUsersView')

interface UserRecord {
  id: string
  username: string
  email: string
  display_name: string | null
  is_active: boolean
  is_platform_admin: boolean
  roles: Array<{ name: string; is_system: boolean }>
}

interface NewUserForm {
  email: string
  username: string
  password: string
  display_name: string
}


const users = ref<UserRecord[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)
const searchQuery = ref('')
const page = ref(0)
const pageSize = 20

const showCreateModal = ref(false)
const creating = ref(false)
const createError = ref<string | null>(null)
const newUser = ref<NewUserForm>({ email: '', username: '', password: '', display_name: '' })

const deleteTarget = ref<UserRecord | null>(null)

// Voice bundle state
const { saving: bundleSaving, saveError: bundleError, assignBundle, getUserBundle } = useAdminVoiceBundle()
const userBundles = ref<Record<string, VoiceBundleName | null | undefined>>({})
const bundleTarget = ref<UserRecord | null>(null)
const newBundleName = ref<VoiceBundleName | null>(null)
// Stale-result guard: tracks which user's bundle fetch was initiated for the open modal
const bundleModalUserId = ref<string | null>(null)
const bundleModalLoading = ref(false)

const totalPages = computed(() => Math.ceil(total.value / pageSize))

function primaryRole(user: UserRecord): string {
  if (user.is_platform_admin) return 'admin'
  const sysRole = user.roles.find(r => r.is_system)
  return sysRole?.name ?? 'user'
}

async function loadUsers(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const params = new URLSearchParams({
      limit: String(pageSize),
      offset: String(page.value * pageSize),
    })
    if (searchQuery.value.trim()) {
      params.set('search', searchQuery.value.trim())
    }
    const res = await fetchWithAuth(`${getBackendUrl()}/user-management/users?${params}`)
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`)
    }
    const data = await res.json() as { users: UserRecord[]; total: number }
    users.value = data.users
    total.value = data.total
    loadUserBundles(data.users)
  } catch (err) {
    logger.error('Failed to load users:', err)
    error.value = err instanceof Error ? err.message : 'Failed to load users'
  } finally {
    loading.value = false
  }
}

function loadUserBundles(userList: UserRecord[]): void {
  const toFetch = userList.filter(u => userBundles.value[u.id] === undefined)
  if (toFetch.length === 0) return
  Promise.all(
    toFetch.map(user =>
      getUserBundle(user.id)
        .then(assignment => { userBundles.value[user.id] = assignment?.bundle_name ?? null })
        .catch(() => { userBundles.value[user.id] = null })
    )
  )
}

function openBundleModal(user: UserRecord): void {
  bundleTarget.value = user
  bundleModalUserId.value = user.id
  const cached = userBundles.value[user.id]
  if (cached !== undefined) {
    newBundleName.value = cached
    return
  }
  // loadUserBundles fetch for this user is still in flight — fetch it directly now
  // so the modal shows the real current value rather than null.
  // The bundleModalUserId guard discards the result if the modal is closed or
  // switched to a different user before this resolves.
  newBundleName.value = null
  bundleModalLoading.value = true
  getUserBundle(user.id)
    .then(assignment => {
      if (bundleModalUserId.value !== user.id) return
      const bundleName = assignment?.bundle_name ?? null
      userBundles.value[user.id] = bundleName
      newBundleName.value = bundleName
    })
    .catch(() => {
      if (bundleModalUserId.value !== user.id) return
      userBundles.value[user.id] = null
      newBundleName.value = null
    })
    .finally(() => {
      if (bundleModalUserId.value === user.id) bundleModalLoading.value = false
    })
}

function closeBundleModal(): void {
  bundleModalUserId.value = null
  bundleModalLoading.value = false
  bundleTarget.value = null
}

async function doAssignBundle(): Promise<void> {
  if (!bundleTarget.value) return
  const userId = bundleTarget.value.id
  const ok = await assignBundle(userId, newBundleName.value)
  if (ok) {
    userBundles.value[userId] = newBundleName.value
    closeBundleModal()
  }
}

let searchTimer: ReturnType<typeof setTimeout> | null = null
function debouncedSearch(): void {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 0
    loadUsers()
  }, 300)
}

function changePage(delta: number): void {
  page.value += delta
  loadUsers()
}

async function onRoleChange(user: UserRecord, role: string): Promise<void> {
  try {
    const res = await fetchWithAuth(`${getBackendUrl()}/user-management/users/${user.id}/role`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role }),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`)
    }
    await loadUsers()
  } catch (err) {
    logger.error('Failed to update role:', err)
    error.value = err instanceof Error ? err.message : 'Failed to update role'
  }
}

async function toggleActive(user: UserRecord, activate: boolean): Promise<void> {
  const action = activate ? 'activate' : 'deactivate'
  try {
    const res = await fetchWithAuth(`${getBackendUrl()}/user-management/users/${user.id}/${action}`, {
      method: 'POST',
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`)
    }
    await loadUsers()
  } catch (err) {
    logger.error(`Failed to ${action} user:`, err)
    error.value = err instanceof Error ? err.message : `Failed to ${action} user`
  }
}

function confirmDelete(user: UserRecord): void {
  deleteTarget.value = user
}

async function deleteUser(): Promise<void> {
  if (!deleteTarget.value) return
  try {
    const res = await fetchWithAuth(`${getBackendUrl()}/user-management/users/${deleteTarget.value.id}`, {
      method: 'DELETE',
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`)
    }
    deleteTarget.value = null
    await loadUsers()
  } catch (err) {
    logger.error('Failed to delete user:', err)
    error.value = err instanceof Error ? err.message : 'Failed to delete user'
    deleteTarget.value = null
  }
}

async function createUser(): Promise<void> {
  creating.value = true
  createError.value = null
  try {
    const res = await fetchWithAuth(`${getBackendUrl()}/user-management/users`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: newUser.value.email,
        username: newUser.value.username,
        password: newUser.value.password,
        display_name: newUser.value.display_name || undefined,
      }),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`)
    }
    showCreateModal.value = false
    newUser.value = { email: '', username: '', password: '', display_name: '' }
    await loadUsers()
  } catch (err) {
    logger.error('Failed to create user:', err)
    createError.value = err instanceof Error ? err.message : 'Failed to create user'
  } finally {
    creating.value = false
  }
}

onMounted(loadUsers)
</script>

<style scoped>
.admin-users-view {
  padding: var(--spacing-6);
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: var(--spacing-6);
  gap: var(--spacing-4);
  flex-wrap: wrap;
}

.page-title {
  font-size: var(--text-2xl);
  font-weight: 600;
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-1);
}

.page-subtitle {
  font-size: var(--text-sm);
  color: var(--color-text-secondary, #6b7280);
  margin: var(--spacing-0);
}

.header-actions {
  display: flex;
  gap: var(--spacing-2);
}

.error-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-4);
  background: var(--color-error-bg, #fef2f2);
  border: 1px solid var(--color-error-border, #fca5a5);
  border-radius: var(--radius-lg);
  margin-bottom: var(--spacing-4);
  color: var(--color-error, #dc2626);
}

.btn-dismiss {
  margin-left: auto;
  background: none;
  border: none;
  cursor: pointer;
  color: inherit;
}

.search-bar {
  position: relative;
  margin-bottom: var(--spacing-4);
}

.search-icon {
  position: absolute;
  left: 0.75rem;
  top: 50%;
  transform: translateY(-50%);
  color: var(--color-text-secondary, #6b7280);
}

.search-input {
  width: 100%;
  padding: var(--spacing-2) var(--spacing-3) var(--spacing-2) var(--spacing-9);
  border: 1px solid var(--color-border, #d1d5db);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  box-sizing: border-box;
}

.table-section {
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: var(--radius-xl);
  overflow: hidden;
}

.loading-state {
  padding: var(--spacing-8);
  text-align: center;
  color: var(--color-text-secondary, #6b7280);
}

.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table th {
  text-align: left;
  padding: var(--spacing-3) var(--spacing-4);
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-secondary, #6b7280);
  background: var(--color-surface-alt, #f9fafb);
  border-bottom: 1px solid var(--color-border, #e5e7eb);
}

.data-table td {
  padding: var(--spacing-3) var(--spacing-4);
  border-bottom: 1px solid var(--color-border, #f3f4f6);
  font-size: var(--text-sm);
}

.data-table tr:last-child td {
  border-bottom: none;
}

.username-cell {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.username {
  font-weight: 500;
}

.badge {
  display: inline-block;
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-full);
  font-size: 0.7rem;
  font-weight: 600;
}

.badge-admin {
  background: var(--color-warning-bg, #fffbeb);
  color: var(--color-warning, #d97706);
}

.badge-active {
  background: var(--color-success-bg, #f0fdf4);
  color: var(--color-success, #16a34a);
}

.badge-inactive {
  background: var(--color-error-bg, #fef2f2);
  color: var(--color-error, #dc2626);
}

.badge-bundle {
  background: var(--color-info-bg, #eff6ff);
  color: var(--color-info, #2563eb);
  white-space: nowrap;
}

.bundle-cell {
  min-width: 8rem;
}

.bundle-loading {
  font-size: var(--text-xs);
  color: var(--color-text-secondary, #6b7280);
}

.bundle-user-name {
  margin: 0 0 var(--spacing-4);
  font-size: var(--text-sm);
}

.role-select {
  padding: var(--spacing-1) var(--spacing-2);
  border: 1px solid var(--color-border, #d1d5db);
  border-radius: var(--radius-md);
  font-size: 0.8125rem;
  background: transparent;
}

.actions-cell {
  display: flex;
  gap: var(--spacing-1);
}

.btn-icon {
  width: 2rem;
  height: 2rem;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xs);
}

.btn-warning {
  background: var(--color-warning-bg, #fffbeb);
  color: var(--color-warning, #d97706);
}

.btn-info {
  background: var(--color-info-bg, #eff6ff);
  color: var(--color-info, #2563eb);
}

.btn-success {
  background: var(--color-success-bg, #f0fdf4);
  color: var(--color-success, #16a34a);
}

.btn-danger {
  background: var(--color-error-bg, #fef2f2);
  color: var(--color-error, #dc2626);
}

.empty-row {
  text-align: center;
  color: var(--color-text-secondary, #6b7280);
  padding: 2rem !important;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-4);
  padding: var(--spacing-3);
  border-top: 1px solid var(--color-border, #e5e7eb);
}

.btn-page {
  padding: var(--spacing-1-5) var(--spacing-3);
  border: 1px solid var(--color-border, #d1d5db);
  border-radius: var(--radius-md);
  background: transparent;
  cursor: pointer;
}

.btn-page:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.page-info {
  font-size: var(--text-sm);
  color: var(--color-text-secondary, #6b7280);
}

.btn-action-primary,
.btn-action-secondary,
.btn-action-danger {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1-5);
  padding: var(--spacing-2) var(--spacing-4);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 500;
  border: 1px solid transparent;
  cursor: pointer;
}

.btn-action-primary {
  background: var(--color-primary, #2563eb);
  color: #fff;
}

.btn-action-secondary {
  background: transparent;
  border-color: var(--color-border, #d1d5db);
  color: var(--color-text, #111827);
}

.btn-action-danger {
  background: var(--color-error, #dc2626);
  color: #fff;
}

.btn-action-primary:disabled,
.btn-action-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
}

.modal {
  background: var(--color-surface, #fff);
  border-radius: var(--radius-xl);
  width: 100%;
  max-width: 480px;
  box-shadow: var(--shadow-2xl);
}

.modal-sm {
  max-width: 360px;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-4) var(--spacing-5);
  border-bottom: 1px solid var(--color-border, #e5e7eb);
}

.modal-header h3 {
  margin: var(--spacing-0);
  font-size: var(--text-base);
  font-weight: 600;
}

.btn-close {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--color-text-secondary, #6b7280);
  font-size: var(--text-sm);
}

.modal-body {
  padding: var(--spacing-5);
}

.form-group {
  margin-bottom: var(--spacing-4);
}

.form-group label {
  display: block;
  margin-bottom: var(--spacing-1-5);
  font-size: var(--text-sm);
  font-weight: 500;
}

.form-input {
  width: 100%;
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--color-border, #d1d5db);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  box-sizing: border-box;
}

.error-inline {
  color: var(--color-error, #dc2626);
  font-size: 0.8125rem;
  margin-top: var(--spacing-2);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-2);
  padding-top: var(--spacing-4);
}
</style>
