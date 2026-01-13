<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="capabilities-display">
    <div class="display-header">
      <h4>System Capabilities</h4>
      <button @click="$emit('refresh')" class="btn-icon" :disabled="loading">
        <i class="fas fa-sync-alt" :class="{ 'fa-spin': loading }"></i>
      </button>
    </div>

    <div v-if="loading && !capabilities" class="loading-state">
      <LoadingSpinner />
      <p>Loading capabilities...</p>
    </div>

    <div v-else class="capabilities-content">
      <!-- Streaming Capabilities -->
      <div class="capability-section">
        <h5><i class="fas fa-desktop"></i> Desktop Streaming</h5>
        <div class="capability-grid" v-if="capabilities">
          <div class="capability-item">
            <div class="capability-status" :class="{ available: capabilities.vnc_available }">
              <i class="fas" :class="capabilities.vnc_available ? 'fa-check' : 'fa-times'"></i>
            </div>
            <div class="capability-info">
              <span class="capability-name">VNC Server</span>
              <span class="capability-desc">Virtual network computing server</span>
            </div>
          </div>

          <div class="capability-item">
            <div class="capability-status" :class="{ available: capabilities.novnc_available }">
              <i class="fas" :class="capabilities.novnc_available ? 'fa-check' : 'fa-times'"></i>
            </div>
            <div class="capability-info">
              <span class="capability-name">noVNC Web Access</span>
              <span class="capability-desc">Browser-based VNC client</span>
            </div>
          </div>

          <div class="capability-item">
            <div class="capability-status available">
              <span class="capability-value">{{ capabilities.max_sessions }}</span>
            </div>
            <div class="capability-info">
              <span class="capability-name">Max Sessions</span>
              <span class="capability-desc">Maximum concurrent streaming sessions</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Supported Resolutions -->
      <div class="capability-section" v-if="capabilities?.supported_resolutions?.length">
        <h5><i class="fas fa-expand"></i> Supported Resolutions</h5>
        <div class="resolution-list">
          <span
            v-for="res in capabilities.supported_resolutions"
            :key="res"
            class="resolution-badge"
          >
            {{ res }}
          </span>
        </div>
      </div>

      <!-- Supported Color Depths -->
      <div class="capability-section" v-if="capabilities?.supported_depths?.length">
        <h5><i class="fas fa-palette"></i> Color Depths</h5>
        <div class="depth-list">
          <span
            v-for="depth in capabilities.supported_depths"
            :key="depth"
            class="depth-badge"
          >
            {{ depth }}-bit
          </span>
        </div>
      </div>

      <!-- Control Features -->
      <div class="capability-section" v-if="controlInfo">
        <h5><i class="fas fa-cogs"></i> Control Features</h5>
        <div class="features-list">
          <div
            v-for="feature in controlInfo.features"
            :key="feature"
            class="feature-item"
          >
            <i class="fas fa-check-circle"></i>
            <span>{{ feature }}</span>
          </div>
        </div>
      </div>

      <!-- API Endpoints -->
      <div class="capability-section" v-if="controlInfo">
        <h5><i class="fas fa-plug"></i> API Endpoints</h5>
        <div class="endpoints-grid">
          <div class="endpoint-item">
            <span class="endpoint-label">Streaming</span>
            <code class="endpoint-path">{{ controlInfo.endpoints.streaming }}</code>
          </div>
          <div class="endpoint-item">
            <span class="endpoint-label">Takeover</span>
            <code class="endpoint-path">{{ controlInfo.endpoints.takeover }}</code>
          </div>
          <div class="endpoint-item">
            <span class="endpoint-label">System</span>
            <code class="endpoint-path">{{ controlInfo.endpoints.system }}</code>
          </div>
        </div>

        <div class="websocket-endpoints">
          <h6>WebSocket Endpoints</h6>
          <div class="endpoint-item">
            <span class="endpoint-label">Monitoring</span>
            <code class="endpoint-path">{{ controlInfo.endpoints.websockets.monitoring }}</code>
          </div>
          <div class="endpoint-item">
            <span class="endpoint-label">Desktop</span>
            <code class="endpoint-path">{{ controlInfo.endpoints.websockets.desktop }}</code>
          </div>
        </div>
      </div>

      <!-- Version Info -->
      <div class="capability-section" v-if="controlInfo">
        <h5><i class="fas fa-info-circle"></i> System Info</h5>
        <div class="info-grid">
          <div class="info-item">
            <span class="info-label">Name</span>
            <span class="info-value">{{ controlInfo.name }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">Version</span>
            <span class="info-value">{{ controlInfo.version }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { StreamingCapabilities, AdvancedControlInfo } from '@/utils/AdvancedControlApiClient';
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue';

defineProps<{
  capabilities: StreamingCapabilities | null;
  controlInfo: AdvancedControlInfo | null;
  loading: boolean;
}>();

defineEmits<{
  refresh: [];
}>();
</script>

<style scoped>
.capabilities-display {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.display-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-default);
}

.display-header h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.btn-icon {
  width: 32px;
  height: 32px;
  background: var(--bg-tertiary);
  border: none;
  border-radius: 6px;
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.btn-icon:hover:not(:disabled) {
  background: var(--bg-hover);
}

.btn-icon:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.loading-state {
  padding: 60px 20px;
  text-align: center;
  color: var(--text-tertiary);
}

.capabilities-content {
  padding: 20px;
}

.capability-section {
  margin-bottom: 28px;
}

.capability-section:last-child {
  margin-bottom: 0;
}

.capability-section h5 {
  margin: 0 0 16px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.capability-section h5 i {
  color: var(--color-primary);
}

.capability-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.capability-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.capability-status {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  background: var(--color-error-bg);
  color: var(--color-error);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
}

.capability-status.available {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.capability-value {
  font-size: 18px;
  font-weight: 600;
}

.capability-info {
  display: flex;
  flex-direction: column;
}

.capability-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.capability-desc {
  font-size: 12px;
  color: var(--text-muted);
}

.resolution-list,
.depth-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.resolution-badge,
.depth-badge {
  padding: 6px 12px;
  background: var(--bg-tertiary);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  font-family: var(--font-mono);
}

.features-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 10px;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: var(--bg-tertiary);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-secondary);
}

.feature-item i {
  color: var(--color-success);
}

.endpoints-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 16px;
}

.endpoint-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: var(--bg-tertiary);
  border-radius: 6px;
}

.endpoint-label {
  min-width: 80px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
}

.endpoint-path {
  font-family: var(--font-mono);
  font-size: 12px;
  background: var(--bg-secondary);
  padding: 4px 8px;
  border-radius: 4px;
  color: var(--color-primary);
}

.websocket-endpoints {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border-default);
}

.websocket-endpoints h6 {
  margin: 0 0 12px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.info-grid {
  display: flex;
  gap: 24px;
}

.info-item {
  display: flex;
  flex-direction: column;
}

.info-label {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.info-value {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}
</style>
