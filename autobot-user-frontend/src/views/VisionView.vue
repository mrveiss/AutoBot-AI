<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!--
  Vision & Multimodal AI View

  Container view for vision analysis, image processing, and automation features.
  Issue #777: Frontend for Vision & Multimodal AI Features.
-->
<template>
  <div class="vision-view">
    <!-- Sidebar Navigation -->
    <aside class="vision-sidebar">
      <div class="sidebar-header">
        <h3>
          <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
            <path d="M10 12a2 2 0 100-4 2 2 0 000 4z" />
            <path
              fill-rule="evenodd"
              d="M.458 10C1.732 5.943 5.522 3 10 3s8.268 2.943 9.542 7c-1.274 4.057-5.064 7-9.542 7S1.732 14.057.458 10zM14 10a4 4 0 11-8 0 4 4 0 018 0z"
              clip-rule="evenodd"
            />
          </svg>
          Vision & AI
        </h3>
      </div>

      <nav class="sidebar-nav">
        <router-link
          to="/vision/analyze"
          class="nav-item"
          :class="{ active: $route.path === '/vision/analyze' }"
        >
          <i class="fas fa-desktop"></i>
          <span>Screen Analysis</span>
        </router-link>

        <router-link
          to="/vision/image"
          class="nav-item"
          :class="{ active: $route.path === '/vision/image' }"
        >
          <i class="fas fa-image"></i>
          <span>Image Processing</span>
        </router-link>

        <router-link
          to="/vision/automation"
          class="nav-item"
          :class="{ active: $route.path === '/vision/automation' }"
        >
          <i class="fas fa-robot"></i>
          <span>Automation</span>
        </router-link>
      </nav>

      <!-- Service Status -->
      <div class="sidebar-footer">
        <div class="status-indicator" :class="statusClass">
          <div class="status-dot"></div>
          <span>{{ statusText }}</span>
        </div>
      </div>
    </aside>

    <!-- Main Content -->
    <main class="vision-content">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { createLogger } from '@/utils/debugUtils';
import { visionMultimodalApiClient } from '@/utils/VisionMultimodalApiClient';

const logger = createLogger('VisionView');

const serviceStatus = ref<'healthy' | 'degraded' | 'offline'>('offline');

const statusClass = computed(() => ({
  healthy: serviceStatus.value === 'healthy',
  degraded: serviceStatus.value === 'degraded',
  offline: serviceStatus.value === 'offline',
}));

const statusText = computed(() => {
  if (serviceStatus.value === 'healthy') return 'Vision service online';
  if (serviceStatus.value === 'degraded') return 'Service degraded';
  return 'Service offline';
});

const checkServiceHealth = async () => {
  try {
    const res = await visionMultimodalApiClient.getVisionHealth();
    if (res.success && res.data?.status === 'healthy') {
      serviceStatus.value = 'healthy';
    } else {
      serviceStatus.value = 'degraded';
    }
  } catch {
    serviceStatus.value = 'offline';
    logger.warn('Vision service health check failed');
  }
};

onMounted(() => {
  checkServiceHealth();
});
</script>

<style scoped>
.vision-view {
  display: flex;
  height: 100%;
  overflow: hidden;
}

/* Sidebar */
.vision-sidebar {
  width: 220px;
  min-width: 220px;
  background: var(--bg-secondary, #fff);
  border-right: 1px solid var(--border-default, #e5e7eb);
  display: flex;
  flex-direction: column;
}

.sidebar-header {
  padding: 20px 16px 12px;
  border-bottom: 1px solid var(--border-default, #e5e7eb);
}

.sidebar-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary, #111827);
  display: flex;
  align-items: center;
  gap: 8px;
}

.sidebar-header svg {
  color: var(--color-primary, #6366f1);
}

.sidebar-nav {
  flex: 1;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary, #6b7280);
  text-decoration: none;
  transition: all 0.15s;
}

.nav-item:hover {
  background: var(--bg-tertiary, #f3f4f6);
  color: var(--text-primary, #111827);
}

.nav-item.active {
  background: var(--color-primary-bg, #eef2ff);
  color: var(--color-primary, #6366f1);
}

.nav-item i {
  width: 18px;
  text-align: center;
  font-size: 14px;
}

/* Footer status */
.sidebar-footer {
  padding: 12px 16px;
  border-top: 1px solid var(--border-default, #e5e7eb);
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-tertiary, #9ca3af);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-muted, #d1d5db);
}

.status-indicator.healthy .status-dot {
  background: #22c55e;
}

.status-indicator.healthy {
  color: #16a34a;
}

.status-indicator.degraded .status-dot {
  background: #f59e0b;
}

.status-indicator.degraded {
  color: #d97706;
}

.status-indicator.offline .status-dot {
  background: #ef4444;
}

/* Main content */
.vision-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  background: var(--bg-primary, #f9fafb);
}

/* Responsive */
@media (max-width: 768px) {
  .vision-sidebar {
    width: 56px;
    min-width: 56px;
  }

  .sidebar-header h3 span,
  .nav-item span,
  .sidebar-footer span {
    display: none;
  }

  .sidebar-header h3 {
    justify-content: center;
  }

  .nav-item {
    justify-content: center;
    padding: 10px;
  }

  .nav-item i {
    width: auto;
  }

  .status-indicator span {
    display: none;
  }

  .status-indicator {
    justify-content: center;
  }
}
</style>
