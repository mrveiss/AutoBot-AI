<template>
  <div class="tools-view view-container">
    <div class="container mx-auto px-4 pt-4 pb-6">
      <!-- Sub-navigation for tools sections -->
      <div class="mb-6">
        <nav class="flex space-x-4 border-b border-blueGray-200">
          <router-link
            to="/tools/terminal"
            class="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
            :class="$route.name?.startsWith('tools-terminal') ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-blueGray-500 hover:text-blueGray-700 hover:border-blueGray-300'"
          >
            <i class="fas fa-terminal mr-2"></i>Terminal
          </router-link>
          <router-link
            to="/tools/files"
            class="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
            :class="$route.name === 'tools-files' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-blueGray-500 hover:text-blueGray-700 hover:border-blueGray-300'"
          >
            <i class="fas fa-folder mr-2"></i>Files
          </router-link>
          <router-link
            to="/tools/browser"
            class="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
            :class="$route.name === 'tools-browser' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-blueGray-500 hover:text-blueGray-700 hover:border-blueGray-300'"
          >
            <i class="fas fa-globe mr-2"></i>Browser
          </router-link>
          <router-link
            to="/tools/novnc"
            class="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
            :class="$route.name === 'tools-novnc' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-blueGray-500 hover:text-blueGray-700 hover:border-blueGray-300'"
          >
            <i class="fas fa-desktop mr-2"></i>noVNC
          </router-link>
          <router-link
            to="/tools/voice"
            class="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
            :class="$route.name === 'tools-voice' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-blueGray-500 hover:text-blueGray-700 hover:border-blueGray-300'"
          >
            <i class="fas fa-microphone mr-2"></i>Voice
          </router-link>
          <router-link
            to="/tools/mcp"
            class="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
            :class="$route.name === 'tools-mcp' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-blueGray-500 hover:text-blueGray-700 hover:border-blueGray-300'"
          >
            <i class="fas fa-plug mr-2"></i>MCP Registry
          </router-link>
          <router-link
            to="/tools/agents"
            class="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
            :class="$route.name === 'tools-agents' ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-blueGray-500 hover:text-blueGray-700 hover:border-blueGray-300'"
          >
            <i class="fas fa-robot mr-2"></i>Agents
          </router-link>
        </nav>
      </div>

      <!-- Tools component content -->
      <router-view />
    </div>
  </div>
</template>

<script setup lang="ts">
// View-level component for tools layout
</script>

<style scoped>
/* View-specific styles only - scroll styling provided by .view-container (Issue #548) */
</style>
