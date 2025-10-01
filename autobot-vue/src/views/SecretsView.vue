<template>
  <div class="secrets-view">
    <div class="container mx-auto px-4 py-6">
      <div class="mb-6">
        <h1 class="text-3xl font-bold text-blueGray-700">Secrets Manager</h1>
        <p class="text-blueGray-600 mt-2">Manage API keys, tokens, and sensitive configuration</p>
      </div>

      <!-- Security notice -->
      <div class="mb-6 bg-amber-50 border border-amber-200 rounded-lg p-4">
        <div class="flex items-start">
          <i class="fas fa-shield-alt text-amber-500 text-lg mr-3 mt-0.5"></i>
          <div>
            <h3 class="text-sm font-medium text-amber-800">Security Notice</h3>
            <p class="text-sm text-amber-700 mt-1">
              All secrets are encrypted and stored securely. Never share your API keys or access tokens.
            </p>
          </div>
        </div>
      </div>

      <!-- Secrets content will be handled by the existing secrets component -->
      <router-view />
    </div>
  </div>
</template>

<script setup lang="ts">
// View-level component for secrets management layout
</script>

<style scoped>
.secrets-view {
  min-height: calc(100vh - 80px);
  max-height: calc(100vh - 80px);
  overflow-y: auto;
  overflow-x: hidden;
  scroll-behavior: smooth;
}

/* Custom scrollbar styling for better UX */
.secrets-view::-webkit-scrollbar {
  width: 8px;
}

.secrets-view::-webkit-scrollbar-track {
  background: #f1f1f1;
}

.secrets-view::-webkit-scrollbar-thumb {
  background: #888;
  border-radius: 4px;
}

.secrets-view::-webkit-scrollbar-thumb:hover {
  background: #555;
}
</style>
