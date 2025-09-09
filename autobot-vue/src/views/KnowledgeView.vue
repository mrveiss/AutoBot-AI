<template>
  <div class="knowledge-view">
    <div class="container mx-auto px-4 py-6">
      <div class="mb-6">
        <h1 class="text-3xl font-bold text-blueGray-700">Knowledge Base</h1>
        <p class="text-blueGray-600 mt-2">Manage documents, categories, and knowledge entries</p>
      </div>

      <!-- Sub-navigation for knowledge sections -->
      <div class="mb-6">
        <nav class="flex space-x-4 border-b border-blueGray-200">
          <router-link
            to="/knowledge/search"
            class="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
            :class="$route.name === 'knowledge-search' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-blueGray-500 hover:text-blueGray-700 hover:border-blueGray-300'"
          >
            <i class="fas fa-search mr-2"></i>Search
          </router-link>
          <router-link
            to="/knowledge/categories"
            class="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
            :class="$route.name === 'knowledge-categories' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-blueGray-500 hover:text-blueGray-700 hover:border-blueGray-300'"
          >
            <i class="fas fa-folder mr-2"></i>Categories
          </router-link>
          <router-link
            to="/knowledge/upload"
            class="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
            :class="$route.name === 'knowledge-upload' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-blueGray-500 hover:text-blueGray-700 hover:border-blueGray-300'"
          >
            <i class="fas fa-upload mr-2"></i>Upload
          </router-link>
          <router-link
            to="/knowledge/manage"
            class="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
            :class="$route.name === 'knowledge-manage' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-blueGray-500 hover:text-blueGray-700 hover:border-blueGray-300'"
          >
            <i class="fas fa-edit mr-2"></i>Manage
          </router-link>
          <router-link
            to="/knowledge/stats"
            class="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
            :class="$route.name === 'knowledge-stats' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-blueGray-500 hover:text-blueGray-700 hover:border-blueGray-300'"
          >
            <i class="fas fa-chart-bar mr-2"></i>Statistics
          </router-link>
          <router-link
            to="/knowledge/manpages"
            class="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
            :class="$route.name === 'knowledge-manpages' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-blueGray-500 hover:text-blueGray-700 hover:border-blueGray-300'"
          >
            <i class="fas fa-book mr-2"></i>Man Pages
          </router-link>
        </nav>
      </div>

      <!-- Knowledge component content -->
      <router-view />
    </div>
  </div>
</template>

<script setup lang="ts">
// View-level component for knowledge base layout
</script>

<style scoped>
.knowledge-view {
  min-height: calc(100vh - 80px);
}
</style>
