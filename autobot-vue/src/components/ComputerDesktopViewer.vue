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
        Phase 9 Complete - VNC Integration Active
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue';
import { API_CONFIG } from '@/config/environment.js';

export default {
  name: 'ComputerDesktopViewer',
  setup() {
    const vncUrl = ref('Loading...');

    onMounted(async () => {
      try {
        // Use environment configuration or fallback to dynamic URL
        vncUrl.value = API_CONFIG.PLAYWRIGHT_VNC_URL || 
                      `${window.location.protocol}//${window.location.hostname}:6080/vnc.html`;
      } catch (error) {
        console.error('Error loading VNC URL:', error);
        vncUrl.value = 'Configuration unavailable';
      }
    });

    return {
      vncUrl
    };
  }
};
</script>

<style scoped>
.computer-desktop-viewer {
  background: linear-gradient(135deg, #fef3c7 0%, #f59e0b 100%);
  border-radius: 8px;
  border: 2px dashed #d97706;
  min-height: 400px;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
