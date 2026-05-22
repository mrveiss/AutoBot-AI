<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!--
  HostsView — UI-driven host inventory management (GH#7513).
  Lists all SLM-managed nodes, shows per-host roles and health,
  and provides an "Add Host" form plus a "Provision Role" action.
-->
<template>
  <div class="hosts-view view-container">
    <div class="page-header">
      <div class="page-header-content">
        <h2 class="page-title">Host Inventory</h2>
        <p class="page-subtitle">Manage AutoBot multi-host role deployments</p>
      </div>
      <div class="header-actions">
        <button class="btn-action-primary" @click="showAddHost = true">
          <Icon name="plus" />
          Add Host
        </button>
        <button class="btn-action-secondary" :disabled="loading" @click="fetchHosts()">
          <Icon name="sync-alt" :spin="loading" />
          Refresh
        </button>
      </div>
    </div>

    <!-- Error banner -->
    <div v-if="error" class="error-banner" role="alert">
      <Icon name="exclamation-circle" />
      <span>{{ error }}</span>
      <button class="btn-dismiss" aria-label="Dismiss" @click="clearError">
        <Icon name="times" />
      </button>
    </div>

    <!-- Add Host sheet -->
    <div v-if="showAddHost" class="add-host-sheet">
      <h3 class="sheet-title">Add New Host</h3>
      <form class="add-host-form" @submit.prevent="submitAddHost">
        <div class="form-row">
          <label class="form-label" for="ah-hostname">Hostname *</label>
          <input
            id="ah-hostname"
            v-model="newHost.hostname"
            class="form-input"
            type="text"
            required
            placeholder="e.g. worker-01"
          />
        </div>
        <div class="form-row">
          <label class="form-label" for="ah-ip">IP Address *</label>
          <input
            id="ah-ip"
            v-model="newHost.ip_address"
            class="form-input"
            type="text"
            required
            placeholder="e.g. 192.168.1.100"
          />
        </div>
        <div class="form-row">
          <label class="form-label" for="ah-ansible">Ansible Name</label>
          <input
            id="ah-ansible"
            v-model="newHost.ansible_name"
            class="form-input"
            type="text"
            placeholder="Ansible inventory alias (optional)"
          />
        </div>
        <div class="form-row">
          <label class="form-label" for="ah-ssh-user">SSH User</label>
          <input
            id="ah-ssh-user"
            v-model="newHost.ssh_user"
            class="form-input"
            type="text"
            placeholder="autobot"
          />
        </div>
        <div class="form-actions">
          <button type="submit" class="btn-action-primary" :disabled="loading">
            <Icon name="plus" />
            Add
          </button>
          <button type="button" class="btn-action-secondary" @click="cancelAddHost">
            Cancel
          </button>
        </div>
      </form>
    </div>

    <!-- Loading skeleton -->
    <div v-if="loading && hosts.length === 0" class="loading-state">
      <Icon name="sync-alt" :spin="true" /> Loading hosts…
    </div>

    <!-- Empty state -->
    <div v-else-if="!loading && hosts.length === 0" class="empty-state">
      <Icon name="server" class="empty-icon" />
      <p>No hosts registered yet.</p>
      <button class="btn-action-primary" @click="showAddHost = true">
        <Icon name="plus" /> Add your first host
      </button>
    </div>

    <!-- Host cards -->
    <div v-else class="hosts-grid">
      <HostCard
        v-for="host in hosts"
        :key="host.node_id"
        :host="host"
        @provision="handleProvision"
      />
    </div>

    <!-- Pagination hint -->
    <p v-if="total > hosts.length" class="pagination-hint">
      Showing {{ hosts.length }} of {{ total }} hosts.
    </p>

    <!-- Provision result toast -->
    <div v-if="provisionJobId" class="toast toast-success" role="status">
      <Icon name="check-circle" />
      Provision job started: <code>{{ provisionJobId }}</code>
      <button class="btn-dismiss" aria-label="Dismiss" @click="provisionJobId = null">
        <Icon name="times" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import Icon from '@/components/ui/Icon.vue'
import { useHostInventory, type HostCreate } from '@/composables/useHostInventory'
import HostCard from '@/components/admin/HostCard.vue'

const { hosts, total, loading, error, fetchHosts, addHost, provisionRole, clearError } =
  useHostInventory()

const showAddHost = ref(false)
const provisionJobId = ref<string | null>(null)

const newHost = ref<HostCreate>({
  hostname: '',
  ip_address: '',
  ansible_name: '',
  ssh_user: 'autobot',
})

async function submitAddHost(): Promise<void> {
  const payload: HostCreate = {
    hostname: newHost.value.hostname,
    ip_address: newHost.value.ip_address,
  }
  if (newHost.value.ansible_name) payload.ansible_name = newHost.value.ansible_name
  if (newHost.value.ssh_user) payload.ssh_user = newHost.value.ssh_user
  const host = await addHost(payload)
  if (host) cancelAddHost()
}

function cancelAddHost(): void {
  showAddHost.value = false
  newHost.value = { hostname: '', ip_address: '', ansible_name: '', ssh_user: 'autobot' }
}

async function handleProvision(nodeId: string, roleName: string): Promise<void> {
  const jobId = await provisionRole(nodeId, roleName)
  if (jobId) provisionJobId.value = jobId
}

onMounted(() => fetchHosts())
</script>

<style scoped>
.hosts-view {
  padding: 1.5rem;
}

.add-host-sheet {
  background: var(--bg-secondary, #1a1a2e);
  border: 1px solid var(--border-color, rgba(255, 255, 255, 0.1));
  border-radius: 0.5rem;
  padding: 1.25rem;
  margin-bottom: 1.5rem;
}

.sheet-title {
  margin: 0 0 1rem;
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary, #e0e0e0);
}

.add-host-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.form-row {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.form-label {
  font-size: 0.8rem;
  color: var(--text-secondary, rgba(255, 255, 255, 0.6));
}

.form-input {
  padding: 0.4rem 0.65rem;
  background: var(--bg-tertiary, rgba(255, 255, 255, 0.04));
  border: 1px solid var(--border-color, rgba(255, 255, 255, 0.15));
  border-radius: 0.375rem;
  color: var(--text-primary, #e0e0e0);
  font-size: 0.875rem;
}

.form-actions {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.5rem;
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

.hosts-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 1rem;
}

.pagination-hint {
  margin-top: 1rem;
  font-size: 0.8rem;
  color: var(--text-secondary, rgba(255, 255, 255, 0.4));
  text-align: right;
}

.toast {
  position: fixed;
  bottom: 1.5rem;
  right: 1.5rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border-radius: 0.5rem;
  font-size: 0.875rem;
  z-index: 9999;
}

.toast-success {
  background: rgba(34, 197, 94, 0.15);
  border: 1px solid rgba(34, 197, 94, 0.3);
  color: #86efac;
}

.toast .btn-dismiss {
  margin-left: auto;
  background: none;
  border: none;
  cursor: pointer;
  color: inherit;
  padding: 0;
  line-height: 1;
}
</style>
