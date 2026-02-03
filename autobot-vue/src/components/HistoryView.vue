<template>
  <div class="history-view">
    <h2>Chat History</h2>
    <div class="history-actions">
      <button
        @click="refreshHistory"
        :disabled="isRefreshing"
        :class="{ 'loading': isRefreshing }"
        aria-label="Refresh history">
        <i class="fas" :class="isRefreshing ? 'fa-spinner fa-spin' : 'fa-sync-alt'"></i>
        {{ isRefreshing ? 'Refreshing...' : 'Refresh' }}
      </button>
      <button
        @click="clearHistory"
        :disabled="isClearing"
        :class="{ 'loading': isClearing }"
        aria-label="Clear history">
        <i class="fas" :class="isClearing ? 'fa-spinner fa-spin' : 'fa-trash-alt'"></i>
        {{ isClearing ? 'Clearing...' : 'Clear History' }}
      </button>
    </div>
    <div class="history-list-container">
      <!-- Loading overlay when refreshing -->
      <div v-if="isRefreshing" class="loading-overlay">
        <div class="loading-content">
          <i class="fas fa-spinner fa-spin fa-2x"></i>
          <p>Loading history...</p>
        </div>
      </div>

      <EmptyState
        v-if="history.length === 0 && !isRefreshing"
        icon="fas fa-history"
        message="No chat history available."
      />
      <div v-else-if="!isRefreshing" class="history-entries">
        <div v-for="(entry, index) in history" :key="entry.id || `history-${entry.date}`" class="history-entry" @click="viewHistoryEntry(entry)" tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
          <div class="history-summary">
            <span class="history-date">{{ entry.date }}</span>
            <span class="history-preview">{{ entry.preview }}</span>
          </div>
          <div class="history-actions-entry">
            <button
              @click.stop="deleteHistoryEntry(entry)"
              :disabled="isDeleting"
              :class="{ 'deleting': isDeleting }"
              aria-label="Delete entry">
              <i class="fas" :class="isDeleting ? 'fa-spinner fa-spin' : 'fa-trash'"></i>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue';
import apiClient from '../utils/ApiClient.js';
import { useAsyncHandler } from '@/composables/useErrorHandler';
import EmptyState from '@/components/ui/EmptyState.vue';
import { createLogger } from '@/utils/debugUtils';

const logger = createLogger('HistoryView');

export default {
  name: 'HistoryView',
  components: {
    EmptyState
  },
  setup() {
    const history = ref([]);

    // Function to fetch chat history from backend
    const { execute: refreshHistory, loading: isRefreshing } = useAsyncHandler(
      async () => {
        const response = await apiClient.getChatList();
        const chats = response.chats || [];

        // Use Promise.allSettled to handle individual chat errors gracefully
        const results = await Promise.allSettled(
          chats.map(async (chat) => {
            const messagesResponse = await apiClient.getChatHistory(chat.chatId);
            const messages = messagesResponse.history || [];
            // Look for the first user message to use as a preview or subject
            const userMessage = messages.find(msg => msg.sender === 'user');
            // If there's a user message, use it as the subject/preview
            const subject = userMessage ? userMessage.text.substring(0, 30) + (userMessage.text.length > 30 ? '...' : '') : 'No subject';
            return {
              id: chat.chatId,
              date: messages.length > 0 ? messages[0].timestamp : 'Unknown date',
              preview: subject,
              name: chat.name || ''
            };
          })
        );

        // Process results - use fulfilled values, provide fallback for rejected
        history.value = results.map((result, index) => {
          if (result.status === 'fulfilled') {
            return result.value;
          } else {
            logger.error(`Error loading messages for chat ${chats[index].chatId}:`, result.reason);
            return {
              id: chats[index].chatId,
              date: 'Unknown date',
              preview: 'Error loading chat',
              name: chats[index].name || ''
            };
          }
        });
      },
      {
        onError: () => {
          // Fallback to local storage
          loadHistoryFromLocalStorage();
        },
        logErrors: true,
        errorPrefix: '[HistoryView]'
      }
    );

    // Function to build chat history from local storage
    const loadHistoryFromLocalStorage = () => {
      const localChats = [];
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key.startsWith('chat_') && key.endsWith('_messages')) {
          const chatId = key.split('_')[1];
          const messagesStr = localStorage.getItem(key);
          if (messagesStr) {
            try {
              const messages = JSON.parse(messagesStr);
              // Look for the first user message to use as a preview or subject
              const userMessage = messages.find(msg => msg.sender === 'user');
              // If there's a user message, use it as the subject/preview
              const subject = userMessage ? userMessage.text.substring(0, 30) + (userMessage.text.length > 30 ? '...' : '') : 'No subject';
              localChats.push({
                id: chatId,
                date: messages.length > 0 ? messages[0].timestamp : 'Unknown date',
                preview: subject,
                name: ''
              });
            } catch (e) {
              logger.error(`Error parsing messages for chat ${chatId}:`, e);
            }
          }
        }
      }
      history.value = localChats;
    };

    const { execute: performClearHistory, loading: isClearing } = useAsyncHandler(
      async () => {
        // Delete all chats from backend and localStorage
        const deletePromises = history.value.map(async (entry) => {
          try {
            await apiClient.deleteChat(entry.id);
            localStorage.removeItem(`chat_${entry.id}_messages`);
          } catch (error) {
            logger.error(`Failed to delete chat ${entry.id}:`, error);
            // Continue with other deletions even if one fails
          }
        });

        await Promise.allSettled(deletePromises);

        // Clear local array after deletion attempts
        history.value = [];
      },
      {
        onError: () => {
          alert('Failed to clear all chat history. Some chats may not have been deleted.');
        },
        successMessage: 'Chat history cleared successfully',
        logErrors: true,
        errorPrefix: '[HistoryView]'
      }
    );

    const clearHistory = async () => {
      if (confirm('Are you sure you want to delete ALL chat history? This cannot be undone.')) {
        await performClearHistory();
      }
    };

    const viewHistoryEntry = (entry) => {
      // Navigate to the chat in ChatInterface by updating the URL hash
      window.location.hash = `chatId=${entry.id}`;
    };

    const { execute: deleteHistoryEntry, loading: isDeleting } = useAsyncHandler(
      async (entry) => {
        await apiClient.deleteChat(entry.id);
        // Remove from local storage
        localStorage.removeItem(`chat_${entry.id}_messages`);
        // Remove from history list
        history.value = history.value.filter(e => e.id !== entry.id);
      },
      {
        onError: () => {
          alert('Failed to delete chat history. Please try again.');
        },
        logErrors: true,
        errorPrefix: '[HistoryView]'
      }
    );

    // Load history on mount
    onMounted(() => {
      refreshHistory();
    });

    return {
      history,
      refreshHistory,
      clearHistory,
      viewHistoryEntry,
      deleteHistoryEntry,
      isRefreshing,
      isDeleting,
      isClearing
    };
  }
};
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.history-view {
  background-color: var(--bg-primary);
  border-radius: 8px;
  box-shadow: var(--shadow-md);
  padding: 15px;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.history-view h2 {
  margin: 0 0 15px 0;
  font-size: 20px;
  color: var(--color-primary);
}

.history-actions {
  display: flex;
  gap: 10px;
  margin-bottom: 15px;
}

.history-actions button {
  background-color: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  padding: 8px 15px;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.3s;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
}

.history-actions button:hover:not(:disabled) {
  background-color: var(--color-primary-hover);
}

.history-actions button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.history-actions button.loading {
  opacity: 0.7;
}

.history-actions button:last-child {
  background-color: var(--color-danger);
}

.history-actions button:last-child:hover:not(:disabled) {
  background-color: var(--color-danger-hover);
}

.history-list-container {
  flex: 1;
  overflow-y: auto;
  border: 1px solid var(--border-light);
  border-radius: 4px;
  padding: 10px;
  position: relative;
}

.loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: var(--bg-overlay-light);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
  border-radius: 4px;
}

.loading-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: var(--color-primary);
}

.loading-content p {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
}

.history-entries {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.history-entry {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px;
  border: 1px solid var(--border-light);
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.3s;
}

.history-entry:hover {
  background-color: var(--bg-hover);
}

.history-summary {
  flex: 1;
  overflow: hidden;
}

.history-date {
  font-size: 14px;
  color: var(--text-tertiary);
  display: block;
  margin-bottom: 5px;
}

.history-preview {
  font-size: 16px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
}

.history-actions-entry button {
  background-color: var(--color-danger);
  color: var(--text-on-primary);
  border: none;
  padding: 5px 10px;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.3s;
  min-width: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.history-actions-entry button:hover:not(:disabled) {
  background-color: var(--color-danger-hover);
}

.history-actions-entry button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.history-actions-entry button.deleting {
  opacity: 0.7;
}
</style>
