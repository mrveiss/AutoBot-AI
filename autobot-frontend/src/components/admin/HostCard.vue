<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="host-card" :class="`status-${host.status}`">
    <div class="card-header">
      <div class="host-identity">
        <span class="status-dot" :title="host.status"></span>
        <h4 class="host-name">{{ host.hostname }}</h4>
        <code class="host-ip">{{ host.ip_address }}</code>
      </div>
      <button
        class="btn-expand"
        :aria-label="expanded ? 'Collapse' : 'Expand'"
        @click="expanded = !expanded"
      >
        <i :class="['fas', expanded ? 'fa-chevron-up' : 'fa-chevron-down']"></i>
      </button>
    </div>

    <div class="card-meta">
      <span v-if="host.agent_version" class="meta-badge">v{{ host.agent_version }}</span>
      <span v-if="host.os_info" class="meta-badge">{{ host.os_info }}</span>
      <span v-if="host.ansible_name" class="meta-badge">
        <Icon name="terminal" /> {{ host.ansible_name }}
      </span>
    </div>

    <!-- Health bars -->
    <div class="health-bars">
      <HealthBar label="CPU" :value="host.cpu_percent" />
      <HealthBar label="MEM" :value="host.memory_percent" />
      <HealthBar label="DISK" :value="host.disk_percent" />
    </div>

    <!-- Expandable roles panel -->
    <div v-if="expanded" class="roles-panel">
      <div class="roles-header">
        <span class="roles-title">Assigned Roles</span>
      </div>
      <div v-if="host.roles.length === 0" class="roles-empty">No roles assigned.</div>
      <ul v-else class="roles-list">
        <li v-for="role in host.roles" :key="role" class="role-item">
          <span class="role-name">{{ role }}</span>
          <button
            class="btn-provision"
            :aria-label="`Provision ${role} on ${host.hostname}`"
            @click="$emit('provision', host.node_id, role)"
          >
            <Icon name="play" /> Provision
          </button>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref } from 'vue'
import type { Host } from '@/composables/useHostInventory'
import HealthBar from '@/components/admin/HealthBar.vue'

defineProps<{ host: Host }>()
defineEmits<{ provision: [nodeId: string, role: string] }>()

const expanded = ref(false)
</script>

<style scoped>
.host-card {
  background: var(--bg-secondary, #1a1a2e);
  border: 1px solid var(--border-color, rgba(255, 255, 255, 0.1));
  border-radius: 0.5rem;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.host-card.status-online { border-left: 3px solid #22c55e; }
.host-card.status-offline { border-left: 3px solid #ef4444; }
.host-card.status-unknown { border-left: 3px solid #6b7280; }

.card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.5rem;
}

.host-identity {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  background: #6b7280;
}

.status-online .status-dot { background: #22c55e; }
.status-offline .status-dot { background: #ef4444; }

.host-name {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary, #e0e0e0);
}

.host-ip {
  font-size: 0.75rem;
  color: var(--text-secondary, rgba(255, 255, 255, 0.5));
  background: rgba(255, 255, 255, 0.06);
  padding: 0.1rem 0.4rem;
  border-radius: 0.25rem;
}

.btn-expand {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-secondary, rgba(255, 255, 255, 0.4));
  padding: 0.2rem;
  flex-shrink: 0;
}

.card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.meta-badge {
  font-size: 0.72rem;
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-secondary, rgba(255, 255, 255, 0.5));
  padding: 0.1rem 0.4rem;
  border-radius: 0.25rem;
}

.health-bars {
  display: flex;
  gap: 0.5rem;
}

.roles-panel {
  border-top: 1px solid var(--border-color, rgba(255, 255, 255, 0.08));
  padding-top: 0.65rem;
}

.roles-header {
  margin-bottom: 0.5rem;
}

.roles-title {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--text-secondary, rgba(255, 255, 255, 0.5));
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.roles-empty {
  font-size: 0.8rem;
  color: var(--text-secondary, rgba(255, 255, 255, 0.35));
}

.roles-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.role-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.role-name {
  font-size: 0.875rem;
  color: var(--text-primary, #e0e0e0);
}

.btn-provision {
  font-size: 0.75rem;
  padding: 0.2rem 0.5rem;
  background: rgba(99, 102, 241, 0.15);
  border: 1px solid rgba(99, 102, 241, 0.3);
  border-radius: 0.25rem;
  color: #a5b4fc;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.3rem;
  transition: background 0.15s;
}

.btn-provision:hover {
  background: rgba(99, 102, 241, 0.25);
}
</style>
