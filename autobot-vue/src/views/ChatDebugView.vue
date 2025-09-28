<template>
  <div class="min-h-screen bg-gray-100 p-4">
    <div class="max-w-6xl mx-auto">
      <h1 class="text-3xl font-bold text-gray-800 mb-6">Chat Persistence Debug Page</h1>

      <div class="mb-6">
        <ChatPersistenceDebugger />
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- Chat Sidebar Component -->
        <div class="bg-white rounded-lg shadow">
          <h2 class="text-xl font-semibold text-gray-700 p-4 border-b">Chat Sidebar</h2>
          <div class="h-96">
            <ChatSidebar />
          </div>
        </div>

        <!-- Instructions -->
        <div class="bg-white rounded-lg shadow p-6">
          <h2 class="text-xl font-semibold text-gray-700 mb-4">Testing Instructions</h2>

          <div class="space-y-4 text-sm">
            <div class="p-3 bg-blue-50 rounded">
              <h3 class="font-semibold text-blue-800">Test Chat Deletion Persistence</h3>
              <ol class="list-decimal list-inside mt-2 space-y-1 text-blue-700">
                <li>Create a few test sessions using the "Create Test Session" button</li>
                <li>Delete a session using the "Delete Last Session" button or the sidebar</li>
                <li>Check that the session count decreases in both store and persistence panels</li>
                <li>Refresh the page (F5)</li>
                <li>Verify the deleted session does NOT reappear</li>
              </ol>
            </div>

            <div class="p-3 bg-green-50 rounded">
              <h3 class="font-semibold text-green-800">Debug Tools</h3>
              <ul class="list-disc list-inside mt-2 space-y-1 text-green-700">
                <li><strong>Refresh State:</strong> Updates the persistence panel</li>
                <li><strong>Debug Console:</strong> Prints detailed persistence info to browser console</li>
                <li><strong>Clear localStorage:</strong> Resets all chat data</li>
              </ul>
            </div>

            <div class="p-3 bg-yellow-50 rounded">
              <h3 class="font-semibold text-yellow-800">Expected Behavior</h3>
              <ul class="list-disc list-inside mt-2 space-y-1 text-yellow-700">
                <li>Store and Persistence panels should show same session count</li>
                <li>Deletion should immediately update both store and localStorage</li>
                <li>Page refresh should preserve the deletion (no reappearing chats)</li>
                <li>Console should show green checkmarks for successful operations</li>
              </ul>
            </div>

            <div class="p-3 bg-red-50 rounded">
              <h3 class="font-semibold text-red-800">If Issues Persist</h3>
              <ul class="list-disc list-inside mt-2 space-y-1 text-red-700">
                <li>Check browser console for error messages</li>
                <li>Use "Debug Console" button to see detailed persistence state</li>
                <li>Clear localStorage and restart testing</li>
                <li>Verify backend DELETE endpoints are working (Network tab)</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import ChatPersistenceDebugger from '@/components/debug/ChatPersistenceDebugger.vue'
import ChatSidebar from '@/components/chat/ChatSidebar.vue'
</script>