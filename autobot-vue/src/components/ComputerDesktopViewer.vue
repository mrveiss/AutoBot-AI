<template>
  <div class="computer-desktop-viewer p-8 text-center text-gray-500">
    <div class="max-w-md mx-auto">
      <div class="text-4xl mb-4">🖥️</div>
      <h3 class="text-lg font-semibold mb-2">Computer Desktop Viewer</h3>
      <p class="text-sm mb-4">
        Desktop streaming is now available via the Playwright Browser component with noVNC integration.
      </p>
      <div class="info-box p-4 bg-blue-50 border border-blue-200 rounded-lg">
        <p class="text-sm text-blue-700 mb-2">
          <strong>🎭 Active:</strong> Browser automation desktop available
        </p>
        <p class="text-xs text-blue-600">
          Access: {{ vncUrl }}
        </p>
      </div>
      <div class="mt-4 text-xs text-gray-400">
        VNC Integration Active
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue';
import { createLogger } from '@/utils/debugUtils';
import appConfig from '@/config/AppConfig.js';

const logger = createLogger('ComputerDesktopViewer');

export default {
  name: 'ComputerDesktopViewer',
  setup() {
    const vncUrl = ref('Loading...');

    onMounted(async () => {
      try {
        // Use centralized AppConfig for VNC URL
        vncUrl.value = await appConfig.getVNCUrl('desktop', {
          autoconnect: true,
          resize: 'remote',
          reconnect: true
        });
      } catch (error) {
        logger.error('Error loading VNC URL from centralized configuration:', error);
        vncUrl.value = 'Configuration unavailable - check service discovery';
      }
    });

    return {
      vncUrl
    };
  }
};
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.computer-desktop-viewer {
  background: linear-gradient(135deg, var(--color-warning-light) 0%, var(--color-warning) 100%);
  border-radius: var(--radius-md);
  border: 2px dashed var(--color-warning-dark);
  min-height: 400px;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>