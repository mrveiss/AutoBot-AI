<template>
  <div class="knowledge-manager">
    <h2>Knowledge Base Manager</h2>
    
    <div class="tabs">
      <button 
        v-for="tab in tabs" 
        :key="tab.id"
        :class="['tab-button', { active: activeTab === tab.id }]"
        @click="activeTab = tab.id"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- Search Tab -->
    <div v-if="activeTab === 'search'" class="tab-content">
      <h3>Search Knowledge Base</h3>
      <div class="search-form">
        <input 
          v-model="searchQuery" 
          type="text" 
          placeholder="Enter search query..."
          @keyup.enter="performSearch"
        />
        <button @click="performSearch" :disabled="searching">
          {{ searching ? 'Searching...' : 'Search' }}
        </button>
      </div>
      
      <div v-if="searchResults.length > 0" class="search-results">
        <h4>Search Results ({{ searchResults.length }})</h4>
        <div v-for="(result, index) in searchResults" :key="index" class="search-result">
          <div class="result-score">Score: {{ result.score?.toFixed(3) || 'N/A' }}</div>
          <div class="result-content">{{ result.content || result.text || 'No content' }}</div>
          <div class="result-metadata" v-if="result.metadata">
            <span v-for="(value, key) in result.metadata" :key="key">
              <strong>{{ key }}:</strong> {{ value }}
            </span>
          </div>
        </div>
      </div>
      
      <div v-else-if="searchPerformed && !searching" class="no-results">
        No results found for "{{ lastSearchQuery }}"
      </div>
    </div>

    <!-- Add Content Tab -->
    <div v-if="activeTab === 'add'" class="tab-content">
      <h3>Add Content to Knowledge Base</h3>
      
      <div class="add-form">
        <div class="form-group">
          <label>Content Type:</label>
          <select v-model="addContentType">
            <option value="text">Text</option>
            <option value="url">URL/Link</option>
            <option value="file">File Upload</option>
          </select>
        </div>

        <!-- Text Input -->
        <div v-if="addContentType === 'text'" class="form-group">
          <label>Text Content:</label>
          <textarea 
            v-model="textContent" 
            placeholder="Enter your text content here..."
            rows="8"
          ></textarea>
          <div class="form-row">
            <input v-model="textTitle" type="text" placeholder="Title (optional)" />
            <input v-model="textSource" type="text" placeholder="Source (optional)" />
          </div>
        </div>

        <!-- URL Input -->
        <div v-if="addContentType === 'url'" class="form-group">
          <label>URL:</label>
          <input v-model="urlContent" type="url" placeholder="https://example.com" />
          <div class="url-options">
            <label>
              <input type="radio" v-model="urlMethod" value="fetch" />
              Fetch and store content
            </label>
            <label>
              <input type="radio" v-model="urlMethod" value="reference" />
              Store as reference only
            </label>
          </div>
        </div>

        <!-- File Upload -->
        <div v-if="addContentType === 'file'" class="form-group">
          <label>File:</label>
          <input type="file" @change="handleFileUpload" accept=".txt,.md,.pdf,.docx" />
          <div v-if="selectedFile" class="file-info">
            Selected: {{ selectedFile.name }} ({{ formatFileSize(selectedFile.size) }})
          </div>
        </div>

        <button @click="addContent" :disabled="adding" class="add-button">
          {{ adding ? 'Adding...' : 'Add to Knowledge Base' }}
        </button>
      </div>

      <div v-if="addMessage" :class="['message', addMessageType]">
        {{ addMessage }}
      </div>
    </div>

    <!-- Manage Tab -->
    <div v-if="activeTab === 'manage'" class="tab-content">
      <h3>Manage Knowledge Base</h3>
      
      <div class="manage-actions">
        <button @click="exportKnowledgeBase" :disabled="exporting">
          {{ exporting ? 'Exporting...' : 'Export Knowledge Base' }}
        </button>
        <button @click="cleanupKnowledgeBase" :disabled="cleaning" class="warning">
          {{ cleaning ? 'Cleaning...' : 'Cleanup Old Entries' }}
        </button>
      </div>

      <div v-if="manageMessage" :class="['message', manageMessageType]">
        {{ manageMessage }}
      </div>
    </div>

    <!-- Statistics Tab -->
    <div v-if="activeTab === 'stats'" class="tab-content">
      <h3>Knowledge Base Statistics</h3>
      
      <button @click="loadStats" :disabled="loadingStats" class="refresh-button">
        {{ loadingStats ? 'Loading...' : 'Refresh Statistics' }}
      </button>

      <div v-if="stats" class="stats-grid">
        <div class="stat-card">
          <h4>Total Facts</h4>
          <div class="stat-value">{{ stats.total_facts || 0 }}</div>
          <div class="stat-description">Stored knowledge entries</div>
        </div>
        
        <div class="stat-card">
          <h4>Total Documents</h4>
          <div class="stat-value">{{ stats.total_documents || 0 }}</div>
          <div class="stat-description">Document entries</div>
        </div>
        
        <div class="stat-card">
          <h4>Total Vectors</h4>
          <div class="stat-value">{{ stats.total_vectors || 0 }}</div>
          <div class="stat-description">Vector embeddings</div>
        </div>
        
        <div class="stat-card">
          <h4>Database Size</h4>
          <div class="stat-value">{{ formatFileSize(stats.db_size || 0) }}</div>
          <div class="stat-description">Storage used</div>
        </div>
      </div>

      <div v-if="detailedStats" class="detailed-stats">
        <h4>Detailed Statistics</h4>
        <pre>{{ JSON.stringify(detailedStats, null, 2) }}</pre>
      </div>

      <div v-if="statsMessage" :class="['message', statsMessageType]">
        {{ statsMessage }}
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue';

export default {
  name: 'KnowledgeManager',
  setup() {
    // Tab management
    const activeTab = ref('search');
    const tabs = [
      { id: 'search', label: 'Search' },
      { id: 'add', label: 'Add Content' },
      { id: 'manage', label: 'Manage' },
      { id: 'stats', label: 'Statistics' }
    ];

    // Search functionality
    const searchQuery = ref('');
    const searchResults = ref([]);
    const searching = ref(false);
    const searchPerformed = ref(false);
    const lastSearchQuery = ref('');

    // Add content functionality
    const addContentType = ref('text');
    const textContent = ref('');
    const textTitle = ref('');
    const textSource = ref('');
    const urlContent = ref('');
    const urlMethod = ref('fetch');
    const selectedFile = ref(null);
    const adding = ref(false);
    const addMessage = ref('');
    const addMessageType = ref('');

    // Manage functionality
    const exporting = ref(false);
    const cleaning = ref(false);
    const manageMessage = ref('');
    const manageMessageType = ref('');

    // Statistics functionality
    const stats = ref(null);
    const detailedStats = ref(null);
    const loadingStats = ref(false);
    const statsMessage = ref('');
    const statsMessageType = ref('');

    // Settings
    const settings = ref({
      backend: {
        api_endpoint: 'http://localhost:8001'
      }
    });

    // Load settings from localStorage
    const loadSettings = () => {
      const savedSettings = localStorage.getItem('chat_settings');
      if (savedSettings) {
        try {
          settings.value = JSON.parse(savedSettings);
        } catch (e) {
          console.error('Error loading settings:', e);
        }
      }
    };

    // Search functionality
    const performSearch = async () => {
      if (!searchQuery.value.trim()) return;
      
      searching.value = true;
      searchPerformed.value = true;
      lastSearchQuery.value = searchQuery.value;
      
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/api/knowledge/search`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ 
            query: searchQuery.value,
            limit: 10
          })
        });

        if (response.ok) {
          const data = await response.json();
          searchResults.value = data.results || [];
        } else {
          console.error('Search failed:', response.statusText);
          searchResults.value = [];
        }
      } catch (error) {
        console.error('Search error:', error);
        searchResults.value = [];
      } finally {
        searching.value = false;
      }
    };

    // Add content functionality
    const handleFileUpload = (event) => {
      selectedFile.value = event.target.files[0];
    };

    const addContent = async () => {
      adding.value = true;
      addMessage.value = '';
      
      try {
        let requestData = {};
        let endpoint = '';

        if (addContentType.value === 'text') {
          if (!textContent.value.trim()) {
            addMessage.value = 'Please enter some text content.';
            addMessageType.value = 'error';
            return;
          }
          endpoint = '/api/knowledge/add_text';
          requestData = {
            text: textContent.value,
            title: textTitle.value,
            source: textSource.value || 'Manual Entry'
          };
        } else if (addContentType.value === 'url') {
          if (!urlContent.value.trim()) {
            addMessage.value = 'Please enter a URL.';
            addMessageType.value = 'error';
            return;
          }
          endpoint = '/api/knowledge/add_url';
          requestData = {
            url: urlContent.value,
            method: urlMethod.value
          };
        } else if (addContentType.value === 'file') {
          if (!selectedFile.value) {
            addMessage.value = 'Please select a file.';
            addMessageType.value = 'error';
            return;
          }
          
          const formData = new FormData();
          formData.append('file', selectedFile.value);
          
          const response = await fetch(`${settings.value.backend.api_endpoint}/api/knowledge/add_file`, {
            method: 'POST',
            body: formData
          });

          if (response.ok) {
            const result = await response.json();
            addMessage.value = result.message || 'File added successfully!';
            addMessageType.value = 'success';
            selectedFile.value = null;
          } else {
            const error = await response.json();
            addMessage.value = error.detail || 'Failed to add file.';
            addMessageType.value = 'error';
          }
          return;
        }

        const response = await fetch(`${settings.value.backend.api_endpoint}${endpoint}`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(requestData)
        });

        if (response.ok) {
          const result = await response.json();
          addMessage.value = result.message || 'Content added successfully!';
          addMessageType.value = 'success';
          
          // Clear form
          if (addContentType.value === 'text') {
            textContent.value = '';
            textTitle.value = '';
            textSource.value = '';
          } else if (addContentType.value === 'url') {
            urlContent.value = '';
          }
        } else {
          const error = await response.json();
          addMessage.value = error.detail || 'Failed to add content.';
          addMessageType.value = 'error';
        }
      } catch (error) {
        console.error('Add content error:', error);
        addMessage.value = 'Error adding content. Please try again.';
        addMessageType.value = 'error';
      } finally {
        adding.value = false;
      }
    };

    // Manage functionality
    const exportKnowledgeBase = async () => {
      exporting.value = true;
      manageMessage.value = '';
      
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/api/knowledge/export`);
        
        if (response.ok) {
          const blob = await response.blob();
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `knowledge_base_export_${new Date().toISOString().split('T')[0]}.json`;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          window.URL.revokeObjectURL(url);
          
          manageMessage.value = 'Knowledge base exported successfully!';
          manageMessageType.value = 'success';
        } else {
          const error = await response.json();
          manageMessage.value = error.detail || 'Failed to export knowledge base.';
          manageMessageType.value = 'error';
        }
      } catch (error) {
        console.error('Export error:', error);
        manageMessage.value = 'Error exporting knowledge base.';
        manageMessageType.value = 'error';
      } finally {
        exporting.value = false;
      }
    };

    const cleanupKnowledgeBase = async () => {
      if (!confirm('Are you sure you want to cleanup old entries? This action cannot be undone.')) {
        return;
      }
      
      cleaning.value = true;
      manageMessage.value = '';
      
      try {
        const response = await fetch(`${settings.value.backend.api_endpoint}/api/knowledge/cleanup`, {
          method: 'POST'
        });
        
        if (response.ok) {
          const result = await response.json();
          manageMessage.value = result.message || 'Cleanup completed successfully!';
          manageMessageType.value = 'success';
        } else {
          const error = await response.json();
          manageMessage.value = error.detail || 'Failed to cleanup knowledge base.';
          manageMessageType.value = 'error';
        }
      } catch (error) {
        console.error('Cleanup error:', error);
        manageMessage.value = 'Error cleaning up knowledge base.';
        manageMessageType.value = 'error';
      } finally {
        cleaning.value = false;
      }
    };

    // Statistics functionality
    const loadStats = async () => {
      loadingStats.value = true;
      statsMessage.value = '';
      
      try {
        // Load basic stats
        const response = await fetch(`${settings.value.backend.api_endpoint}/api/knowledge/stats`);
        
        if (response.ok) {
          stats.value = await response.json();
          
          // Load detailed stats
          const detailedResponse = await fetch(`${settings.value.backend.api_endpoint}/api/knowledge/detailed_stats`);
          if (detailedResponse.ok) {
            detailedStats.value = await detailedResponse.json();
          }
          
          statsMessage.value = 'Statistics loaded successfully!';
          statsMessageType.value = 'success';
        } else {
          const error = await response.json();
          statsMessage.value = error.detail || 'Failed to load statistics.';
          statsMessageType.value = 'error';
        }
      } catch (error) {
        console.error('Stats loading error:', error);
        statsMessage.value = 'Error loading statistics.';
        statsMessageType.value = 'error';
      } finally {
        loadingStats.value = false;
      }
    };

    // Utility functions
    const formatFileSize = (bytes) => {
      if (bytes === 0) return '0 Bytes';
      const k = 1024;
      const sizes = ['Bytes', 'KB', 'MB', 'GB'];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    };

    // Initialize component
    onMounted(() => {
      loadSettings();
      loadStats();
    });

    return {
      // Tab management
      activeTab,
      tabs,
      
      // Search
      searchQuery,
      searchResults,
      searching,
      searchPerformed,
      lastSearchQuery,
      performSearch,
      
      // Add content
      addContentType,
      textContent,
      textTitle,
      textSource,
      urlContent,
      urlMethod,
      selectedFile,
      adding,
      addMessage,
      addMessageType,
      handleFileUpload,
      addContent,
      
      // Manage
      exporting,
      cleaning,
      manageMessage,
      manageMessageType,
      exportKnowledgeBase,
      cleanupKnowledgeBase,
      
      // Statistics
      stats,
      detailedStats,
      loadingStats,
      statsMessage,
      statsMessageType,
      loadStats,
      
      // Utilities
      formatFileSize
    };
  }
};
</script>

<style scoped>
.knowledge-manager {
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
  padding: 20px;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.knowledge-manager h2 {
  margin: 0 0 20px 0;
  color: #007bff;
  font-size: 24px;
}

.tabs {
  display: flex;
  border-bottom: 2px solid #e9ecef;
  margin-bottom: 20px;
}

.tab-button {
  background: none;
  border: none;
  padding: 12px 20px;
  cursor: pointer;
  font-size: 16px;
  color: #6c757d;
  border-bottom: 2px solid transparent;
  transition: all 0.3s;
}

.tab-button:hover {
  color: #007bff;
}

.tab-button.active {
  color: #007bff;
  border-bottom-color: #007bff;
  font-weight: bold;
}

.tab-content {
  flex: 1;
  overflow-y: auto;
}

.tab-content h3 {
  margin: 0 0 20px 0;
  color: #333;
  font-size: 20px;
}

/* Search styles */
.search-form {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}

.search-form input {
  flex: 1;
  padding: 10px;
  border: 1px solid #ced4da;
  border-radius: 4px;
  font-size: 14px;
}

.search-form button {
  background-color: #007bff;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  white-space: nowrap;
}

.search-form button:hover:not(:disabled) {
  background-color: #0056b3;
}

.search-form button:disabled {
  background-color: #6c757d;
  cursor: not-allowed;
}

.search-results h4 {
  color: #333;
  margin-bottom: 15px;
}

.search-result {
  border: 1px solid #e9ecef;
  border-radius: 4px;
  padding: 15px;
  margin-bottom: 10px;
  background-color: #f8f9fa;
}

.result-score {
  font-size: 12px;
  color: #6c757d;
  margin-bottom: 5px;
}

.result-content {
  margin-bottom: 10px;
  line-height: 1.5;
}

.result-metadata {
  font-size: 12px;
  color: #6c757d;
}

.result-metadata span {
  margin-right: 15px;
}

.no-results {
  text-align: center;
  color: #6c757d;
  font-style: italic;
  padding: 40px;
}

/* Add content styles */
.add-form {
  max-width: 600px;
}

.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: block;
  margin-bottom: 5px;
  font-weight: bold;
  color: #333;
}

.form-group select,
.form-group input,
.form-group textarea {
  width: 100%;
  padding: 10px;
  border: 1px solid #ced4da;
  border-radius: 4px;
  font-size: 14px;
}

.form-group textarea {
  resize: vertical;
  min-height: 120px;
}

.form-row {
  display: flex;
  gap: 10px;
  margin-top: 10px;
}

.form-row input {
  flex: 1;
}

.url-options {
  margin-top: 10px;
}

.url-options label {
  display: flex;
  align-items: center;
  margin-bottom: 5px;
  font-weight: normal;
}

.url-options input[type="radio"] {
  width: auto;
  margin-right: 5px;
}

.file-info {
  margin-top: 10px;
  padding: 10px;
  background-color: #e9ecef;
  border-radius: 4px;
  font-size: 14px;
}

.add-button {
  background-color: #28a745;
  color: white;
  border: none;
  padding: 12px 24px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 16px;
  font-weight: bold;
}

.add-button:hover:not(:disabled) {
  background-color: #218838;
}

.add-button:disabled {
  background-color: #6c757d;
  cursor: not-allowed;
}

/* Manage styles */
.manage-actions {
  display: flex;
  gap: 15px;
  margin-bottom: 20px;
}

.manage-actions button {
  background-color: #007bff;
  color: white;
  border: none;
  padding: 12px 20px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.manage-actions button:hover:not(:disabled) {
  background-color: #0056b3;
}

.manage-actions button.warning {
  background-color: #ffc107;
  color: #212529;
}

.manage-actions button.warning:hover:not(:disabled) {
  background-color: #e0a800;
}

.manage-actions button:disabled {
  background-color: #6c757d;
  cursor: not-allowed;
}

/* Statistics styles */
.refresh-button {
  background-color: #007bff;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  margin-bottom: 20px;
}

.refresh-button:hover:not(:disabled) {
  background-color: #0056b3;
}

.refresh-button:disabled {
  background-color: #6c757d;
  cursor: not-allowed;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
  margin-bottom: 30px;
}

.stat-card {
  background-color: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 8px;
  padding: 20px;
  text-align: center;
}

.stat-card h4 {
  margin: 0 0 10px 0;
  color: #333;
  font-size: 16px;
}

.stat-value {
  font-size: 32px;
  font-weight: bold;
  color: #007bff;
  margin-bottom: 5px;
}

.stat-description {
  font-size: 14px;
  color: #6c757d;
}

.detailed-stats {
  margin-top: 30px;
}

.detailed-stats h4 {
  margin-bottom: 15px;
  color: #333;
}

.detailed-stats pre {
  background-color: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 4px;
  padding: 15px;
  font-size: 12px;
  overflow-x: auto;
}

/* Message styles */
.message {
  padding: 12px;
  border-radius: 4px;
  margin-top: 15px;
  font-size: 14px;
}

.message.success {
  background-color: #d4edda;
  color: #155724;
  border: 1px solid #c3e6cb;
}

.message.error {
  background-color: #f8d7da;
  color: #721c24;
  border: 1px solid #f5c6cb;
}

/* Responsive design */
@media (max-width: 768px) {
  .knowledge-manager {
    padding: 15px;
  }
  
  .tabs {
    flex-wrap: wrap;
  }
  
  .tab-button {
    flex: 1;
    min-width: 120px;
  }
  
  .search-form {
    flex-direction: column;
  }
  
  .manage-actions {
    flex-direction: column;
  }
  
  .stats-grid {
    grid-template-columns: 1fr;
  }
  
  .form-row {
    flex-direction: column;
  }
}
</style>
