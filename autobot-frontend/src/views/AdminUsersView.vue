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
          <i class="fas fa-user-plus"></i>
          Add User
        </button>
        <button class="btn-action-secondary" :disabled="loading" @click="loadUsers">
          <i class="fas fa-sync-alt" :class="{ 'fa-spin': loading }"></i>
          Refresh
        </button>
      </div>
    </div>

    <div v-if="error" class="error-banner">
      <i class="fas fa-exclamation-circle"></i>
      <span>{{ error }}</span>
      <button class="btn-dismiss" @click="error = null"><i class="fas fa-times"></i></button>
    </div>

    <!-- Search bar -->
    <div class="search-bar">
      <i class="fas fa-search search-icon"></i>
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
        <i class="fas fa-spinner fa-spin"></i> Loading users…
      </div>

      <table v-else class="data-table">
        <thead>
          <tr>
            <th>Username</th>
            <th>Email</th>
            <th>Display Name</th>
            <th>Role</th>
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
                <i class="fas fa-ban"></i>
              </button>
              <button
                v-else
                class="btn-icon btn-success"
                title="Activate"
                @click="toggleActive(user, true)"
              >
                <i class="fas fa-check-circle"></i>
              </button>
              <button
                class="btn-icon btn-danger"
                title="Delete"
                @click="confirmDelete(user)"
              >
                <i class="fas fa-trash"></i>
              </button>
            </td>
          </tr>
          <tr v-if="!loading && users.length === 0">
            <td colspan="6" class="empty-row">No users found.</td>
          </tr>
        </tbody>
      </table>

      <!-- Pagination -->
      <div v-if="total > pageSize" class="pagination">
        <button :disabled="page === 0" class="btn-page" @click="changePage(-1)">
          <i class="fas fa-chevron-left"></i>
        </button>
        <span class="page-info">{{ page + 1 }} / {{ totalPages }}</span>
        <button :disabled="page >= totalPages - 1" class="btn-page" @click="changePage(1)">
          <i class="fas fa-chevron-right"></i>
        </button>
      </div>
    </div>

    <!-- Create User Modal -->
    <div v-if="showCreateModal" class="modal-overlay" @click.self="showCreateModal = false">
      <div class="modal">
        <div class="modal-header">
          <h3>Add User</h3>
          <button class="btn-close" @click="showCreateModal = false"><i class="fas fa-times"></i></button>
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
              <i v-if="creating" class="fas fa-spinner fa-spin"></i>
              Create User
            </button>
          </div>
        </form>
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
import { useUserStore } from '@/stores/useUserStore'
import { createLogger } from '@/utils/debugUtils'

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

const userStore = useUserStore()

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

const totalPages = computed(() => Math.ceil(total.value / pageSize))

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = userStore.authState.token
  if (token && token !== 'single_user_mode') {
    headers['Authorization'] = `Bearer ${token}`
  }
  return headers
}

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
    const res = await fetch(`${getBackendUrl()}/user-management/users?${params}`, {
      headers: authHeaders(),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`)
    }
    const data = await res.json() as { users: UserRecord[]; total: number }
    users.value = data.users
    total.value = data.total
  } catch (err) {
    logger.error('Failed to load users:', err)
    error.value = err instanceof Error ? err.message : 'Failed to load users'
  } finally {
    loading.value = false
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
    const res = await fetch(`${getBackendUrl()}/user-management/users/${user.id}/role`, {
      method: 'PUT',
      headers: authHeaders(),
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
    const res = await fetch(`${getBackendUrl()}/user-management/users/${user.id}/${action}`, {
      method: 'POST',
      headers: authHeaders(),
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
    const res = await fetch(`${getBackendUrl()}/user-management/users/${deleteTarget.value.id}`, {
      method: 'DELETE',
      headers: authHeaders(),
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
    const res = await fetch(`${getBackendUrl()}/user-management/users`, {
      method: 'POST',
      headers: authHeaders(),
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
  padding: 1.5rem;
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 1.5rem;
  gap: 1rem;
  flex-wrap: wrap;
}

.page-title {
  font-size: 1.5rem;
  font-weight: 600;
  margin: 0 0 0.25rem;
}

.page-subtitle {
  font-size: 0.875rem;
  color: var(--color-text-secondary, #6b7280);
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 0.5rem;
}

.error-banner {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  background: var(--color-error-bg, #fef2f2);
  border: 1px solid var(--color-error-border, #fca5a5);
  border-radius: 0.5rem;
  margin-bottom: 1rem;
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
  margin-bottom: 1rem;
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
  padding: 0.5rem 0.75rem 0.5rem 2.25rem;
  border: 1px solid var(--color-border, #d1d5db);
  border-radius: 0.5rem;
  font-size: 0.875rem;
  box-sizing: border-box;
}

.table-section {
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 0.75rem;
  overflow: hidden;
}

.loading-state {
  padding: 2rem;
  text-align: center;
  color: var(--color-text-secondary, #6b7280);
}

.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table th {
  text-align: left;
  padding: 0.75rem 1rem;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-secondary, #6b7280);
  background: var(--color-surface-alt, #f9fafb);
  border-bottom: 1px solid var(--color-border, #e5e7eb);
}

.data-table td {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--color-border, #f3f4f6);
  font-size: 0.875rem;
}

.data-table tr:last-child td {
  border-bottom: none;
}

.username-cell {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.username {
  font-weight: 500;
}

.badge {
  display: inline-block;
  padding: 0.125rem 0.5rem;
  border-radius: 9999px;
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

.role-select {
  padding: 0.25rem 0.5rem;
  border: 1px solid var(--color-border, #d1d5db);
  border-radius: 0.375rem;
  font-size: 0.8125rem;
  background: transparent;
}

.actions-cell {
  display: flex;
  gap: 0.25rem;
}

.btn-icon {
  width: 2rem;
  height: 2rem;
  border: none;
  border-radius: 0.375rem;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 0.75rem;
}

.btn-warning {
  background: var(--color-warning-bg, #fffbeb);
  color: var(--color-warning, #d97706);
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
  gap: 1rem;
  padding: 0.75rem;
  border-top: 1px solid var(--color-border, #e5e7eb);
}

.btn-page {
  padding: 0.375rem 0.75rem;
  border: 1px solid var(--color-border, #d1d5db);
  border-radius: 0.375rem;
  background: transparent;
  cursor: pointer;
}

.btn-page:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.page-info {
  font-size: 0.875rem;
  color: var(--color-text-secondary, #6b7280);
}

.btn-action-primary,
.btn-action-secondary,
.btn-action-danger {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  font-size: 0.875rem;
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
  border-radius: 0.75rem;
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
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--color-border, #e5e7eb);
}

.modal-header h3 {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
}

.btn-close {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--color-text-secondary, #6b7280);
  font-size: 0.875rem;
}

.modal-body {
  padding: 1.25rem;
}

.form-group {
  margin-bottom: 1rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.375rem;
  font-size: 0.875rem;
  font-weight: 500;
}

.form-input {
  width: 100%;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--color-border, #d1d5db);
  border-radius: 0.375rem;
  font-size: 0.875rem;
  box-sizing: border-box;
}

.error-inline {
  color: var(--color-error, #dc2626);
  font-size: 0.8125rem;
  margin-top: 0.5rem;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  padding-top: 1rem;
}
</style>
