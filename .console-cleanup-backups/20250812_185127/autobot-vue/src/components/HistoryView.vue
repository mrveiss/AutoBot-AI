<template>
  <div class="history-view">
    <h2>Chat History</h2>
    <div class="history-actions">
      <button @click="refreshHistory">Refresh</button>
      <button @click="clearHistory">Clear History</button>
    </div>
    <div class="history-list-container">
      <div v-if="history.length === 0" class="no-history">No chat history available.</div>
      <div v-else class="history-entries">
        <div v-for="(entry, index) in history" :key="index" class="history-entry" @click="viewHistoryEntry(entry)">
          <div class="history-summary">
            <span class="history-date">{{ entry.date }}</span>
            <span class="history-preview">{{ entry.preview }}</span>
          </div>
          <div class="history-actions-entry">
            <button @click.stop="deleteHistoryEntry(entry)">Delete</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref } from 'vue';

export default {
  name: 'HistoryView',
  setup() {
    const history = ref([]);

    // Function to fetch chat history from backend
    const refreshHistory = async () => {
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/api/chats`);
        if (response.ok) {
          const data = await response.json();
          const chats = data.chats || [];
          history.value = await Promise.all(chats.map(async (chat) => {
            try {
              const messagesResponse = await fetch(`${settings.value.backend.api_endpoint}/api/chats/${chat.chatId}`);
              if (messagesResponse.ok) {
                const data = await messagesResponse.json();
                const messages = data.history || [];
                // Look for the first user message to use as a preview or subject
                const userMessage = messages.find(msg => msg.sender === 'user');
                // If there's a user message, use it as the subject/preview
                let subject = userMessage ? userMessage.text.substring(0, 30) + (userMessage.text.length > 30 ? '...' : '') : 'No subject';
                return {
                  id: chat.chatId,
                  date: messages.length > 0 ? messages[0].timestamp : 'Unknown date',
                  preview: subject,
                  name: chat.name || ''
                };
              }
            } catch (error) {
              console.error(`Error loading messages for chat ${chat.chatId}:`, error);
            }
            return {
              id: chat.chatId,
              date: 'Unknown date',
              preview: 'Error loading chat',
              name: chat.name || ''
            };
          }));
          console.log('Chat history refreshed from backend:', history.value.length, 'chats loaded');
        } else {
          console.error('Failed to load chat history from backend:', response.statusText);
          // Fallback to local storage
          loadHistoryFromLocalStorage();
        }
      } catch (error) {
        console.error('Error loading chat history from backend:', error);
        // Fallback to local storage
        loadHistoryFromLocalStorage();
      }
    };

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
              let subject = userMessage ? userMessage.text.substring(0, 30) + (userMessage.text.length > 30 ? '...' : '') : 'No subject';
              localChats.push({
                id: chatId,
                date: messages.length > 0 ? messages[0].timestamp : 'Unknown date',
                preview: subject,
                name: ''
              });
            } catch (e) {
              console.error(`Error parsing messages for chat ${chatId}:`, e);
            }
          }
        }
      }
      history.value = localChats;
    };

    const clearHistory = async () => {
      try {
        // Since clearing all chats might be destructive, we'll just clear the list for now
        // In a real implementation, you might want to delete each chat individually from backend
        history.value = [];
        console.log('Chat history cleared (local only)');
      } catch (error) {
        console.error('Error clearing chat history:', error);
      }
    };

    const viewHistoryEntry = (entry) => {
      // Navigate to the chat in ChatInterface by updating the URL hash
      window.location.hash = `chatId=${entry.id}`;
      console.log('Viewing history entry:', entry.id);
    };

    const deleteHistoryEntry = async (entry) => {
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/api/chats/${entry.id}`, {
          method: 'DELETE',
          headers: {
            'Content-Type': 'application/json'
          }
        });
        if (response.ok) {
          // Remove from local storage
          localStorage.removeItem(`chat_${entry.id}_messages`);
          // Remove from history list
          history.value = history.value.filter(e => e.id !== entry.id);
          console.log('Deleted history entry:', entry.id);
        } else {
          console.error('Failed to delete chat history entry:', response.statusText);
        }
      } catch (error) {
        console.error('Error deleting chat history entry:', error);
      }
    };

    // Settings structure to match ChatInterface
    const settings = ref({
      backend: {
        api_endpoint: 'http://localhost:8001'
      }
    });

    // Load settings from local storage if available
    const savedSettings = localStorage.getItem('chat_settings');
    if (savedSettings) {
      settings.value = JSON.parse(savedSettings);
    }

    // Initial load of history after settings are initialized
    refreshHistory();

    return {
      history,
      refreshHistory,
      clearHistory,
      viewHistoryEntry,
      deleteHistoryEntry,
      settings
    };
  }
};
</script>

<style scoped>
.history-view {
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
  padding: 15px;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.history-view h2 {
  margin: 0 0 15px 0;
  font-size: 20px;
  color: #007bff;
}

.history-actions {
  display: flex;
  gap: 10px;
  margin-bottom: 15px;
}

.history-actions button {
  background-color: #007bff;
  color: white;
  border: none;
  padding: 8px 15px;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.3s;
}

.history-actions button:hover {
  background-color: #0056b3;
}

.history-actions button:last-child {
  background-color: #dc3545;
}

.history-actions button:last-child:hover {
  background-color: #c82333;
}

.history-list-container {
  flex: 1;
  overflow-y: auto;
  border: 1px solid #e9ecef;
  border-radius: 4px;
  padding: 10px;
}

.no-history {
  text-align: center;
  color: #6c757d;
  font-style: italic;
  padding: 20px;
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
  border: 1px solid #dee2e6;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.3s;
}

.history-entry:hover {
  background-color: #f1f1f1;
}

.history-summary {
  flex: 1;
  overflow: hidden;
}

.history-date {
  font-size: 14px;
  color: #6c757d;
  display: block;
  margin-bottom: 5px;
}

.history-preview {
  font-size: 16px;
  color: #343a40;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
}

.history-actions-entry button {
  background-color: #dc3545;
  color: white;
  border: none;
  padding: 5px 10px;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.3s;
}

.history-actions-entry button:hover {
  background-color: #c82333;
}
</style>
