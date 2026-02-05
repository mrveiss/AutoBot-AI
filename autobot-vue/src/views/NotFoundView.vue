<template>
  <div class="not-found-view view-container-centered">
    <div class="w-full px-4 py-12">
      <div class="text-center">
        <!-- 404 Icon -->
        <div class="mb-8">
          <i class="fas fa-exclamation-triangle text-6xl text-blueGray-400"></i>
        </div>

        <!-- Error Message -->
        <h1 class="text-4xl font-bold text-blueGray-800 mb-4">Page Not Found</h1>
        <p class="text-xl text-blueGray-600 mb-8">
          The page you're looking for doesn't exist or has been moved.
        </p>

        <!-- Navigation Options -->
        <div class="space-x-4">
          <router-link
            to="/chat"
            class="btn btn-primary inline-flex items-center"
          >
            <i class="fas fa-home mr-2"></i>
Go to Chat
          </router-link>
          <button
            @click="$router.go(-1)"
            class="btn btn-outline inline-flex items-center"
          >
            <i class="fas fa-arrow-left mr-2"></i>
            Go Back
          </button>
        </div>

        <!-- Helpful Links -->
        <div class="mt-12">
          <h3 class="text-lg font-semibold text-blueGray-700 mb-4">Quick Links</h3>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-4 max-w-2xl mx-auto">
            <router-link
              to="/chat"
              class="p-4 bg-white rounded-lg shadow hover:shadow-md transition-shadow text-center"
            >
              <i class="fas fa-comments text-2xl text-indigo-500 mb-2"></i>
              <div class="text-sm font-medium text-blueGray-700">AI Assistant</div>
            </router-link>
            <router-link
              to="/knowledge"
              class="p-4 bg-white rounded-lg shadow hover:shadow-md transition-shadow text-center"
            >
              <i class="fas fa-database text-2xl text-indigo-500 mb-2"></i>
              <div class="text-sm font-medium text-blueGray-700">Knowledge Base</div>
            </router-link>
            <router-link
              to="/tools"
              class="p-4 bg-white rounded-lg shadow hover:shadow-md transition-shadow text-center"
            >
              <i class="fas fa-tools text-2xl text-indigo-500 mb-2"></i>
              <div class="text-sm font-medium text-blueGray-700">Developer Tools</div>
            </router-link>
            <router-link
              to="/monitoring"
              class="p-4 bg-white rounded-lg shadow hover:shadow-md transition-shadow text-center"
            >
              <i class="fas fa-chart-line text-2xl text-indigo-500 mb-2"></i>
              <div class="text-sm font-medium text-blueGray-700">Monitoring</div>
            </router-link>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// View-level component for 404 error page
</script>

<style scoped>
/* View-specific styles - centered layout provided by .view-container-centered (Issue #548) */
</style>
