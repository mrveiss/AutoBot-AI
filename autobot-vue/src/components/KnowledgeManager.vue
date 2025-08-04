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

    <!-- Templates Tab -->
    <div v-if="activeTab === 'templates'" class="tab-content">
      <div class="templates-header">
        <h3>Knowledge Entry Templates</h3>
        <button @click="showCreateTemplateModal = true" class="create-btn">
          <span class="icon">📝</span> Create Template
        </button>
      </div>

      <div class="templates-grid">
        <div v-for="template in knowledgeTemplates" :key="template.id" class="template-card" @click="useTemplate(template)">
          <div class="template-icon">{{ template.icon }}</div>
          <h4>{{ template.name }}</h4>
          <p>{{ template.description }}</p>
          <div class="template-fields">
            <span v-for="field in template.fields.slice(0, 3)" :key="field" class="field-tag">{{ typeof field === 'string' ? field : field.name }}</span>
            <span v-if="template.fields.length > 3" class="more-fields">+{{ template.fields.length - 3 }} more</span>
          </div>
          <div class="template-actions" @click.stop>
            <button @click="editTemplate(template)" class="edit-template-btn" title="Edit Template">✏️</button>
            <button @click="deleteTemplate(template.id)" class="delete-template-btn" title="Delete Template">🗑️</button>
          </div>
        </div>

        <!-- Add custom template card -->
        <div class="template-card add-template" @click="showCreateTemplateModal = true">
          <div class="template-icon">➕</div>
          <h4>Create Custom Template</h4>
          <p>Design your own knowledge entry template</p>
        </div>
      </div>
    </div>

    <!-- Knowledge Entries Tab -->
    <div v-if="activeTab === 'entries'" class="tab-content">
      <div class="entries-header">
        <h3>Knowledge Entries</h3>
        <button @click="showCreateModal = true" class="create-btn">
          <span class="icon">+</span> Add New Entry
        </button>
      </div>

      <div class="entries-content">
        <div class="search-bar">
          <input
            type="text"
            v-model="entriesSearchQuery"
            placeholder="Search entries by content, source, or tags..."
            class="search-input"
          />
          <button @click="filterEntries" class="search-btn">Search</button>
          <button @click="refreshEntries" class="refresh-btn">Refresh</button>
        </div>

        <div class="entries-stats" v-if="knowledgeEntries.length > 0">
          <span>{{ filteredKnowledgeEntries.length }} of {{ knowledgeEntries.length }} entries</span>
        </div>

        <div class="entries-list" v-if="knowledgeEntries.length > 0">
          <div v-for="entry in filteredKnowledgeEntries" :key="entry.id" class="entry-item">
            <div class="entry-header">
              <div class="entry-title">
                <h4>{{ getEntryTitle(entry) }}</h4>
                <div class="entry-tags" v-if="entry.metadata && entry.metadata.tags">
                  <span v-for="tag in entry.metadata.tags" :key="tag" class="tag">{{ tag }}</span>
                </div>
              </div>
              <div class="entry-actions">
                <button @click="viewEntry(entry)" class="view-btn" title="View Details">
                  <span class="icon">👁</span>
                </button>
                <button @click="editEntry(entry)" class="edit-btn" title="Edit">
                  <span class="icon">✏️</span>
                </button>
                <button v-if="isUrlEntry(entry)" @click="crawlUrl(entry)" class="crawl-btn" title="Crawl URL Content">
                  <span class="icon">🕷️</span>
                </button>
                <button @click="duplicateEntry(entry)" class="duplicate-btn" title="Duplicate">
                  <span class="icon">📋</span>
                </button>
                <button @click="deleteEntry(entry.id)" class="delete-btn" title="Delete">
                  <span class="icon">🗑️</span>
                </button>
              </div>
            </div>

            <div class="entry-preview">
              <p>{{ getEntryPreview(entry) }}</p>
            </div>

            <div class="entry-meta">
              <span class="entry-source" v-if="entry.metadata && entry.metadata.source">
                <span class="icon">📄</span> {{ entry.metadata.source }}
              </span>
              <span class="entry-date" v-if="entry.metadata && entry.metadata.created_at">
                <span class="icon">📅</span> {{ formatDate(entry.metadata.created_at) }}
              </span>
              <span class="entry-collection" v-if="entry.collection">
                <span class="icon">📁</span> {{ entry.collection }}
              </span>
              <span class="entry-links" v-if="entry.metadata && entry.metadata.links && entry.metadata.links.length > 0">
                <span class="icon">🔗</span> {{ entry.metadata.links.length }} links
              </span>
            </div>
          </div>
        </div>

        <div v-else class="no-entries">
          <div class="empty-state">
            <span class="icon large">📚</span>
            <h4>No knowledge entries found</h4>
            <p>Start by adding your first knowledge entry or uploading documents.</p>
            <button @click="showCreateModal = true" class="create-btn primary">
              Add Your First Entry
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Entry Modal (Create/Edit/View) -->
    <div v-if="showCreateModal || showEditModal || showViewModal" class="modal-overlay" @click="closeModals">
      <div class="modal" @click.stop>
        <div class="modal-header">
          <h3 v-if="showCreateModal">Create New Entry</h3>
          <h3 v-else-if="showEditModal">Edit Entry</h3>
          <h3 v-else>View Entry</h3>
          <button @click="closeModals" class="close-btn">&times;</button>
        </div>

        <div class="modal-body">
          <form @submit.prevent="saveEntry" v-if="showCreateModal || showEditModal">
            <div class="form-group">
              <label for="entry-title">Title/Subject</label>
              <input
                type="text"
                id="entry-title"
                v-model="currentEntry.title"
                placeholder="Enter a descriptive title for this entry"
              />
            </div>

            <div class="form-row">
              <div class="form-group">
                <label for="entry-source">Source</label>
                <input
                  type="text"
                  id="entry-source"
                  v-model="currentEntry.source"
                  placeholder="Document name, URL, or source reference"
                />
                <small v-if="isUrlSource(currentEntry.source)" class="url-hint">
                  🕷️ URL detected - you can leave content empty to auto-crawl
                </small>
              </div>

              <div class="form-group">
                <label for="entry-collection">Collection</label>
                <input
                  type="text"
                  id="entry-collection"
                  v-model="currentEntry.collection"
                  placeholder="Collection name"
                />
              </div>
            </div>

            <div class="form-group">
              <label for="entry-content">Content</label>
              <textarea
                id="entry-content"
                v-model="currentEntry.content"
                rows="8"
                :placeholder="isUrlSource(currentEntry.source) ? 'Leave empty to auto-crawl from URL, or enter content manually' : 'Enter the knowledge content...'"
                :required="!isUrlSource(currentEntry.source)"
              ></textarea>
              <small v-if="isUrlSource(currentEntry.source) && !currentEntry.content" class="auto-crawl-hint">
                ✨ Content will be automatically crawled from the URL when you save
              </small>
            </div>

            <div class="form-group">
              <label for="entry-tags">Tags</label>
              <input
                type="text"
                id="entry-tags"
                v-model="tagsInput"
                placeholder="Enter tags separated by commas"
                @input="updateTags"
              />
              <div class="tags-preview" v-if="currentEntry.tags && currentEntry.tags.length > 0">
                <span v-for="tag in currentEntry.tags" :key="tag" class="tag">
                  {{ tag }}
                  <button type="button" @click="removeTag(tag)" class="tag-remove">&times;</button>
                </span>
              </div>
            </div>

            <div class="form-group">
              <label>Links</label>
              <div class="links-section">
                <div class="link-input-group">
                  <input
                    type="url"
                    v-model="newLink.url"
                    placeholder="https://example.com"
                  />
                  <input
                    type="text"
                    v-model="newLink.title"
                    placeholder="Link title (optional)"
                  />
                  <button type="button" @click="addLink" class="add-link-btn">
                    <span class="icon">🔗</span> Add
                  </button>
                </div>

                <div class="links-list" v-if="currentEntry.links && currentEntry.links.length > 0">
                  <div v-for="(link, index) in currentEntry.links" :key="index" class="link-item">
                    <a :href="link.url" target="_blank" class="link-url">
                      {{ link.title || link.url }}
                    </a>
                    <button type="button" @click="removeLink(index)" class="remove-btn">&times;</button>
                  </div>
                </div>
              </div>
            </div>

            <div class="modal-actions">
              <button type="button" @click="closeModals" class="cancel-btn">Cancel</button>
              <button
                v-if="showEditModal && isUrlSource(currentEntry.source)"
                type="button"
                @click="crawlCurrentEntry"
                class="crawl-btn-modal"
                :disabled="crawlingInModal"
              >
                <span v-if="crawlingInModal">🔄 Crawling...</span>
                <span v-else>🕷️ Re-crawl URL</span>
              </button>
              <button type="submit" class="save-btn">
                {{ showCreateModal ? 'Create Entry' : 'Save Changes' }}
              </button>
            </div>
          </form>

          <!-- View Mode -->
          <div v-else class="entry-view">
            <div class="view-section">
              <h4>Content</h4>
              <div class="content-display">{{ currentEntry.content }}</div>
            </div>

            <div class="view-meta">
              <div class="meta-item" v-if="currentEntry.source">
                <strong>Source:</strong> {{ currentEntry.source }}
              </div>
              <div class="meta-item" v-if="currentEntry.collection">
                <strong>Collection:</strong> {{ currentEntry.collection }}
              </div>
              <div class="meta-item" v-if="currentEntry.tags && currentEntry.tags.length > 0">
                <strong>Tags:</strong>
                <div class="tags-display">
                  <span v-for="tag in currentEntry.tags" :key="tag" class="tag">{{ tag }}</span>
                </div>
              </div>
              <div class="meta-item" v-if="currentEntry.created_at">
                <strong>Created:</strong> {{ formatDate(currentEntry.created_at) }}
              </div>
            </div>

            <div class="view-section" v-if="currentEntry.links && currentEntry.links.length > 0">
              <h4>Links</h4>
              <div class="links-display">
                <div v-for="link in currentEntry.links" :key="link.url" class="link-display">
                  <span class="icon">🔗</span>
                  <a :href="link.url" target="_blank">{{ link.title || link.url }}</a>
                </div>
              </div>
            </div>

            <div class="modal-actions">
              <button @click="editEntry(currentEntry)" class="edit-btn">Edit Entry</button>
              <button @click="closeModals" class="close-btn">Close</button>
            </div>
          </div>
        </div>
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
import apiClient from '../utils/ApiClient.js';

export default {
  name: 'KnowledgeManager',
  setup() {
    // Tab management
    const activeTab = ref('search');
    const tabs = [
      { id: 'search', label: 'Search' },
      { id: 'entries', label: 'Knowledge Entries' },
      { id: 'templates', label: 'Templates' },
      { id: 'manage', label: 'Manage' },
      { id: 'stats', label: 'Statistics' }
    ];

    // Search functionality
    const searchQuery = ref('');
    const searchResults = ref([]);
    const searching = ref(false);
    const searchPerformed = ref(false);
    const lastSearchQuery = ref('');

    // Knowledge Entries functionality
    const knowledgeEntries = ref([]);
    const filteredKnowledgeEntries = ref([]);
    const entriesSearchQuery = ref('');
    const loading = ref(false);
    const showCreateModal = ref(false);
    const showEditModal = ref(false);
    const showViewModal = ref(false);
    const currentEntry = ref({
      title: '',
      content: '',
      source: '',
      collection: 'default',
      tags: [],
      links: []
    });
    const tagsInput = ref('');
    const newLink = ref({ url: '', title: '' });

    // Templates functionality
    const knowledgeTemplates = ref([
      {
        id: 1,
        name: 'Research Article',
        icon: '📊',
        category: 'research',
        description: 'Template for documenting research findings and analysis',
        fields: ['title', 'author', 'summary', 'key_findings', 'methodology', 'conclusions'],
        contentTemplate: `# {{title}}\n\n**Author:** {{author}}\n**Date:** {{date}}\n\n## Summary\n{{summary}}\n\n## Key Findings\n{{key_findings}}\n\n## Methodology\n{{methodology}}\n\n## Conclusions\n{{conclusions}}\n\n## References\n{{references}}`
      },
      {
        id: 2,
        name: 'Meeting Notes',
        icon: '📋',
        category: 'business',
        description: 'Template for capturing meeting discussions and action items',
        fields: ['meeting_title', 'date', 'attendees', 'agenda', 'discussion', 'action_items', 'next_meeting'],
        contentTemplate: `# {{meeting_title}}\n\n**Date:** {{date}}\n**Attendees:** {{attendees}}\n\n## Agenda\n{{agenda}}\n\n## Discussion Points\n{{discussion}}\n\n## Action Items\n{{action_items}}\n\n## Next Meeting\n{{next_meeting}}`
      },
      {
        id: 3,
        name: 'Bug Report',
        icon: '🐛',
        category: 'development',
        description: 'Template for documenting software bugs and issues',
        fields: ['bug_title', 'severity', 'steps_to_reproduce', 'expected_behavior', 'actual_behavior', 'environment', 'screenshots'],
        contentTemplate: `# Bug: {{bug_title}}\n\n**Severity:** {{severity}}\n**Environment:** {{environment}}\n\n## Steps to Reproduce\n{{steps_to_reproduce}}\n\n## Expected Behavior\n{{expected_behavior}}\n\n## Actual Behavior\n{{actual_behavior}}\n\n## Screenshots/Evidence\n{{screenshots}}`
      },
      {
        id: 4,
        name: 'Learning Notes',
        icon: '🎓',
        category: 'personal',
        description: 'Template for documenting learning and study materials',
        fields: ['topic', 'source', 'key_concepts', 'examples', 'questions', 'related_topics'],
        contentTemplate: `# Learning: {{topic}}\n\n**Source:** {{source}}\n**Date:** {{date}}\n\n## Key Concepts\n{{key_concepts}}\n\n## Examples\n{{examples}}\n\n## Questions for Further Study\n{{questions}}\n\n## Related Topics\n{{related_topics}}`
      }
    ]);

    const showCreateTemplateModal = ref(false);
    const showEditTemplateModal = ref(false);
    const currentTemplate = ref({
      name: '',
      icon: '📝',
      category: 'general',
      description: '',
      fields: [
        { name: 'title', type: 'text', placeholder: 'Enter title' },
        { name: 'content', type: 'textarea', placeholder: 'Enter main content' }
      ],
      contentTemplate: '# {{title}}\n\n{{content}}'
    });

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
        const data = await apiClient.searchKnowledge(searchQuery.value);
        searchResults.value = data.results || [];
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

          const result = await apiClient.addFileToKnowledge(selectedFile.value);
          addMessage.value = result.message || 'File added successfully!';
          addMessageType.value = 'success';
          selectedFile.value = null;

          // Refresh knowledge entries list to show the new entry
          await loadKnowledgeEntries();
          return;
        }

        let result;
        if (addContentType.value === 'text') {
          result = await apiClient.addTextToKnowledge(textContent.value, textTitle.value, textSource.value);
        } else if (addContentType.value === 'url') {
          result = await apiClient.addUrlToKnowledge(urlContent.value, urlMethod.value);
        }

        addMessage.value = result.message || 'Content added successfully!';
        addMessageType.value = 'success';

        // Refresh knowledge entries list to show the new entry
        await loadKnowledgeEntries();

        // Clear form
        if (addContentType.value === 'text') {
          textContent.value = '';
          textTitle.value = '';
          textSource.value = '';
        } else if (addContentType.value === 'url') {
          urlContent.value = '';
        }
      } catch (error) {
        console.error('Add content error:', error);
        addMessage.value = 'Error adding content. Please try again.';
        addMessageType.value = 'error';
      } finally {
        adding.value = false;
      }
    };

    // Knowledge Entries functionality
    const loadKnowledgeEntries = async () => {
      try {
        loading.value = true;
        const response = await apiClient.get('/api/knowledge_base/entries');
        const data = await response.json();
        knowledgeEntries.value = data.entries || [];
        filteredKnowledgeEntries.value = knowledgeEntries.value;
      } catch (error) {
        console.error('Error loading knowledge entries:', error);
        knowledgeEntries.value = [];
        filteredKnowledgeEntries.value = [];
      } finally {
        loading.value = false;
      }
    };

    const filterEntries = () => {
      if (!entriesSearchQuery.value.trim()) {
        filteredKnowledgeEntries.value = knowledgeEntries.value;
        return;
      }

      const query = entriesSearchQuery.value.toLowerCase();
      filteredKnowledgeEntries.value = knowledgeEntries.value.filter(entry => {
        const content = (entry.content || '').toLowerCase();
        const source = (entry.metadata?.source || '').toLowerCase();
        const tags = (entry.metadata?.tags || []).join(' ').toLowerCase();
        const collection = (entry.collection || '').toLowerCase();

        return content.includes(query) || source.includes(query) ||
               tags.includes(query) || collection.includes(query);
      });
    };

    const refreshEntries = () => {
      loadKnowledgeEntries();
    };

    const getEntryTitle = (entry) => {
      return entry.title || entry.metadata?.title || entry.metadata?.source || 'Untitled Entry';
    };

    const getEntryPreview = (entry) => {
      const content = entry.content || '';
      return content.length > 150 ? content.substring(0, 150) + '...' : content;
    };

    const formatDate = (dateString) => {
      if (!dateString) return 'Unknown';
      try {
        return new Date(dateString).toLocaleDateString();
      } catch {
        return 'Unknown';
      }
    };

    const isUrlEntry = (entry) => {
      // Check if source contains a URL
      if (entry.metadata?.source) {
        try {
          new URL(entry.metadata.source);
          return entry.metadata.source.startsWith('http://') || entry.metadata.source.startsWith('https://');
        } catch {}
      }

      // Check if content contains URLs
      if (entry.content) {
        const urlRegex = /https?:\/\/[^\s]+/;
        return urlRegex.test(entry.content);
      }

      // Legacy checks
      return entry.metadata?.type === 'url_reference' ||
             entry.content?.startsWith('URL Reference:') ||
             entry.metadata?.url;
    };

    const crawlUrl = async (entry) => {
      if (!confirm('Crawl and extract content from this URL? This will replace the current content.')) {
        return;
      }

      try {
        let url = null;

        // Try to get URL from source first
        if (entry.metadata?.source) {
          try {
            new URL(entry.metadata.source);
            if (entry.metadata.source.startsWith('http://') || entry.metadata.source.startsWith('https://')) {
              url = entry.metadata.source;
            }
          } catch {}
        }

        // If no URL in source, extract from content
        if (!url) {
          url = extractUrlFromContent(entry.content);
        }

        // Legacy URL check
        if (!url && entry.metadata?.url) {
          url = entry.metadata.url;
        }

        if (!url) {
          showError('No URL found to crawl');
          return;
        }

        // Call backend to crawl URL and extract content
        const response = await fetch('/api/knowledge/crawl_url', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            entry_id: entry.id,
            url: url
          })
        });

        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || 'Failed to crawl URL');
        }

        const result = await response.json();
        showSuccess(`URL content crawled successfully! Extracted ${result.content_length} characters.`);
        await loadKnowledgeEntries(); // Refresh the list
      } catch (error) {
        console.error('Error crawling URL:', error);
        showError('Failed to crawl URL: ' + error.message);
      }
    };

    const extractUrlFromContent = (content) => {
      const urlRegex = /https?:\/\/[^\s]+/;
      const match = content?.match(urlRegex);
      return match ? match[0] : null;
    };

    const viewEntry = (entry) => {
      currentEntry.value = {
        ...entry,
        title: entry.title || entry.metadata?.title || '',
        source: entry.metadata?.source || '',
        collection: entry.collection || 'default',
        tags: entry.metadata?.tags || [],
        links: entry.metadata?.links || [],
        created_at: entry.metadata?.created_at
      };
      showViewModal.value = true;
    };

    const editEntry = (entry) => {
      currentEntry.value = {
        ...entry,
        source: entry.metadata?.source || '',
        collection: entry.collection || 'default',
        tags: entry.metadata?.tags || [],
        links: entry.metadata?.links || []
      };
      tagsInput.value = currentEntry.value.tags.join(', ');
      showViewModal.value = false;
      showEditModal.value = true;
    };

    const duplicateEntry = (entry) => {
      currentEntry.value = {
        content: entry.content,
        source: (entry.metadata?.source || '') + ' (Copy)',
        collection: entry.collection || 'default',
        tags: [...(entry.metadata?.tags || [])],
        links: [...(entry.metadata?.links || [])]
      };
      tagsInput.value = currentEntry.value.tags.join(', ');
      showCreateModal.value = true;
    };

    const deleteEntry = async (entryId) => {
      if (!confirm('Are you sure you want to delete this entry? This action cannot be undone.')) {
        return;
      }

      try {
        await apiClient.delete(`/api/knowledge_base/entries/${entryId}`);
        await loadKnowledgeEntries();
        showSuccess('Entry deleted successfully');
      } catch (error) {
        console.error('Error deleting entry:', error);
        showError('Failed to delete entry: ' + error.message);
      }
    };

    // URL detection helper for form
    const isUrlSource = (source) => {
      if (!source) return false;
      try {
        new URL(source);
        return source.startsWith('http://') || source.startsWith('https://');
      } catch {
        return false;
      }
    };

    // Crawl URL in modal
    const crawlingInModal = ref(false);
    const crawlCurrentEntry = async () => {
      if (!confirm('This will replace the current content with crawled content from the URL. Continue?')) {
        return;
      }

      crawlingInModal.value = true;
      try {
        const response = await fetch('/api/knowledge/crawl_url', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            entry_id: currentEntry.value.id,
            url: currentEntry.value.source
          })
        });

        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || 'Failed to crawl URL');
        }

        const result = await response.json();
        currentEntry.value.content = result.content || result.extracted_content || '';
        showSuccess(`Content crawled successfully! Extracted ${result.content_length || currentEntry.value.content.length} characters.`);
      } catch (error) {
        console.error('Error crawling URL in modal:', error);
        showError('Failed to crawl URL: ' + error.message);
      } finally {
        crawlingInModal.value = false;
      }
    };

    const saveEntry = async () => {
      try {
        loading.value = true;

        const entryData = {
          type: currentEntry.value.title || currentEntry.value.source || 'Manual Entry',
          content: currentEntry.value.content,
          source: currentEntry.value.source,
          title: currentEntry.value.title,
          metadata: {
            source: currentEntry.value.source,
            tags: currentEntry.value.tags,
            links: currentEntry.value.links,
            title: currentEntry.value.title
          }
        };

        let response;
        if (showEditModal.value) {
          response = await fetch(`/api/knowledge_base/entries/${currentEntry.value.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(entryData)
          });
        } else {
          response = await fetch('/api/knowledge_base/entries', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(entryData)
          });
        }

        if (!response.ok) {
          throw new Error(`Failed to ${showEditModal.value ? 'update' : 'create'} entry`);
        }

        // If it's a new URL entry with no content, auto-crawl it
        if (!showEditModal.value && isUrlSource(currentEntry.value.source) && !currentEntry.value.content) {
          const result = await response.json();
          if (result.id) {
            try {
              const crawlResponse = await fetch('/api/knowledge/crawl_url', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  entry_id: result.id,
                  url: currentEntry.value.source
                })
              });

              if (crawlResponse.ok) {
                const crawlResult = await crawlResponse.json();
                showSuccess(`Entry created and URL content crawled! Extracted ${crawlResult.content_length} characters.`);
              } else {
                showSuccess('Entry created successfully, but URL crawling failed.');
              }
            } catch (crawlError) {
              showSuccess('Entry created successfully, but URL crawling failed.');
            }
          }
        } else {
          showSuccess(showEditModal.value ? 'Entry updated successfully' : 'Entry created successfully');
        }

        await loadKnowledgeEntries();
        closeModals();
      } catch (error) {
        console.error('Error saving entry:', error);
        showError('Failed to save entry: ' + error.message);
      } finally {
        loading.value = false;
      }
    };

    const closeModals = () => {
      showCreateModal.value = false;
      showEditModal.value = false;
      showViewModal.value = false;
      currentEntry.value = {
        content: '',
        source: '',
        collection: 'default',
        tags: [],
        links: []
      };
      tagsInput.value = '';
      newLink.value = { url: '', title: '' };
    };

    const updateTags = () => {
      const tags = tagsInput.value
        .split(',')
        .map(tag => tag.trim())
        .filter(tag => tag.length > 0);
      currentEntry.value.tags = [...new Set(tags)]; // Remove duplicates
    };

    const removeTag = (tagToRemove) => {
      currentEntry.value.tags = currentEntry.value.tags.filter(tag => tag !== tagToRemove);
      tagsInput.value = currentEntry.value.tags.join(', ');
    };

    const addLink = () => {
      if (!newLink.value.url.trim()) return;

      const link = {
        url: newLink.value.url.trim(),
        title: newLink.value.title.trim() || newLink.value.url.trim()
      };

      if (!currentEntry.value.links) {
        currentEntry.value.links = [];
      }

      // Check for duplicates
      const exists = currentEntry.value.links.some(l => l.url === link.url);
      if (!exists) {
        currentEntry.value.links.push(link);
      }

      newLink.value = { url: '', title: '' };
    };

    const removeLink = (index) => {
      currentEntry.value.links.splice(index, 1);
    };

    const showSuccess = (message) => {
      // You can implement a toast notification system here
      console.log('Success:', message);
    };

    const showError = (message) => {
      // You can implement a toast notification system here
      console.error('Error:', message);
    };

    // Template functionality
    const useTemplate = (template) => {
      currentEntry.value = {
        title: '',
        content: template.contentTemplate,
        source: '',
        collection: template.category || 'default',
        tags: [template.name.toLowerCase().replace(/\s+/g, '_')],
        links: []
      };
      tagsInput.value = currentEntry.value.tags.join(', ');
      showCreateModal.value = true;
    };

    const editTemplate = (template) => {
      currentTemplate.value = {
        ...template,
        fields: template.fields.map(field =>
          typeof field === 'string'
            ? { name: field, type: 'text', placeholder: `Enter ${field}` }
            : { ...field }
        )
      };
      showEditTemplateModal.value = true;
    };

    const deleteTemplate = (templateId) => {
      if (!confirm('Are you sure you want to delete this template? This action cannot be undone.')) {
        return;
      }
      knowledgeTemplates.value = knowledgeTemplates.value.filter(t => t.id !== templateId);
      showSuccess('Template deleted successfully');
    };

    // Manage functionality
    const exportKnowledgeBase = async () => {
      exporting.value = true;
      manageMessage.value = '';

      try {
        await apiClient.downloadFile('/api/knowledge/export/download', `knowledge_base_export_${new Date().toISOString().split('T')[0]}.json`);
        manageMessage.value = 'Knowledge base exported successfully!';
        manageMessageType.value = 'success';
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
        const result = await apiClient.cleanupKnowledge();
        manageMessage.value = result.message || 'Cleanup completed successfully!';
        manageMessageType.value = 'success';
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
        stats.value = await apiClient.getKnowledgeStats();

        // Load detailed stats
        detailedStats.value = await apiClient.getDetailedKnowledgeStats();

        statsMessage.value = 'Statistics loaded successfully!';
        statsMessageType.value = 'success';
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
      loadKnowledgeEntries();
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

      // Knowledge Entries
      knowledgeEntries,
      filteredKnowledgeEntries,
      entriesSearchQuery,
      loading,
      showCreateModal,
      showEditModal,
      showViewModal,
      currentEntry,
      tagsInput,
      newLink,
      loadKnowledgeEntries,
      filterEntries,
      refreshEntries,
      getEntryTitle,
      getEntryPreview,
      formatDate,
      viewEntry,
      editEntry,
      duplicateEntry,
      deleteEntry,
      saveEntry,
      closeModals,
      updateTags,
      removeTag,
      addLink,
      removeLink,
      showSuccess,
      showError,
      isUrlEntry,
      crawlUrl,
      extractUrlFromContent,
      isUrlSource,
      crawlCurrentEntry,
      crawlingInModal,

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
      formatFileSize,

      // Templates
      knowledgeTemplates,
      showCreateTemplateModal,
      showEditTemplateModal,
      currentTemplate,
      useTemplate,
      editTemplate,
      deleteTemplate
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

/* Knowledge Entries Styles */
.entries-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.entries-header h3 {
  margin: 0;
  color: #333;
}

.create-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: #28a745;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
}

.create-btn:hover {
  background: #218838;
}

.create-btn.primary {
  background: #007bff;
  padding: 12px 24px;
  font-size: 16px;
}

.create-btn.primary:hover {
  background: #0056b3;
}

.search-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 15px;
}

.search-input {
  flex: 1;
  padding: 10px 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
}

.search-btn, .refresh-btn {
  padding: 10px 16px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
}

.search-btn {
  background: #007bff;
  color: white;
}

.search-btn:hover {
  background: #0056b3;
}

.refresh-btn {
  background: #6c757d;
  color: white;
}

.refresh-btn:hover {
  background: #545b62;
}

.entries-stats {
  margin-bottom: 15px;
  color: #666;
  font-size: 14px;
}

.entries-list {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.entry-item {
  border: 1px solid #e9ecef;
  border-radius: 8px;
  padding: 20px;
  background: white;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  transition: box-shadow 0.2s;
}

.entry-item:hover {
  box-shadow: 0 4px 8px rgba(0,0,0,0.15);
}

.entry-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 15px;
}

.entry-title {
  flex: 1;
}

.entry-title h4 {
  margin: 0 0 8px 0;
  color: #333;
  font-size: 16px;
  line-height: 1.4;
}

.entry-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.tag {
  background: #e9ecef;
  color: #495057;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 4px;
}

.tag-remove {
  background: none;
  border: none;
  color: #666;
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
}

.tag-remove:hover {
  color: #333;
}

.entry-actions {
  display: flex;
  gap: 6px;
}

.view-btn, .edit-btn, .delete-btn, .duplicate-btn {
  padding: 6px 8px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  height: 28px;
}

.view-btn {
  background: #17a2b8;
  color: white;
}

.view-btn:hover {
  background: #138496;
}

.edit-btn {
  background: #28a745;
  color: white;
}

.edit-btn:hover {
  background: #218838;
}

.duplicate-btn {
  background: #ffc107;
  color: #212529;
}

.duplicate-btn:hover {
  background: #e0a800;
}

.delete-btn {
  background: #dc3545;
  color: white;
}

.delete-btn:hover {
  background: #c82333;
}

.entry-preview {
  margin-bottom: 15px;
}

.entry-preview p {
  margin: 0;
  color: #666;
  line-height: 1.5;
  font-size: 14px;
}

.entry-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 15px;
  font-size: 12px;
  color: #666;
  border-top: 1px solid #f8f9fa;
  padding-top: 12px;
}

.entry-meta span {
  display: flex;
  align-items: center;
  gap: 4px;
}

.icon {
  font-size: 14px;
}

.icon.large {
  font-size: 48px;
  opacity: 0.5;
}

.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: #666;
}

.empty-state h4 {
  margin: 16px 0 8px;
  color: #333;
}

.empty-state p {
  margin-bottom: 24px;
  color: #666;
}

/* Modal Styles */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: white;
  border-radius: 8px;
  width: 90%;
  max-width: 800px;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid #e9ecef;
}

.modal-header h3 {
  margin: 0;
  color: #333;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #666;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.close-btn:hover {
  color: #333;
}

.modal-body {
  padding: 20px;
}

.form-group {
  margin-bottom: 20px;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  font-weight: 500;
  color: #333;
}

.form-group input,
.form-group textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
  box-sizing: border-box;
}

.form-group textarea {
  resize: vertical;
  min-height: 120px;
}

.tags-preview {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.links-section {
  border: 1px solid #e9ecef;
  border-radius: 6px;
  padding: 15px;
}

.add-link-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: #f8f9fa;
  border: 1px solid #ddd;
  border-radius: 4px;
  cursor: pointer;
  color: #333;
}

.add-link-btn:hover {
  background: #e9ecef;
}

.links-list {
  margin-top: 12px;
}

.link-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: #f8f9fa;
  border-radius: 4px;
  margin-bottom: 8px;
}

.link-url {
  flex: 1;
  color: #333;
  text-decoration: none;
}

.link-url:hover {
  text-decoration: underline;
  color: #007bff;
}

.remove-btn {
  background: #dc3545;
  color: white;
  border: none;
  border-radius: 50%;
  width: 20px;
  height: 20px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
}

.remove-btn:hover {
  background: #c82333;
}

.link-input-group {
  display: grid;
  grid-template-columns: 2fr 1fr auto;
  gap: 8px;
  margin-bottom: 12px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 30px;
  padding-top: 20px;
  border-top: 1px solid #e9ecef;
}

.cancel-btn, .save-btn {
  padding: 10px 20px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
}

.cancel-btn {
  background: #6c757d;
  color: white;
}

.cancel-btn:hover {
  background: #545b62;
}

.save-btn {
  background: #007bff;
  color: white;
}

.save-btn:hover {
  background: #0056b3;
}

/* Entry View Styles */
.entry-view {
  max-width: none;
}

.view-section {
  margin-bottom: 20px;
}

.view-section h4 {
  margin: 0 0 10px 0;
  color: #333;
  font-size: 14px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.content-display {
  background: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 6px;
  padding: 15px;
  white-space: pre-wrap;
  line-height: 1.6;
  color: #333;
}

.view-meta {
  background: #f8f9fa;
  border-radius: 6px;
  padding: 15px;
  margin-bottom: 20px;
}

.meta-item {
  margin-bottom: 10px;
  color: #333;
}

.meta-item:last-child {
  margin-bottom: 0;
}

.meta-item strong {
  color: #333;
  margin-right: 8px;
}

.tags-display {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.links-display {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.link-display {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #f8f9fa;
  border-radius: 4px;
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
    grid-template-columns: 1fr;
  }

  .link-input-group {
    grid-template-columns: 1fr;
  }

  .entry-actions {
    flex-wrap: wrap;
  }

  .entry-meta {
    flex-direction: column;
    gap: 8px;
  }

  .modal {
    width: 95%;
    margin: 20px;
  }
}
</style>
