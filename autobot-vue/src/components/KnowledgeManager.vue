<template>
  <ErrorBoundary fallback="Knowledge Base failed to load. Please try refreshing.">
    <div class="knowledge-manager">

    <div class="tabs">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        :class="['tab-button', { active: activeTab === tab.id }]"
        @click="activeTab = tab.id"
       aria-label="{{ tab.label }}">
        {{ tab.label }}
      </button>
    </div>

    <!-- Search Tab -->
    <div v-if="activeTab === 'search'" class="tab-content">
      <div class="search-header">
        <h3>Search Knowledge Base</h3>
        <button
          @click="toggleAdvancedSearch"
          class="toggle-advanced-btn"
          :class="{ 'active': showAdvancedSearch }"
        >
          {{ showAdvancedSearch ? 'Simple Search' : 'Advanced Search' }}
        </button>
      </div>

      <div class="search-form">
        <!-- Main search input with enhanced UX -->
        <div class="search-input-container">
          <div class="search-input-wrapper">
            <input
              v-model="searchQuery"
              type="text"
              placeholder="Search knowledge base... (try keywords, questions, or topics)"
              @keyup.enter="performSearch"
              @input="onSearchInput"
              @focus="showSearchHelp = true"
              @blur="hideSearchHelp"
              class="main-search-input enhanced"
              id="knowledge-search-input"
              autocomplete="off"
              spellcheck="false"
            />
            <div class="search-input-icons">
              <i v-if="searching" class="fas fa-spinner fa-spin search-spinner"></i>
              <i v-else-if="searchQuery" @click="clearSearch" class="fas fa-times clear-search" title="Clear search"></i>
              <i v-else class="fas fa-search search-icon"></i>
            </div>
          </div>
          <button
            @click="performSearch"
            :disabled="searching || !searchQuery.trim()"
            class="search-btn enhanced"
            :class="{ 'searching': searching }"
          >
            {{ searching ? 'Searching...' : 'Search' }}
          </button>
        </div>

        <!-- Search help tooltip -->
        <div v-if="showSearchHelp && !searchQuery" class="search-help-tooltip">
          <div class="help-item">
            <strong>💡 Search Tips:</strong>
          </div>
          <div class="help-item">• Use quotes for exact phrases: "machine learning"</div>
          <div class="help-item">• Use wildcards: config* or *setup</div>
          <div class="help-item">• Try natural questions: "How to configure Redis?"</div>
        </div>

        <!-- Enhanced search suggestions with categories -->
        <div v-if="showSuggestions && searchSuggestions.length > 0" class="search-suggestions enhanced">
          <div class="suggestions-header">
            <i class="fas fa-lightbulb"></i>
            <span>Suggested searches</span>
          </div>
          <div class="suggestions-list">
            <div
              v-for="(suggestion, index) in searchSuggestions"
              :key="suggestion"
              @click="applySuggestion(suggestion)"
              @keyup.enter="applySuggestion(suggestion)"
              class="suggestion-item enhanced"
              :class="{ 'highlighted': index === selectedSuggestionIndex }"
              tabindex="0"
            >
              <i class="fas fa-search suggestion-icon"></i>
              <span class="suggestion-text">{{ suggestion }}</span>
              <span class="suggestion-count" v-if="suggestionCounts[suggestion]">
                {{ suggestionCounts[suggestion] }} results
              </span>
            </div>
          </div>
        </div>

        <!-- Advanced search filters -->
        <div v-if="showAdvancedSearch" class="advanced-search">
          <div class="filter-row">
            <div class="filter-group">
              <label>Content Type:</label>
              <select v-model="searchFilters.contentType">
                <option value="">All Types</option>
                <option value="text">Text</option>
                <option value="document">Document</option>
                <option value="code">Code</option>
                <option value="note">Note</option>
              </select>
            </div>

            <div class="filter-group">
              <label>Collection:</label>
              <select v-model="searchFilters.collection">
                <option value="">All Collections</option>
                <option v-for="collection in availableCollections" :key="collection" :value="collection">
                  {{ collection }}
                </option>
              </select>
            </div>

            <div class="filter-group">
              <label>Date Range:</label>
              <select v-model="searchFilters.dateRange">
                <option value="">Any Time</option>
                <option value="today">Today</option>
                <option value="week">This Week</option>
                <option value="month">This Month</option>
                <option value="year">This Year</option>
              </select>
            </div>
          </div>

          <div class="filter-row">
            <div class="filter-group">
              <label>Min Score:</label>
              <input
                v-model.number="searchFilters.minScore"
                type="range"
                min="0"
                max="1"
                step="0.1"
                class="score-slider"
              />
              <span class="score-value">{{ searchFilters.minScore.toFixed(1) }}</span>
            </div>

            <div class="filter-group">
              <label>Tags:</label>
              <input
                v-model="searchFilters.tags"
                type="text"
                placeholder="Enter tags (comma separated)"
                class="tags-input"
              />
            </div>
          </div>

          <div class="search-options">
            <label class="checkbox-option">
              <input v-model="searchFilters.exactMatch" type="checkbox" />
              Exact phrase matching
            </label>
            <label class="checkbox-option">
              <input v-model="searchFilters.includeMetadata" type="checkbox" />
              Search in metadata
            </label>
            <label class="checkbox-option">
              <input v-model="searchFilters.caseSensitive" type="checkbox" />
              Case sensitive
            </label>
          </div>
        </div>
      </div>

      <!-- Search results header with sorting -->
      <div v-if="searchResults.length > 0" class="results-header">
        <div class="results-info">
          <h4>Search Results ({{ filteredResults.length }} of {{ searchResults.length }})</h4>
          <span class="search-time" v-if="searchTime">Found in {{ searchTime }}ms</span>
        </div>
        <div class="results-controls">
          <div class="sort-controls">
            <label>Sort by:</label>
            <select v-model="sortBy" @change="sortResults">
              <option value="score">Relevance Score</option>
              <option value="date">Date Modified</option>
              <option value="title">Title</option>
              <option value="type">Content Type</option>
            </select>
            <button @click="toggleSortOrder" class="sort-order-btn enhanced">
              <i class="fas" :class="sortOrder === 'desc' ? 'fa-sort-amount-down' : 'fa-sort-amount-up'"></i>
              {{ sortOrder === 'desc' ? 'Desc' : 'Asc' }}
            </button>
          </div>
          <div class="view-controls enhanced">
            <button
              @click="resultsViewMode = 'list'"
              :class="{ active: resultsViewMode === 'list' }"
              class="view-mode-btn"
              title="List view"
            >
              <i class="fas fa-list"></i>
            </button>
            <button
              @click="resultsViewMode = 'cards'"
              :class="{ active: resultsViewMode === 'cards' }"
              class="view-mode-btn"
              title="Card view"
            >
              <i class="fas fa-th-large"></i>
            </button>
          </div>
          <div class="action-controls">
            <button
              @click="exportResults"
              class="export-btn"
              :disabled="!searchResults.length"
              title="Export search results"
            >
              <i class="fas fa-download"></i>
            </button>
          </div>
        </div>
      </div>

      <!-- No results state with suggestions -->
      <div v-if="searchPerformed && filteredResults.length === 0" class="no-results">
        <div class="no-results-icon">
          <i class="fas fa-search"></i>
        </div>
        <h3>No results found</h3>
        <p v-if="searchQuery">We couldn't find anything matching "{{ searchQuery }}"</p>
        <div class="no-results-suggestions">
          <h4>Try:</h4>
          <ul>
            <li>• Checking your spelling</li>
            <li>• Using different keywords</li>
            <li>• Making your search less specific</li>
            <li>• Using the advanced search filters</li>
          </ul>
        </div>
        <div class="no-results-actions">
          <button @click="clearSearch" class="btn-secondary">
            <i class="fas fa-times"></i> Clear Search
          </button>
          <button @click="showAdvancedSearch = true" class="btn-primary">
            <i class="fas fa-sliders-h"></i> Advanced Search
          </button>
        </div>
      </div>

      <!-- Enhanced search results with improved UX -->
      <div v-if="filteredResults.length > 0" class="search-results enhanced" :class="resultsViewMode">
        <div
          v-for="(result, index) in paginatedResults"
          :key="result.id || `result-${index}`"
          class="search-result enhanced"
          :class="{
            'high-score': result.score > 0.8,
            'medium-score': result.score > 0.5 && result.score <= 0.8,
            'low-score': result.score <= 0.5
          }"
          @click="selectResult(result)"
          :tabindex="0"
          @keyup.enter="selectResult(result)"
        >
          <div class="result-header enhanced">
            <div class="result-title">
              <h5 v-html="highlightText(getResultTitle(result), searchQuery)" class="title-text"></h5>
              <div class="result-badges">
                <span class="badge score" :class="getScoreClass(result.score)" :title="`Relevance score: ${result.score?.toFixed(3)}`">
                  <i class="fas fa-star"></i>
                  {{ result.score?.toFixed(2) || '0.00' }}
                </span>
                <span v-if="result.type" class="badge type" :title="`Content type: ${result.type}`">
                  <i class="fas" :class="getTypeIcon(result.type)"></i>
                  {{ result.type }}
                </span>
                <span v-if="result.collection" class="badge collection" :title="`Collection: ${result.collection}`">
                  <i class="fas fa-folder"></i>
                  {{ result.collection }}
                </span>
              </div>
            </div>
            <div class="result-actions enhanced">
              <button
                @click.stop="viewResult(result)"
                class="action-btn view-btn"
                title="View full content"
                :aria-label="`View full content of ${getResultTitle(result)}`"
              >
                <i class="fas fa-eye"></i>
              </button>
              <button
                @click.stop="useResult(result)"
                class="action-btn use-btn"
                title="Use in chat"
                :aria-label="`Use ${getResultTitle(result)} in chat conversation`"
              >
                <i class="fas fa-comments"></i>
              </button>
              <button
                @click.stop="copyResult(result)"
                class="action-btn copy-btn"
                title="Copy to clipboard"
                :aria-label="`Copy ${getResultTitle(result)} to clipboard`"
              >
                <i class="fas fa-copy"></i>
              </button>
              <button
                @click.stop="bookmarkResult(result)"
                class="action-btn bookmark-btn"
                :class="{ 'bookmarked': isBookmarked(result) }"
                :title="isBookmarked(result) ? 'Remove bookmark' : 'Add bookmark'"
                :aria-label="`${isBookmarked(result) ? 'Remove' : 'Add'} bookmark for ${getResultTitle(result)}`"
              >
                <i class="fas" :class="isBookmarked(result) ? 'fa-bookmark' : 'fa-bookmark-o'"></i>
              </button>
            </div>
          </div>

          <div class="result-content">
            <p v-html="highlightText(getResultPreview(result), searchQuery)"></p>
          </div>

          <div class="result-metadata" v-if="result.metadata || result.tags">
            <div v-if="result.tags && result.tags.length > 0" class="result-tags">
              <span class="icon">🏷️</span>
              <span v-for="tag in result.tags.slice(0, 3)" :key="tag" class="tag">{{ tag }}</span>
              <span v-if="result.tags.length > 3" class="more-tags">+{{ result.tags.length - 3 }}</span>
            </div>

            <div v-if="result.metadata" class="metadata-items">
              <span v-if="result.metadata.source" class="metadata-item">
                <span class="icon">📄</span> {{ result.metadata.source }}
              </span>
              <span v-if="result.metadata.created" class="metadata-item">
                <span class="icon">📅</span> {{ formatDate(result.metadata.created) }}
              </span>
              <span v-if="result.content" class="metadata-item">
                <span class="icon">📏</span> {{ formatContentSize(result.content.length) }}
              </span>
            </div>
          </div>
        </div>

        <!-- Pagination -->
        <div v-if="totalPages > 1" class="pagination">
          <button
            @click="currentPage = 1"
            :disabled="currentPage === 1"
            class="page-btn"
          >
            First
          </button>
          <button
            @click="currentPage--"
            :disabled="currentPage === 1"
            class="page-btn"
          >
            Prev
          </button>

          <span class="page-info">
            Page {{ currentPage }} of {{ totalPages }}
          </span>

          <button
            @click="currentPage++"
            :disabled="currentPage === totalPages"
            class="page-btn"
          >
            Next
          </button>
          <button
            @click="currentPage = totalPages"
            :disabled="currentPage === totalPages"
            class="page-btn"
          >
            Last
          </button>
        </div>
      </div>

      <div v-else-if="searchPerformed && !searching" class="no-results">
        <div class="empty-state">
          <span class="icon large">🔍</span>
          <h4>No results found</h4>
          <p>No matches found for "<strong>{{ lastSearchQuery }}</strong>"</p>
          <div class="suggestions">
            <h5>Try:</h5>
            <ul>
              <li>Using different keywords</li>
              <li>Checking your spelling</li>
              <li>Using fewer or more general terms</li>
              <li v-if="showAdvancedSearch">Adjusting your filters</li>
            </ul>
          </div>
        </div>
      </div>

      <!-- Quick search tips -->
      <div v-if="!searchPerformed" class="search-tips">
        <h4>Search Tips</h4>
        <div class="tips-grid">
          <div class="tip-item">
            <span class="tip-icon">🔍</span>
            <strong>Basic Search:</strong> Type keywords to find relevant content
          </div>
          <div class="tip-item">
            <span class="tip-icon">🎯</span>
            <strong>Exact Match:</strong> Use quotes for exact phrases "like this"
          </div>
          <div class="tip-item">
            <span class="tip-icon">🏷️</span>
            <strong>Tags:</strong> Search by tags using #tag syntax
          </div>
          <div class="tip-item">
            <span class="tip-icon">⚙️</span>
            <strong>Advanced:</strong> Use advanced search for precise filtering
          </div>
        </div>
      </div>
    </div>

    <!-- Categories Tab -->
    <div v-if="activeTab === 'categories'" class="tab-content">
      <div class="categories-header">
        <h3>Knowledge Categories</h3>
        <button @click="refreshCategories" class="refresh-btn" aria-label="Refresh">Refresh</button>
      </div>

      <div v-if="loadingCategories" class="loading-message">
        Loading categories...
      </div>

      <div v-else-if="categories.length > 0" class="categories-grid">
        <div v-for="category in categories" :key="category.name" class="category-card">
          <div class="category-icon">{{ category.icon || '📁' }}</div>
          <h4>{{ category.name }}</h4>
          <p class="category-description">{{ category.description || 'No description available' }}</p>
          <div class="category-stats">
            <span class="stat-item">
              <span class="icon">📊</span> {{ category.count || 0 }} entries
            </span>
            <span class="stat-item" v-if="category.last_updated">
              <span class="icon">📅</span> {{ formatDate(category.last_updated) }}
            </span>
          </div>
          <div class="category-actions">
            <button @click="browseCategory(category.name)" class="browse-btn" aria-label="Browse">Browse</button>
            <button @click="editCategory(category)" class="edit-btn" aria-label="Edit">Edit</button>
          </div>
        </div>
      </div>

      <div v-else class="no-categories">
        <div class="empty-state">
          <span class="icon large">📂</span>
          <h4>No categories found</h4>
          <p>Categories will appear here as you add knowledge entries with different collections.</p>
        </div>
      </div>
    </div>

    <!-- System Knowledge Tab -->
    <div v-if="activeTab === 'system'" class="tab-content">
      <div class="system-knowledge-header">
        <h3>System Knowledge & Documentation</h3>
        <div class="header-actions">
          <button @click="refreshSystemKnowledge" class="refresh-btn" aria-label="Refresh">Refresh</button>
          <button @click="importSystemDocs" class="import-btn" :disabled="importingDocs" aria-label="{{ importingdocs ? 'importing...' : 'import documentation' }}">
            {{ importingDocs ? 'Importing...' : 'Import Documentation' }}
          </button>
        </div>
      </div>

      <div v-if="loadingSystemKnowledge" class="loading-message">
        Loading system knowledge...
      </div>

      <div v-else-if="systemKnowledge.length > 0" class="system-knowledge-list">
        <div v-for="doc in systemKnowledge" :key="doc.id" class="system-doc-item">
          <div class="doc-header">
            <div class="doc-title">
              <span class="doc-type-icon">{{ getDocTypeIcon(doc.type) }}</span>
              <h4>{{ doc.title || doc.name }}</h4>
              <div class="doc-badges">
                <span class="badge doc-type">{{ doc.type || 'documentation' }}</span>
                <span class="badge doc-status" :class="doc.status">{{ doc.status || 'active' }}</span>
              </div>
            </div>
            <div class="doc-actions">
              <button @click="viewSystemDoc(doc)" class="view-btn" title="View">👁</button>
              <button @click="editSystemDoc(doc)" class="edit-btn" title="Edit" :disabled="doc.immutable">✏️</button>
              <button @click="exportSystemDoc(doc)" class="export-btn" title="Export">💾</button>
            </div>
          </div>

          <div class="doc-preview">
            <p>{{ getDocPreview(doc) }}</p>
          </div>

          <div class="doc-meta">
            <span class="doc-source" v-if="doc.source">
              <span class="icon">📄</span> {{ doc.source }}
            </span>
            <span class="doc-version" v-if="doc.version">
              <span class="icon">🏷️</span> v{{ doc.version }}
            </span>
            <span class="doc-updated" v-if="doc.updated_at">
              <span class="icon">📅</span> {{ formatDate(doc.updated_at) }}
            </span>
            <span class="doc-size" v-if="doc.content">
              <span class="icon">📏</span> {{ formatContentSize(doc.content.length) }}
            </span>
          </div>
        </div>
      </div>

      <div v-else class="no-system-knowledge">
        <div class="empty-state">
          <span class="icon large">📚</span>
          <h4>No system documentation found</h4>
          <p>System documentation will appear here after import or creation.</p>
          <button @click="importSystemDocs" class="import-btn primary" :disabled="importingDocs" aria-label="{{ importingdocs ? 'importing...' : 'import system documentation' }}">
            {{ importingDocs ? 'Importing...' : 'Import System Documentation' }}
          </button>
        </div>
      </div>
    </div>

    <!-- System Prompts Tab -->
    <div v-if="activeTab === 'prompts'" class="tab-content">
      <div class="system-prompts-header">
        <h3>System Prompts & Templates</h3>
        <div class="header-actions">
          <button @click="refreshSystemPrompts" class="refresh-btn" aria-label="Refresh">Refresh</button>
          <button @click="createSystemPrompt" class="create-btn" aria-label="+ create prompt">+ Create Prompt</button>
          <button @click="importSystemPrompts" class="import-btn" :disabled="importingPrompts" aria-label="{{ importingprompts ? 'importing...' : 'import prompts' }}">
            {{ importingPrompts ? 'Importing...' : 'Import Prompts' }}
          </button>
        </div>
      </div>

      <div v-if="loadingSystemPrompts" class="loading-message">
        Loading system prompts...
      </div>

      <div v-else-if="systemPrompts.length > 0" class="system-prompts-grid">
        <div v-for="prompt in systemPrompts" :key="prompt.id" class="prompt-card">
          <div class="prompt-header">
            <div class="prompt-title">
              <span class="prompt-icon">{{ getPromptIcon(prompt.category) }}</span>
              <h4>{{ prompt.name || prompt.title }}</h4>
            </div>
            <div class="prompt-actions">
              <button @click="useSystemPrompt(prompt)" class="use-btn" title="Use Prompt">🎯</button>
              <button @click="viewSystemPrompt(prompt)" class="view-btn" title="View">👁</button>
              <button @click="editSystemPrompt(prompt)" class="edit-btn" title="Edit" :disabled="prompt.immutable">✏️</button>
              <button @click="duplicateSystemPrompt(prompt)" class="duplicate-btn" title="Duplicate">📋</button>
            </div>
          </div>

          <div class="prompt-description">
            <p>{{ prompt.description || 'No description available' }}</p>
          </div>

          <div class="prompt-preview">
            <code>{{ getPromptPreview(prompt.template || prompt.content) }}</code>
          </div>

          <div class="prompt-meta">
            <div class="prompt-tags" v-if="prompt.tags && prompt.tags.length > 0">
              <span v-for="tag in prompt.tags.slice(0, 3)" :key="tag" class="tag">{{ tag }}</span>
              <span v-if="prompt.tags.length > 3" class="more-tags">+{{ prompt.tags.length - 3 }} more</span>
            </div>
            <div class="prompt-info">
              <span class="prompt-category" v-if="prompt.category">
                <span class="icon">🏷️</span> {{ prompt.category }}
              </span>
              <span class="prompt-version" v-if="prompt.version">
                <span class="icon">📦</span> v{{ prompt.version }}
              </span>
              <span class="prompt-usage" v-if="prompt.usage_count !== undefined">
                <span class="icon">📊</span> {{ prompt.usage_count }} uses
              </span>
            </div>
          </div>
        </div>
      </div>

      <div v-else class="no-system-prompts">
        <div class="empty-state">
          <span class="icon large">🎯</span>
          <h4>No system prompts found</h4>
          <p>System prompts and templates will appear here after import or creation.</p>
          <button @click="importSystemPrompts" class="import-btn primary" :disabled="importingPrompts" aria-label="{{ importingprompts ? 'importing...' : 'import system prompts' }}">
            {{ importingPrompts ? 'Importing...' : 'Import System Prompts' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Templates Tab -->
    <div v-if="activeTab === 'templates'" class="tab-content">
      <div class="templates-header">
        <h3>Knowledge Entry Templates</h3>
        <button @click="showCreateTemplateModal = true" class="create-btn" aria-label="Button">
          <span class="icon">📝</span> Create Template
        </button>
      </div>

      <div class="templates-grid">
        <div v-for="template in knowledgeTemplates" :key="template.id" class="template-card" @click="useTemplate(template)" tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
          <div class="template-icon">{{ template.icon }}</div>
          <h4>{{ template.name }}</h4>
          <p>{{ template.description }}</p>
          <div class="template-fields">
            <span v-for="field in template.fields.slice(0, 3)" :key="field" class="field-tag">{{ typeof field === 'string' ? field : field.name }}</span>
            <span v-if="template.fields.length > 3" class="more-fields">+{{ template.fields.length - 3 }} more</span>
          </div>
          <div class="template-actions" @click.stop tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
            <button @click="editTemplate(template)" class="edit-template-btn" title="Edit Template">✏️</button>
            <button @click="deleteTemplate(template.id)" class="delete-template-btn" title="Delete Template">🗑️</button>
          </div>
        </div>

        <!-- Add custom template card -->
        <div class="template-card add-template" @click="showCreateTemplateModal = true" tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
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
        <button @click="showCreateModal = true" class="create-btn" aria-label="Button">
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
          <button @click="filterEntries" class="search-btn" aria-label="Search">Search</button>
          <button @click="refreshEntries" class="refresh-btn" aria-label="Refresh">Refresh</button>
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
            <button @click="showCreateModal = true" class="create-btn primary" aria-label="Add your first entry">
              Add Your First Entry
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Entry Modal (Create/Edit/View) -->
    <div v-if="showCreateModal || showEditModal || showViewModal" class="modal-overlay" @click="closeModals" tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
      <div class="modal" @click.stop tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
        <div class="modal-header">
          <h3 v-if="showCreateModal">Create New Entry</h3>
          <h3 v-else-if="showEditModal">Edit Entry</h3>
          <h3 v-else>View Entry</h3>
          <button @click="closeModals" class="close-btn" aria-label="&times;">&times;</button>
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
                <div class="source-input-group">
                  <input
                    type="text"
                    id="entry-source"
                    v-model="currentEntry.source"
                    placeholder="Document name, URL, or source reference"
                  />
                  <button type="button" @click="showFileSelector = true" class="file-select-btn" title="Select from files">
                    📁
                  </button>
                  <label class="file-upload-btn" title="Upload new file">
                    📤
                    <input type="file" @change="handleFileUpload" style="display: none;" />
                  </label>
                </div>
                <small v-if="isUrlSource(currentEntry.source)" class="url-hint">
                  🕷️ URL detected - you can leave content empty to auto-crawl
                </small>
                <small v-if="selectedFile" class="file-hint">
                  📄 Selected file: {{ selectedFile.name }}
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
                  <button type="button" @click="removeTag(tag)" class="tag-remove" aria-label="&times;">&times;</button>
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
                  <button type="button" @click="addLink" class="add-link-btn" aria-label="Button">
                    <span class="icon">🔗</span> Add
                  </button>
                </div>

                <div class="links-list" v-if="currentEntry.links && currentEntry.links.length > 0">
                  <div v-for="(link, index) in currentEntry.links" :key="link.url || link.href || `link-${index}`" class="link-item">
                    <a :href="link.url" target="_blank" class="link-url">
                      {{ link.title || link.url }}
                    </a>
                    <button type="button" @click="removeLink(index)" class="remove-btn" aria-label="&times;">&times;</button>
                  </div>
                </div>
              </div>
            </div>

            <div class="modal-actions">
              <button type="button" @click="closeModals" class="cancel-btn" aria-label="Cancel">Cancel</button>
              <button
                v-if="showEditModal && isUrlSource(currentEntry.source)"
                type="button"
                @click="crawlCurrentEntry"
                class="crawl-btn-modal"
                :disabled="crawlingInModal"
               aria-label="Button">
                <span v-if="crawlingInModal">🔄 Crawling...</span>
                <span v-else>🕷️ Re-crawl URL</span>
              </button>
              <button type="submit" class="save-btn" aria-label="{{ showcreatemodal ? 'create entry' : 'save changes' }}">
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
              <button @click="editEntry(currentEntry)" class="edit-btn" aria-label="Edit entry">Edit Entry</button>
              <button @click="closeModals" class="close-btn" aria-label="Close">Close</button>
            </div>
          </div>
        </div>
      </div>
    </div>


    <!-- Manage Tab -->
    <div v-if="activeTab === 'manage'" class="tab-content">
      <h3>Manage Knowledge Base</h3>

      <div class="manage-actions">
        <button @click="exportKnowledgeBase" :disabled="exporting" aria-label="{{ exporting ? 'exporting...' : 'export knowledge base' }}">
          {{ exporting ? 'Exporting...' : 'Export Knowledge Base' }}
        </button>
        <button @click="cleanupKnowledgeBase" :disabled="cleaning" class="warning" aria-label="{{ cleaning ? 'cleaning...' : 'cleanup old entries' }}">
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

      <button @click="loadStats" :disabled="loadingStats" class="refresh-button" aria-label="{{ loadingstats ? 'loading...' : 'refresh statistics' }}">
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
    <!-- File Selector Modal -->
    <div v-if="showFileSelector" class="modal-overlay" @click="showFileSelector = false" tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
      <div class="modal file-selector-modal" @click.stop tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
        <div class="modal-header">
          <h3>Select File</h3>
          <button @click="showFileSelector = false" class="close-btn" aria-label="&times;">&times;</button>
        </div>
        <div class="modal-body">
          <div class="file-list-container">
            <div v-if="availableFiles.length === 0" class="loading-files">
              Loading files...
            </div>
            <div v-else class="file-list">
              <div
                v-for="file in availableFiles"
                :key="file.name"
                class="file-item"
                @click="selectFileForKnowledge(file)"
               tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
                <span class="file-icon">{{ getFileIcon(file) }}</span>
                <span class="file-name">{{ file.name }}</span>
                <span class="file-size">{{ formatFileSize(file.size) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    </div>
  </ErrorBoundary>
</template>

<script>
import { ref, onMounted, watch, computed } from 'vue';
import apiClient from '../utils/ApiClient.js';
import ErrorBoundary from './ErrorBoundary.vue';

export default {
  name: 'KnowledgeManager',
  components: {
    ErrorBoundary
  },
  setup() {
    // Tab management
    const activeTab = ref('search');
    const tabs = [
      { id: 'search', label: 'Search' },
      { id: 'categories', label: 'Categories' },
      { id: 'entries', label: 'Knowledge Entries' },
      { id: 'system', label: 'System Knowledge' },
      { id: 'prompts', label: 'System Prompts' },
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

    // File integration
    const showFileSelector = ref(false);
    const selectedFile = ref(null);
    const availableFiles = ref([]);

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

    // Enhanced Search functionality
    const showAdvancedSearch = ref(false);
    const showSuggestions = ref(false);
    const searchSuggestions = ref([]);
    const searchTime = ref(null);

    // Search filters
    const searchFilters = ref({
      contentType: '',
      collection: '',
      dateRange: '',
      minScore: 0.0,
      tags: '',
      exactMatch: false,
      includeMetadata: true,
      caseSensitive: false
    });

    // Results management
    const sortBy = ref('score');
    const sortOrder = ref('desc');
    const resultsViewMode = ref('list');
    const currentPage = ref(1);
    const resultsPerPage = ref(10);
    const filteredResults = ref([]);
    const availableCollections = ref(['default', 'docs', 'code', 'notes']);

    // Computed properties for pagination
    const totalPages = computed(() => Math.ceil(filteredResults.value.length / resultsPerPage.value));
    const paginatedResults = computed(() => {
      const start = (currentPage.value - 1) * resultsPerPage.value;
      const end = start + resultsPerPage.value;
      return filteredResults.value.slice(start, end);
    });

    // Search suggestions based on previous searches
    const commonSearchTerms = ref([
      'configuration', 'setup', 'API', 'documentation', 'troubleshooting',
      'installation', 'deployment', 'security', 'authentication', 'database'
    ]);

    const toggleAdvancedSearch = () => {
      showAdvancedSearch.value = !showAdvancedSearch.value;
    };

    const onSearchInput = debounce(() => {
      const query = searchQuery.value.toLowerCase().trim();
      if (query.length > 2) {
        searchSuggestions.value = commonSearchTerms.value
          .filter(term => term.toLowerCase().includes(query))
          .slice(0, 5);
        showSuggestions.value = searchSuggestions.value.length > 0;
      } else {
        showSuggestions.value = false;
      }
    }, 300);

    // Search help state
    const showSearchHelp = ref(false);
    const suggestionCounts = ref({});
    const selectedSuggestionIndex = ref(-1);

    const hideSearchHelp = () => {
      setTimeout(() => {
        showSearchHelp.value = false;
      }, 200);
    };

    const clearSearch = () => {
      searchQuery.value = '';
      searchResults.value = [];
      filteredResults.value = [];
      searchPerformed.value = false;
      showSuggestions.value = false;
      showSearchHelp.value = false;
    };

    const selectResult = (result) => {
      // Emit or handle result selection
      console.log('Selected result:', result);
    };

    const getTypeIcon = (type) => {
      const icons = {
        text: 'fa-file-text',
        document: 'fa-file-alt',
        code: 'fa-code',
        note: 'fa-sticky-note',
        url: 'fa-link',
        image: 'fa-image',
        video: 'fa-video',
        audio: 'fa-music'
      };
      return icons[type] || 'fa-file';
    };

    const formatDate = (timestamp) => {
      if (!timestamp) return 'Unknown';
      try {
        const date = new Date(timestamp);
        return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
      } catch {
        return 'Invalid date';
      }
    };

    const formatContentSize = (size) => {
      if (size < 1000) return `${size} chars`;
      if (size < 1000000) return `${(size / 1000).toFixed(1)}K chars`;
      return `${(size / 1000000).toFixed(1)}M chars`;
    };

    // Bookmarking functionality
    const bookmarkedResults = ref(new Set());

    const isBookmarked = (result) => {
      return bookmarkedResults.value.has(result.id);
    };

    const bookmarkResult = (result) => {
      if (isBookmarked(result)) {
        bookmarkedResults.value.delete(result.id);
      } else {
        bookmarkedResults.value.add(result.id);
      }
    };

    // Export functionality
    const exportResults = () => {
      if (!searchResults.value.length) return;

      const exportData = {
        query: lastSearchQuery.value,
        timestamp: new Date().toISOString(),
        total_results: searchResults.value.length,
        filtered_results: filteredResults.value.length,
        results: filteredResults.value
      };

      const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `search_results_${Date.now()}.json`;
      link.click();
      URL.revokeObjectURL(url);
    };

    const applySuggestion = (suggestion) => {
      searchQuery.value = suggestion;
      showSuggestions.value = false;
      performSearch();
    };

    // Text highlighting function
    const highlightText = (text, query) => {
      if (!text || !query) return text;

      const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
      return text.replace(regex, '<mark>$1</mark>');
    };

    // Result helper functions
    const getResultTitle = (result) => {
      return result.title || result.metadata?.title || 'Untitled';
    };

    const getResultPreview = (result) => {
      const content = result.content || result.text || 'No content available';
      return content.length > 200 ? content.substring(0, 200) + '...' : content;
    };

    const getScoreClass = (score) => {
      if (score >= 0.8) return 'high';
      if (score >= 0.6) return 'medium';
      return 'low';
    };

    // Result actions
    const viewResult = (result) => {
      // Open result in modal or new tab
      // Viewing result
      // TODO: Implement result viewer
    };

    const useResult = (result) => {
      // Add result to chat context or use in current conversation
      // Using result in chat
      // TODO: Implement chat integration
    };

    const copyResult = async (result) => {
      try {
        await navigator.clipboard.writeText(result.content || result.text || '');
        // TODO: Show toast notification
        // Content copied to clipboard
      } catch (error) {
        console.error('Failed to copy content:', error);
      }
    };

    // Sorting functions
    const sortResults = () => {
      filteredResults.value.sort((a, b) => {
        let aVal, bVal;

        switch (sortBy.value) {
          case 'score':
            aVal = a.score || 0;
            bVal = b.score || 0;
            break;
          case 'date':
            aVal = new Date(a.metadata?.created || a.created || 0);
            bVal = new Date(b.metadata?.created || b.created || 0);
            break;
          case 'title':
            aVal = getResultTitle(a).toLowerCase();
            bVal = getResultTitle(b).toLowerCase();
            break;
          case 'type':
            aVal = a.type || 'unknown';
            bVal = b.type || 'unknown';
            break;
          default:
            return 0;
        }

        if (sortOrder.value === 'desc') {
          return aVal > bVal ? -1 : aVal < bVal ? 1 : 0;
        } else {
          return aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
        }
      });
    };

    const toggleSortOrder = () => {
      sortOrder.value = sortOrder.value === 'desc' ? 'asc' : 'desc';
      sortResults();
    };

    // Filter results based on advanced search criteria
    const filterResults = () => {
      let results = [...searchResults.value];

      // Apply filters
      if (searchFilters.value.minScore > 0) {
        results = results.filter(r => (r.score || 0) >= searchFilters.value.minScore);
      }

      if (searchFilters.value.contentType) {
        results = results.filter(r => r.type === searchFilters.value.contentType);
      }

      if (searchFilters.value.collection) {
        results = results.filter(r => r.collection === searchFilters.value.collection);
      }

      if (searchFilters.value.tags) {
        const tags = searchFilters.value.tags.split(',').map(t => t.trim().toLowerCase());
        results = results.filter(r =>
          r.tags && r.tags.some(tag =>
            tags.some(filterTag => tag.toLowerCase().includes(filterTag))
          )
        );
      }

      // Apply date range filter
      if (searchFilters.value.dateRange) {
        const now = new Date();
        let cutoffDate;

        switch (searchFilters.value.dateRange) {
          case 'today':
            cutoffDate = new Date(now.getFullYear(), now.getMonth(), now.getDate());
            break;
          case 'week':
            cutoffDate = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
            break;
          case 'month':
            cutoffDate = new Date(now.getFullYear(), now.getMonth() - 1, now.getDate());
            break;
          case 'year':
            cutoffDate = new Date(now.getFullYear() - 1, now.getMonth(), now.getDate());
            break;
        }

        if (cutoffDate) {
          results = results.filter(r => {
            const resultDate = new Date(r.metadata?.created || r.created || 0);
            return resultDate >= cutoffDate;
          });
        }
      }

      filteredResults.value = results;
      currentPage.value = 1; // Reset to first page
      sortResults();
    };

    // Enhanced search function
    const performSearch = async () => {
      if (!searchQuery.value.trim()) return;

      const startTime = performance.now();
      searching.value = true;
      searchPerformed.value = true;
      lastSearchQuery.value = searchQuery.value;
      showSuggestions.value = false;

      try {
        // Build search parameters
        const searchParams = {
          query: searchQuery.value,
          limit: 50, // Get more results for filtering
          include_metadata: searchFilters.value.includeMetadata
        };

        // Add advanced search options
        if (searchFilters.value.exactMatch) {
          searchParams.exact_match = true;
        }

        if (searchFilters.value.caseSensitive) {
          searchParams.case_sensitive = true;
        }

        const data = await apiClient.searchKnowledge(searchParams.query, searchParams);
        searchResults.value = data.results || [];

        // Record search time
        searchTime.value = Math.round(performance.now() - startTime);

        // Apply filters and sorting
        filterResults();

        // Update search suggestions based on successful search
        if (searchResults.value.length > 0) {
          const queryWords = searchQuery.value.toLowerCase().split(' ');
          queryWords.forEach(word => {
            if (word.length > 3 && !commonSearchTerms.value.includes(word)) {
              commonSearchTerms.value.push(word);
            }
          });
        }

      } catch (error) {
        console.error('Search error:', error);
        searchResults.value = [];
        filteredResults.value = [];
        searchTime.value = null;
      } finally {
        searching.value = false;
      }
    };

    // Watch for filter changes
    watch(searchFilters, () => {
      if (searchResults.value.length > 0) {
        filterResults();
      }
    }, { deep: true });

    // Debounce function for search suggestions
    function debounce(func, wait) {
      let timeout;
      return function executedFunction(...args) {
        const later = () => {
          clearTimeout(timeout);
          func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
      };
    }

    // Add content functionality

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
        // Try to use search endpoint as fallback
        try {
          const searchResponse = await apiClient.searchKnowledge('', 100);
          knowledgeEntries.value = searchResponse.results || [];
          filteredKnowledgeEntries.value = knowledgeEntries.value;
        } catch (fallbackError) {
          console.error('Fallback search also failed:', fallbackError);
          knowledgeEntries.value = [];
          filteredKnowledgeEntries.value = [];
        }
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

    // File integration functions
    const loadAvailableFiles = async () => {
      try {
        const response = await fetch(`${apiClient.baseUrl}/api/files/list`);
        if (response.ok) {
          const data = await response.json();
          availableFiles.value = data.files || [];
        }
      } catch (error) {
        console.error('Error loading files:', error);
        availableFiles.value = [];
      }
    };

    const handleFileUpload = async (event) => {
      const file = event.target.files[0];
      if (!file) return;

      try {

        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch(`${apiClient.baseUrl}/api/files/upload`, {
          method: 'POST',
          body: formData
        });

        if (response.ok) {
          const result = await response.json();
          selectedFile.value = { name: file.name, path: result.path };
          currentEntry.value.source = file.name;

          // Try to extract content from the uploaded file
          await extractFileContent(result.path || file.name);

          // Also set collection based on file type
          if (!currentEntry.value.collection || currentEntry.value.collection === 'default') {
            const extension = file.name.split('.').pop().toLowerCase();
            if (extension === 'pdf') {
              currentEntry.value.collection = 'documents';
            } else if (['md', 'txt'].includes(extension)) {
              currentEntry.value.collection = 'text-files';
            } else if (['json', 'xml'].includes(extension)) {
              currentEntry.value.collection = 'data-files';
            }
          }

        } else {
          const errorText = await response.text();
          console.error('Upload failed:', response.status, errorText);
          showError(`Upload failed: ${response.statusText}`);
        }
      } catch (error) {
        console.error('Error uploading file:', error);
        showError('Error uploading file: ' + error.message);
      }

      // Clear the input
      event.target.value = '';
    };

    const selectFileForKnowledge = async (file) => {
      selectedFile.value = file;
      currentEntry.value.source = file.name;
      showFileSelector.value = false;

      // Try to extract content from the file
      await extractFileContent(file.path || file.name);
    };

    const extractFileContent = async (filePath) => {
      try {
        const response = await fetch(`${apiClient.baseUrl}/api/files/view/${encodeURIComponent(filePath)}`);
        if (response.ok) {
          const contentType = response.headers.get('content-type');

          // Handle different file types
          if (contentType && (contentType.includes('text') || contentType.includes('application/json'))) {
            const content = await response.text();
            currentEntry.value.content = content;

            // Auto-generate title if empty
            if (!currentEntry.value.title) {
              const fileName = filePath.split('/').pop();
              const baseName = fileName.replace(/\.[^/.]+$/, ''); // Remove extension
              currentEntry.value.title = baseName.replace(/[_-]/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
            }

            showSuccess(`Successfully extracted ${content.length} characters from ${filePath}`);
          } else if (contentType && contentType.includes('pdf')) {
            // For PDF files, try to extract text via backend
            try {
              const pdfResponse = await fetch(`${apiClient.baseUrl}/api/files/extract-text/${encodeURIComponent(filePath)}`);
              if (pdfResponse.ok) {
                const pdfData = await pdfResponse.json();
                currentEntry.value.content = pdfData.text || '';
                showSuccess(`Successfully extracted ${pdfData.text?.length || 0} characters from PDF`);
              } else {
                showError('Could not extract text from PDF file');
              }
            } catch (pdfError) {
              console.error('PDF extraction error:', pdfError);
              showError('PDF text extraction is not available');
            }
          } else {
            showError(`Unsupported file type: ${contentType}. Please use text files, JSON, or PDFs.`);
          }
        } else {
          console.error('Failed to fetch file:', response.status, response.statusText);
          showError(`Failed to access file: ${response.statusText}`);
        }
      } catch (error) {
        console.error('Error extracting file content:', error);
        showError('Error extracting file content: ' + error.message);
      }
    };

    const getFileIcon = (file) => {
      const extension = file.name.split('.').pop().toLowerCase();
      const iconMap = {
        'txt': '📄',
        'pdf': '📕',
        'doc': '📘',
        'docx': '📘',
        'md': '📝',
        'json': '📊',
        'xml': '📋',
        'csv': '📊',
        'py': '🐍',
        'js': '📜',
        'html': '🌐',
        'css': '🎨',
        'img': '🖼️',
        'png': '🖼️',
        'jpg': '🖼️',
        'jpeg': '🖼️',
        'gif': '🖼️'
      };
      return iconMap[extension] || '📎';
    };

    const formatFileSize = (bytes) => {
      if (!bytes) return '0 B';
      const sizes = ['B', 'KB', 'MB', 'GB'];
      const i = Math.floor(Math.log(bytes) / Math.log(1024));
      return Math.round(bytes / Math.pow(1024, i) * 100) / 100 + ' ' + sizes[i];
    };

    const getEntryTitle = (entry) => {
      return entry.title || entry.metadata?.title || entry.metadata?.source || 'Untitled Entry';
    };

    const getEntryPreview = (entry) => {
      const content = entry.content || '';
      return content.length > 150 ? content.substring(0, 150) + '...' : content;
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
        const response = await fetch(`${apiClient.getBaseUrl()}/api/knowledge_base/crawl_url`, {
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
        const response = await fetch(`${apiClient.getBaseUrl()}/api/knowledge_base/crawl_url`, {
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

        // Add automatic tags based on content
        let finalTags = [...(currentEntry.value.tags || [])];
        if (currentEntry.value.content) {
          const contentLower = currentEntry.value.content.toLowerCase();
          const autoTags = [];

          // Add OS-specific tags
          if (contentLower.includes('debian') || contentLower.includes('ubuntu')) {
            autoTags.push('debian', 'linux', 'operating-system');
          }
          if (contentLower.includes('windows')) {
            autoTags.push('windows', 'operating-system');
          }
          if (contentLower.includes('macos') || contentLower.includes('mac os')) {
            autoTags.push('macos', 'operating-system');
          }

          // Add tech-specific tags
          if (contentLower.includes('python')) autoTags.push('python', 'programming');
          if (contentLower.includes('javascript') || contentLower.includes('node')) {
            autoTags.push('javascript', 'programming');
          }
          if (contentLower.includes('docker')) autoTags.push('docker', 'containerization');
          if (contentLower.includes('kubernetes')) autoTags.push('kubernetes', 'orchestration');

          // Add manual/documentation tags
          if (contentLower.includes('manual') || contentLower.includes('guide') || contentLower.includes('tutorial')) {
            autoTags.push('manual', 'documentation');
          }

          // Merge with existing tags
          finalTags = [...new Set([...finalTags, ...autoTags])];
        }

        const entryData = {
          type: currentEntry.value.title || currentEntry.value.source || 'Manual Entry',
          content: currentEntry.value.content,
          source: currentEntry.value.source,
          title: currentEntry.value.title,
          collection: currentEntry.value.collection || 'default',
          metadata: {
            source: currentEntry.value.source,
            tags: finalTags,
            links: currentEntry.value.links,
            title: currentEntry.value.title,
            // Add file metadata if file is selected
            ...(selectedFile.value && {
              file_path: selectedFile.value.path || selectedFile.value.name,
              file_name: selectedFile.value.name,
              resource_type: 'knowledge',
              content_extracted: true,
              content_length: currentEntry.value.content?.length || 0
            })
          }
        };


        let response;
        if (showEditModal.value) {
          response = await fetch(`${apiClient.getBaseUrl()}/api/knowledge_base/entries/${currentEntry.value.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(entryData)
          });
        } else {
          response = await fetch(`${apiClient.getBaseUrl()}/api/knowledge_base/entries`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(entryData)
          });
        }

        if (!response.ok) {
          const errorText = await response.text();
          console.error('API Response:', response.status, response.statusText, errorText);
          throw new Error(`Failed to ${showEditModal.value ? 'update' : 'create'} entry: ${response.status} ${response.statusText}`);
        }

        // If it's a new URL entry with no content, auto-crawl it
        if (!showEditModal.value && isUrlSource(currentEntry.value.source) && !currentEntry.value.content) {
          const result = await response.json();
          if (result.id) {
            try {
              const crawlResponse = await fetch(`${apiClient.getBaseUrl()}/api/knowledge_base/crawl_url`, {
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

    // Categories functionality
    const categories = ref([]);
    const loadingCategories = ref(false);

    const loadCategories = async () => {
      try {
        loadingCategories.value = true;
        const response = await apiClient.get('/api/knowledge_base/categories');
        const data = await response.json();
        categories.value = data.categories || [];
      } catch (error) {
        console.error('Error loading categories:', error);
        categories.value = [];
      } finally {
        loadingCategories.value = false;
      }
    };

    const refreshCategories = () => {
      loadCategories();
    };

    const browseCategory = (categoryName) => {
      // Switch to entries tab and filter by category
      activeTab.value = 'entries';
      entriesSearchQuery.value = categoryName;
      filterEntries();
    };

    const editCategory = (category) => {
      // TODO: Implement category editing
    };

    // System Knowledge functionality
    const systemKnowledge = ref([]);
    const loadingSystemKnowledge = ref(false);
    const importingDocs = ref(false);

    const loadSystemKnowledge = async () => {
      try {
        loadingSystemKnowledge.value = true;
        const response = await apiClient.get('/api/knowledge_base/system_knowledge/documentation');
        const data = await response.json();
        systemKnowledge.value = data.documentation || [];
      } catch (error) {
        console.error('Error loading system knowledge:', error);
        systemKnowledge.value = [];
      } finally {
        loadingSystemKnowledge.value = false;
      }
    };

    const refreshSystemKnowledge = () => {
      loadSystemKnowledge();
    };

    const importSystemDocs = async () => {
      try {
        importingDocs.value = true;
        const response = await fetch(`${apiClient.getBaseUrl()}/api/knowledge_base/system_knowledge/import_documentation`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        });

        if (!response.ok) {
          throw new Error('Failed to import documentation');
        }

        const result = await response.json();
        showSuccess(`Documentation imported successfully! Imported ${result.count || 0} documents.`);
        await loadSystemKnowledge();
      } catch (error) {
        console.error('Error importing documentation:', error);
        showError('Failed to import documentation: ' + error.message);
      } finally {
        importingDocs.value = false;
      }
    };

    const getDocTypeIcon = (type) => {
      const iconMap = {
        'guide': '📚',
        'api': '🔌',
        'tutorial': '🎓',
        'reference': '📖',
        'configuration': '⚙️',
        'documentation': '📄'
      };
      return iconMap[type] || '📄';
    };

    const viewSystemDoc = (doc) => {
      // TODO: Implement system doc viewer
    };

    const editSystemDoc = (doc) => {
      if (doc.immutable) {
        showError('This document is immutable and cannot be edited');
        return;
      }
      // TODO: Implement system doc editor
    };

    const exportSystemDoc = (doc) => {
      // TODO: Implement system doc export
    };

    const getDocPreview = (doc) => {
      const content = doc.content || doc.description || '';
      return content.length > 200 ? content.substring(0, 200) + '...' : content;
    };


    // System Prompts functionality
    const systemPrompts = ref([]);
    const loadingSystemPrompts = ref(false);
    const importingPrompts = ref(false);

    const loadSystemPrompts = async () => {
      try {
        loadingSystemPrompts.value = true;
        const response = await apiClient.get('/api/knowledge_base/system_knowledge/prompts');
        const data = await response.json();
        systemPrompts.value = data.prompts || [];
      } catch (error) {
        console.error('Error loading system prompts:', error);
        systemPrompts.value = [];
      } finally {
        loadingSystemPrompts.value = false;
      }
    };

    const refreshSystemPrompts = () => {
      loadSystemPrompts();
    };

    const importSystemPrompts = async () => {
      try {
        importingPrompts.value = true;
        const response = await fetch(`${apiClient.getBaseUrl()}/api/knowledge_base/system_knowledge/import_prompts`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        });

        if (!response.ok) {
          throw new Error('Failed to import prompts');
        }

        const result = await response.json();
        showSuccess(`Prompts imported successfully! Imported ${result.count || 0} prompts.`);
        await loadSystemPrompts();
      } catch (error) {
        console.error('Error importing prompts:', error);
        showError('Failed to import prompts: ' + error.message);
      } finally {
        importingPrompts.value = false;
      }
    };

    const getPromptIcon = (category) => {
      const iconMap = {
        'agent': '🤖',
        'chat': '💬',
        'system': '⚙️',
        'tool': '🔧',
        'analysis': '🔍',
        'creative': '🎨'
      };
      return iconMap[category] || '🎯';
    };

    const useSystemPrompt = (prompt) => {
      // TODO: Implement prompt usage
    };

    const viewSystemPrompt = (prompt) => {
      // TODO: Implement system prompt viewer
    };

    const editSystemPrompt = (prompt) => {
      if (prompt.immutable) {
        showError('This prompt is immutable and cannot be edited');
        return;
      }
      // TODO: Implement system prompt editor
    };

    const duplicateSystemPrompt = (prompt) => {
      // TODO: Implement system prompt duplication
    };

    const createSystemPrompt = () => {
      // TODO: Implement system prompt creation
    };

    const getPromptPreview = (template) => {
      const content = template || '';
      return content.length > 100 ? content.substring(0, 100) + '...' : content;
    };

    // Utility functions

    // Watch for file selector modal
    watch(showFileSelector, (newVal) => {
      if (newVal) {
        loadAvailableFiles();
      }
    });

    // Initialize component
    onMounted(async () => {
      // Load settings first (synchronous)
      loadSettings();

      // Only load data for the currently active tab to improve performance
      await loadDataForActiveTab();
    });

    // Load data based on active tab to reduce initial load time
    const loadDataForActiveTab = async () => {
      try {
        switch (activeTab.value) {
          case 'search':
            // Search tab doesn't need preloading
            break;
          case 'categories':
            await loadCategories();
            break;
          case 'entries':
            await loadKnowledgeEntries();
            break;
          case 'system':
            await loadSystemKnowledge();
            break;
          case 'prompts':
            await loadSystemPrompts();
            break;
          case 'stats':
            await loadStats();
            break;
          default:
            // For initial load, only load entries and categories
            await loadKnowledgeEntries();
            break;
        }
      } catch (error) {
        console.error('Error loading tab data:', error);
      }
    };

    // Watch for tab changes and load data as needed
    watch(activeTab, async (newTab, oldTab) => {
      if (newTab !== oldTab) {
        await loadDataForActiveTab();
      }
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

      // Enhanced Search
      showAdvancedSearch,
      showSuggestions,
      searchSuggestions,
      searchTime,
      searchFilters,
      availableCollections,
      toggleAdvancedSearch,
      onSearchInput,
      applySuggestion,

      // Results Management
      sortBy,
      sortOrder,
      resultsViewMode,
      currentPage,
      resultsPerPage,
      filteredResults,
      totalPages,
      paginatedResults,
      sortResults,
      toggleSortOrder,

      // Result Helpers
      highlightText,
      getResultTitle,
      getResultPreview,
      getScoreClass,
      viewResult,
      useResult,
      copyResult,

      // Search UI helpers
      showSearchHelp,
      hideSearchHelp,
      suggestionCounts,
      selectedSuggestionIndex,
      clearSearch,
      selectResult,
      getTypeIcon,
      formatContentSize,
      isBookmarked,
      bookmarkResult,
      exportResults,

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
      loadDataForActiveTab,
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

      // File integration
      showFileSelector,
      selectedFile,
      availableFiles,
      handleFileUpload,
      selectFileForKnowledge,
      getFileIcon,
      formatFileSize,

      // Add content
      addContentType,
      textContent,
      textTitle,
      textSource,
      urlContent,
      urlMethod,
      adding,
      addMessage,
      addMessageType,
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
      deleteTemplate,

      // Categories
      categories,
      loadingCategories,
      loadCategories,
      refreshCategories,
      browseCategory,
      editCategory,

      // System Knowledge
      systemKnowledge,
      loadingSystemKnowledge,
      importingDocs,
      loadSystemKnowledge,
      refreshSystemKnowledge,
      importSystemDocs,
      getDocTypeIcon,
      viewSystemDoc,
      editSystemDoc,
      exportSystemDoc,
      getDocPreview,
      formatContentSize,

      // System Prompts
      systemPrompts,
      loadingSystemPrompts,
      importingPrompts,
      loadSystemPrompts,
      refreshSystemPrompts,
      importSystemPrompts,
      getPromptIcon,
      useSystemPrompt,
      viewSystemPrompt,
      editSystemPrompt,
      duplicateSystemPrompt,
      createSystemPrompt,
      getPromptPreview
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
  min-height: 0; /* Allow flexbox to shrink */
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
  min-height: 0; /* Allow flexbox to shrink */
  display: flex;
  flex-direction: column;
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

.search-results {
  flex: 1;
  overflow-y: auto;
  min-height: 0; /* Allow scrolling within results */
}

.search-results h4 {
  color: #333;
  margin-bottom: 15px;
  flex-shrink: 0; /* Keep header visible */
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
  max-height: 200px;
  overflow-y: auto;
  word-wrap: break-word;
  white-space: pre-wrap;
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
  flex-shrink: 0; /* Keep header visible */
}

.entries-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0; /* Allow scrolling */
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
  flex-shrink: 0; /* Keep search bar visible */
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
  flex: 1;
  overflow-y: auto;
  min-height: 0; /* Allow scrolling within list */
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
  max-height: 400px;
  overflow-y: auto;
  word-wrap: break-word;
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

/* Categories Tab Styles */
.categories-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.categories-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
  margin-bottom: 20px;
}

.category-card {
  background: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 8px;
  padding: 20px;
  text-align: center;
  transition: all 0.3s ease;
}

.category-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.category-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.category-card h4 {
  margin: 0 0 8px 0;
  color: #333;
}

.category-description {
  color: #666;
  font-size: 14px;
  margin-bottom: 16px;
  min-height: 40px;
}

.category-stats {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-bottom: 16px;
  font-size: 12px;
  color: #888;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.category-actions {
  display: flex;
  justify-content: center;
  gap: 8px;
}

.browse-btn, .edit-btn {
  padding: 6px 12px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.browse-btn {
  background: #007bff;
  color: white;
}

.browse-btn:hover {
  background: #0056b3;
}

.edit-btn {
  background: #6c757d;
  color: white;
}

.edit-btn:hover {
  background: #5a6268;
}

/* System Knowledge Tab Styles */
.system-knowledge-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.refresh-btn, .import-btn {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.refresh-btn {
  background: #6c757d;
  color: white;
}

.refresh-btn:hover {
  background: #5a6268;
}

.import-btn {
  background: #17a2b8;
  color: white;
}

.import-btn:hover:not(:disabled) {
  background: #138496;
}

.import-btn:disabled {
  background: #adb5bd;
  cursor: not-allowed;
}

.import-btn.primary {
  background: #007bff;
  padding: 12px 24px;
  font-size: 16px;
}

.import-btn.primary:hover:not(:disabled) {
  background: #0056b3;
}

.system-knowledge-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.system-doc-item {
  background: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 8px;
  padding: 16px;
}

.doc-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}

.doc-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.doc-type-icon {
  font-size: 20px;
}

.doc-title h4 {
  margin: 0;
  color: #333;
}

.doc-badges {
  display: flex;
  gap: 8px;
  margin-left: 12px;
}

.badge {
  padding: 4px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.badge.doc-type {
  background: #e7f3ff;
  color: #0066cc;
}

.badge.doc-status {
  background: #e8f5e8;
  color: #2e7d2e;
}

.badge.doc-status.inactive {
  background: #fff2cd;
  color: #856404;
}

.badge.doc-status.deprecated {
  background: #f8d7da;
  color: #721c24;
}

.doc-actions {
  display: flex;
  gap: 8px;
}

.view-btn, .export-btn {
  padding: 6px 8px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  background: #6c757d;
  color: white;
}

.view-btn:hover, .export-btn:hover {
  background: #5a6268;
}

.doc-preview {
  margin-bottom: 12px;
  color: #666;
  font-size: 14px;
  line-height: 1.5;
}

.doc-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 12px;
  color: #888;
}

.doc-source, .doc-version, .doc-updated, .doc-size {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* System Prompts Tab Styles */
.system-prompts-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.system-prompts-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
}

.prompt-card {
  background: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 8px;
  padding: 16px;
  transition: all 0.3s ease;
}

.prompt-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.prompt-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}

.prompt-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.prompt-icon {
  font-size: 18px;
}

.prompt-title h4 {
  margin: 0;
  color: #333;
  font-size: 16px;
}

.prompt-actions {
  display: flex;
  gap: 6px;
}

.use-btn, .duplicate-btn {
  padding: 4px 6px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.use-btn {
  background: #28a745;
  color: white;
}

.use-btn:hover {
  background: #218838;
}

.duplicate-btn {
  background: #17a2b8;
  color: white;
}

.duplicate-btn:hover {
  background: #138496;
}

.prompt-description {
  margin-bottom: 12px;
  color: #666;
  font-size: 14px;
  line-height: 1.4;
  min-height: 40px;
}

.prompt-preview {
  background: #2d3748;
  color: #e2e8f0;
  padding: 12px;
  border-radius: 4px;
  margin-bottom: 12px;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 12px;
  line-height: 1.4;
  overflow: hidden;
  max-height: 80px;
}

.prompt-preview code {
  background: none;
  color: inherit;
  padding: 0;
}

.prompt-meta {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.prompt-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.prompt-tags .tag {
  padding: 2px 6px;
  background: #e9ecef;
  color: #495057;
  border-radius: 10px;
  font-size: 11px;
}

.more-tags {
  padding: 2px 6px;
  background: #dee2e6;
  color: #6c757d;
  border-radius: 10px;
  font-size: 11px;
  font-style: italic;
}

.prompt-info {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 11px;
  color: #888;
}

.prompt-category, .prompt-version, .prompt-usage {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* Loading and Empty States */
.loading-message {
  text-align: center;
  padding: 40px;
  color: #666;
  font-style: italic;
}

.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: #666;
}

.empty-state .icon.large {
  font-size: 64px;
  margin-bottom: 16px;
  display: block;
}

.empty-state h4 {
  margin: 0 0 8px 0;
  color: #333;
}

.empty-state p {
  margin: 0 0 20px 0;
  font-size: 14px;
  line-height: 1.5;
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

/* File Integration Styles */
.source-input-group {
  display: flex;
  gap: 8px;
  align-items: center;
}

.source-input-group input {
  flex: 1;
}

.file-select-btn,
.file-upload-btn {
  padding: 8px 12px;
  background: #f1f3f5;
  border: 1px solid #dee2e6;
  border-radius: 4px;
  cursor: pointer;
  font-size: 16px;
  transition: all 0.3s ease;
}

.file-select-btn:hover,
.file-upload-btn:hover {
  background: #e9ecef;
  border-color: #6c757d;
}

.file-hint {
  color: #28a745;
  font-style: italic;
}

.file-selector-modal {
  max-width: 600px;
  max-height: 70vh;
}

.file-list-container {
  max-height: 400px;
  overflow-y: auto;
}

.file-list {
  border: 1px solid #dee2e6;
  border-radius: 4px;
  padding: 8px;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  margin: 4px 0;
  background: #f8f9fa;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.file-item:hover {
  background: #e9ecef;
  transform: translateX(4px);
}

.file-icon {
  font-size: 24px;
}

.file-name {
  flex: 1;
  font-weight: 500;
}

.file-size {
  color: #6c757d;
  font-size: 0.875em;
}

.loading-files {
  text-align: center;
  padding: 40px;
  color: #6c757d;
}

/* Enhanced Search Interface Styles */
.search-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.toggle-advanced-btn {
  padding: 8px 16px;
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.toggle-advanced-btn:hover,
.toggle-advanced-btn.active {
  background: #007bff;
  color: white;
  border-color: #007bff;
}

.search-input-container {
  display: flex;
  gap: 10px;
  margin-bottom: 15px;
}

.main-search-input {
  flex: 1;
  padding: 12px 16px;
  border: 2px solid #dee2e6;
  border-radius: 6px;
  font-size: 16px;
  transition: border-color 0.3s ease;
}

.main-search-input:focus {
  border-color: #007bff;
  outline: none;
}

.search-btn {
  padding: 12px 24px;
  background: #007bff;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  transition: background-color 0.3s ease;
}

.search-btn:hover:not(:disabled) {
  background: #0056b3;
}

.search-btn:disabled {
  background: #6c757d;
  cursor: not-allowed;
}

/* Search Suggestions */
.search-suggestions {
  position: absolute;
  top: 100%;
  left: 0;
  right: 60px;
  background: white;
  border: 1px solid #dee2e6;
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  z-index: 1000;
  max-height: 200px;
  overflow-y: auto;
}

.suggestion-item {
  padding: 10px 16px;
  cursor: pointer;
  transition: background-color 0.3s ease;
}

.suggestion-item:hover {
  background: #f8f9fa;
}

/* Advanced Search Filters */
.advanced-search {
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 6px;
  padding: 20px;
  margin-top: 15px;
}

.filter-row {
  display: flex;
  gap: 20px;
  margin-bottom: 15px;
  flex-wrap: wrap;
}

.filter-group {
  display: flex;
  flex-direction: column;
  min-width: 150px;
  flex: 1;
}

.filter-group label {
  font-weight: 500;
  margin-bottom: 5px;
  color: #495057;
}

.filter-group select,
.filter-group input[type="text"] {
  padding: 8px 12px;
  border: 1px solid #ced4da;
  border-radius: 4px;
  font-size: 14px;
}

.score-slider {
  width: 100%;
}

.score-value {
  margin-left: 10px;
  font-weight: 500;
  color: #007bff;
}

.search-options {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
}

.checkbox-option {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 14px;
}

.checkbox-option input[type="checkbox"] {
  width: 16px;
  height: 16px;
}

/* Results Header */
.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 20px 0 15px 0;
  padding: 15px;
  background: #f8f9fa;
  border-radius: 6px;
}

.results-info h4 {
  margin: 0;
  color: #495057;
}

.search-time {
  color: #6c757d;
  font-size: 14px;
  font-style: italic;
}

.results-controls {
  display: flex;
  gap: 20px;
  align-items: center;
}

.sort-controls,
.view-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sort-controls select {
  padding: 6px 12px;
  border: 1px solid #ced4da;
  border-radius: 4px;
}

.sort-order-btn,
.view-mode-btn {
  padding: 6px 12px;
  background: #e9ecef;
  border: 1px solid #ced4da;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.sort-order-btn:hover,
.view-mode-btn:hover,
.view-mode-btn.active {
  background: #007bff;
  color: white;
  border-color: #007bff;
}

/* Enhanced Results Display */
.search-results.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 20px;
}

.search-result {
  background: white;
  border: 1px solid #dee2e6;
  border-radius: 8px;
  padding: 20px;
  transition: all 0.3s ease;
}

.search-result:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  border-color: #007bff;
}

.search-result.high-score {
  border-left: 4px solid #28a745;
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 15px;
}

.result-title h5 {
  margin: 0 0 8px 0;
  color: #212529;
  line-height: 1.3;
}

.result-title h5 mark {
  background: #fff3cd;
  padding: 2px 4px;
  border-radius: 3px;
}

.result-badges {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.badge {
  padding: 4px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  text-transform: uppercase;
}

.badge.score {
  background: #e9ecef;
  color: #495057;
}

.badge.score.high {
  background: #d1e7dd;
  color: #0f5132;
}

.badge.score.medium {
  background: #fff3cd;
  color: #664d03;
}

.badge.score.low {
  background: #f8d7da;
  color: #721c24;
}

.badge.type,
.badge.collection {
  background: #cff4fc;
  color: #055160;
}

.result-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  padding: 6px 10px;
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.3s ease;
}

.action-btn:hover {
  background: #007bff;
  color: white;
  border-color: #007bff;
}

.result-content p {
  color: #6c757d;
  line-height: 1.5;
  margin: 0;
}

.result-content mark {
  background: #fff3cd;
  padding: 2px 4px;
  border-radius: 3px;
  font-weight: 500;
}

.result-metadata {
  margin-top: 15px;
  padding-top: 15px;
  border-top: 1px solid #e9ecef;
}

.result-tags,
.metadata-items {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.result-tags {
  margin-bottom: 8px;
}

.tag,
.more-tags {
  background: #e7f3ff;
  color: #0056b3;
  padding: 3px 8px;
  border-radius: 12px;
  font-size: 12px;
}

.more-tags {
  background: #f8f9fa;
  color: #6c757d;
}

.metadata-item {
  color: #6c757d;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 4px;
}

/* Pagination */
.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 10px;
  margin-top: 30px;
}

.page-btn {
  padding: 8px 16px;
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.page-btn:hover:not(:disabled) {
  background: #007bff;
  color: white;
  border-color: #007bff;
}

.page-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.page-info {
  margin: 0 10px;
  font-weight: 500;
  color: #495057;
}

/* Search Tips */
.search-tips {
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 8px;
  padding: 20px;
  margin-top: 20px;
}

.search-tips h4 {
  margin: 0 0 15px 0;
  color: #495057;
}

.tips-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 15px;
}

.tip-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 15px;
  background: white;
  border-radius: 6px;
  border-left: 3px solid #007bff;
}

.tip-icon {
  font-size: 18px;
  margin-top: 2px;
}

/* Enhanced Search UI Styles */
.search-input-wrapper {
  position: relative;
  flex: 1;
  display: flex;
  align-items: center;
}

.main-search-input.enhanced {
  width: 100%;
  padding: 12px 45px 12px 16px;
  border: 2px solid #e1e5e9;
  border-radius: 8px;
  font-size: 16px;
  transition: all 0.3s ease;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.main-search-input.enhanced:focus {
  outline: none;
  border-color: #007bff;
  box-shadow: 0 4px 8px rgba(0, 123, 255, 0.15);
}

.search-input-icons {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
}

.search-spinner, .clear-search, .search-icon {
  font-size: 16px;
  color: #6c757d;
  cursor: pointer;
}

.clear-search:hover {
  color: #dc3545;
}

.search-btn.enhanced {
  padding: 12px 20px;
  margin-left: 12px;
  background: linear-gradient(45deg, #007bff, #0056b3);
  color: white;
  border: none;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
  box-shadow: 0 2px 4px rgba(0, 123, 255, 0.3);
}

.search-btn.enhanced:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(0, 123, 255, 0.4);
}

.search-btn.enhanced:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.search-help-tooltip {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  background: white;
  border: 1px solid #dee2e6;
  border-radius: 8px;
  padding: 16px;
  z-index: 1000;
  margin-top: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.help-item {
  margin-bottom: 8px;
  font-size: 14px;
  color: #6c757d;
}

.help-item:last-child {
  margin-bottom: 0;
}

.search-suggestions.enhanced {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  background: white;
  border: 1px solid #dee2e6;
  border-radius: 8px;
  z-index: 1000;
  margin-top: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  overflow: hidden;
}

.suggestions-header {
  padding: 12px 16px;
  background: #f8f9fa;
  border-bottom: 1px solid #dee2e6;
  font-weight: 600;
  color: #495057;
  display: flex;
  align-items: center;
  gap: 8px;
}

.suggestion-item.enhanced {
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  transition: background-color 0.2s ease;
  border-bottom: 1px solid #f1f3f4;
}

.suggestion-item.enhanced:hover,
.suggestion-item.enhanced.highlighted {
  background: #f8f9fa;
}

.suggestion-icon {
  color: #6c757d;
  font-size: 14px;
}

.suggestion-text {
  flex: 1;
  font-size: 14px;
  color: #495057;
}

.suggestion-count {
  font-size: 12px;
  color: #6c757d;
  background: #e9ecef;
  padding: 2px 6px;
  border-radius: 10px;
}

.search-results.enhanced {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.search-result.enhanced {
  background: white;
  border: 1px solid #e9ecef;
  border-radius: 12px;
  padding: 20px;
  transition: all 0.3s ease;
  cursor: pointer;
}

.search-result.enhanced:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 25px rgba(0, 0, 0, 0.1);
  border-color: #007bff;
}

.search-result.enhanced.high-score {
  border-left: 4px solid #28a745;
}

.search-result.enhanced.medium-score {
  border-left: 4px solid #ffc107;
}

.search-result.enhanced.low-score {
  border-left: 4px solid #dc3545;
}

.result-header.enhanced {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}

.result-badges {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 8px;
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.badge.score.high {
  background: #d4edda;
  color: #155724;
}

.badge.score.medium {
  background: #fff3cd;
  color: #856404;
}

.badge.score.low {
  background: #f8d7da;
  color: #721c24;
}

.badge.type {
  background: #e2e3e5;
  color: #6c757d;
}

.badge.collection {
  background: #d1ecf1;
  color: #0c5460;
}

.result-actions.enhanced {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.action-btn {
  padding: 8px;
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 36px;
  height: 36px;
}

.action-btn:hover {
  background: #e9ecef;
  transform: translateY(-1px);
}

.action-btn.view-btn:hover {
  color: #007bff;
  border-color: #007bff;
}

.action-btn.use-btn:hover {
  color: #28a745;
  border-color: #28a745;
}

.action-btn.copy-btn:hover {
  color: #6c757d;
  border-color: #6c757d;
}

.action-btn.bookmark-btn.bookmarked {
  background: #fff3cd;
  color: #856404;
  border-color: #ffeaa7;
}

.result-metadata {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 12px;
  color: #6c757d;
}

.result-tags {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tag {
  background: #e9ecef;
  color: #6c757d;
  padding: 2px 6px;
  border-radius: 10px;
  font-size: 11px;
}

.more-tags {
  color: #6c757d;
  font-style: italic;
}

.metadata-items {
  display: flex;
  gap: 16px;
  align-items: center;
}

.metadata-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.no-results {
  text-align: center;
  padding: 60px 20px;
  color: #6c757d;
}

.no-results-icon {
  font-size: 48px;
  margin-bottom: 16px;
  opacity: 0.5;
}

.no-results h3 {
  margin: 16px 0;
  color: #495057;
}

.no-results-suggestions {
  margin: 24px 0;
  text-align: left;
  display: inline-block;
}

.no-results-suggestions h4 {
  margin-bottom: 8px;
  color: #495057;
}

.no-results-suggestions ul {
  list-style: none;
  padding: 0;
}

.no-results-suggestions li {
  margin-bottom: 4px;
  color: #6c757d;
}

.no-results-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  margin-top: 24px;
}

.btn-secondary, .btn-primary {
  padding: 10px 20px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: all 0.2s ease;
}

.btn-secondary {
  background: #6c757d;
  color: white;
}

.btn-secondary:hover {
  background: #5a6268;
}

.btn-primary {
  background: #007bff;
  color: white;
}

.btn-primary:hover {
  background: #0056b3;
}

.view-controls.enhanced {
  display: flex;
  gap: 4px;
  background: #f8f9fa;
  border-radius: 6px;
  padding: 4px;
}

.view-mode-btn {
  padding: 8px 12px;
  background: transparent;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  color: #6c757d;
  transition: all 0.2s ease;
}

.view-mode-btn.active {
  background: white;
  color: #007bff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.export-btn {
  padding: 8px 12px;
  background: #17a2b8;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.export-btn:hover:not(:disabled) {
  background: #138496;
}

.export-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Card view mode */
.search-results.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 20px;
}

.search-results.cards .search-result.enhanced {
  height: fit-content;
}

/* Responsive Design for Enhanced Search */
@media (max-width: 768px) {
  .search-header {
    flex-direction: column;
    align-items: stretch;
    gap: 15px;
  }

  .filter-row {
    flex-direction: column;
    gap: 15px;
  }

  .results-header {
    flex-direction: column;
    align-items: stretch;
    gap: 15px;
  }

  .results-controls {
    justify-content: space-between;
  }

  .search-results.cards {
    grid-template-columns: 1fr;
  }

  .tips-grid {
    grid-template-columns: 1fr;
  }

  .result-actions.enhanced {
    flex-wrap: wrap;
  }

  .no-results-actions {
    flex-direction: column;
    align-items: center;
  }

  .search-input-container {
    flex-direction: column;
    gap: 12px;
  }

  .search-btn.enhanced {
    margin-left: 0;
  }
}
</style>
