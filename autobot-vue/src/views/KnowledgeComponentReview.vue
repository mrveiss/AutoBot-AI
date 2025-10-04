<template>
  <div class="component-review">
    <div class="review-header">
      <h1>Knowledge Component Review</h1>
      <p>Review all knowledge-related components and their usage</p>
    </div>

    <div class="components-list">
      <!-- Component Card: KnowledgeSearch -->
      <div class="component-card active">
        <div class="card-header">
          <h3>
            <i class="fas fa-check-circle text-green-500"></i>
            KnowledgeSearch.vue
          </h3>
          <span class="status-badge active">ACTIVE</span>
        </div>
        <div class="card-body">
          <p class="description">Search interface with RAG enhancement support</p>
          <div class="usage-info">
            <strong>Used by:</strong> /knowledge/search route
          </div>
          <div class="actions">
            <router-link to="/knowledge/search" class="btn-test">
              <i class="fas fa-play"></i> Test Component
            </router-link>
          </div>
        </div>
      </div>

      <!-- Component Card: KnowledgeCategories -->
      <div class="component-card active">
        <div class="card-header">
          <h3>
            <i class="fas fa-check-circle text-green-500"></i>
            KnowledgeCategories.vue
          </h3>
          <span class="status-badge active">ACTIVE</span>
        </div>
        <div class="card-body">
          <p class="description">Category selection view with 3 main category cards, opens KnowledgeBrowser when clicked</p>
          <div class="usage-info">
            <strong>Used by:</strong> /knowledge/categories route
          </div>
          <div class="actions">
            <router-link to="/knowledge/categories" class="btn-test">
              <i class="fas fa-play"></i> Test Component
            </router-link>
          </div>
        </div>
      </div>

      <!-- Component Card: KnowledgeManager -->
      <div class="component-card active">
        <div class="card-header">
          <h3>
            <i class="fas fa-check-circle text-green-500"></i>
            KnowledgeManager.vue
          </h3>
          <span class="status-badge active">ACTIVE</span>
        </div>
        <div class="card-body">
          <p class="description">Manage tab container with Entries, Upload, System Knowledge sub-tabs</p>
          <div class="usage-info">
            <strong>Used by:</strong> /knowledge/manage route
          </div>
          <div class="actions">
            <router-link to="/knowledge/manage" class="btn-test">
              <i class="fas fa-play"></i> Test Component
            </router-link>
          </div>
        </div>
      </div>

      <!-- Component Card: KnowledgeEntries -->
      <div class="component-card active">
        <div class="card-header">
          <h3>
            <i class="fas fa-check-circle text-green-500"></i>
            KnowledgeEntries.vue
          </h3>
          <span class="status-badge active">ACTIVE</span>
        </div>
        <div class="card-body">
          <p class="description">Entry management with sub-tabs: Manage Entries, Upload, System Knowledge</p>
          <div class="usage-info">
            <strong>Used by:</strong> KnowledgeManager (Manage tab content)
          </div>
          <div class="actions">
            <router-link to="/knowledge/manage" class="btn-test">
              <i class="fas fa-play"></i> Test Component
            </router-link>
          </div>
        </div>
      </div>

      <!-- Component Card: KnowledgeUpload -->
      <div class="component-card active">
        <div class="card-header">
          <h3>
            <i class="fas fa-check-circle text-green-500"></i>
            KnowledgeUpload.vue
          </h3>
          <span class="status-badge active">ACTIVE</span>
        </div>
        <div class="card-body">
          <p class="description">Document upload interface (text, URL, files)</p>
          <div class="usage-info">
            <strong>Used by:</strong> KnowledgeEntries (Upload sub-tab)
          </div>
          <div class="actions">
            <router-link to="/knowledge/manage" class="btn-test">
              <i class="fas fa-play"></i> Test Component
            </router-link>
          </div>
        </div>
      </div>

      <!-- Component Card: KnowledgeBrowser -->
      <div class="component-card active">
        <div class="card-header">
          <h3>
            <i class="fas fa-check-circle text-green-500"></i>
            KnowledgeBrowser.vue
          </h3>
          <span class="status-badge active">ACTIVE</span>
        </div>
        <div class="card-body">
          <p class="description">Knowledge browser for user/autobot knowledge base</p>
          <div class="usage-info">
            <strong>Used by:</strong> KnowledgeCategories (User & AutoBot browser tabs)
          </div>
          <div class="actions">
            <router-link to="/knowledge/categories" class="btn-test">
              <i class="fas fa-play"></i> Test Component
            </router-link>
          </div>
        </div>
      </div>

      <!-- Component Card: KnowledgeStats -->
      <div class="component-card active">
        <div class="card-header">
          <h3>
            <i class="fas fa-check-circle text-green-500"></i>
            KnowledgeStats.vue
          </h3>
          <span class="status-badge active">ACTIVE</span>
        </div>
        <div class="card-body">
          <p class="description">Knowledge base statistics and analytics</p>
          <div class="usage-info">
            <strong>Used by:</strong> /knowledge/stats route
          </div>
          <div class="actions">
            <router-link to="/knowledge/stats" class="btn-test">
              <i class="fas fa-play"></i> Test Component
            </router-link>
          </div>
        </div>
      </div>

      <!-- Component Card: KnowledgeAdvanced -->
      <div class="component-card active">
        <div class="card-header">
          <h3>
            <i class="fas fa-check-circle text-green-500"></i>
            KnowledgeAdvanced.vue
          </h3>
          <span class="status-badge active">ACTIVE</span>
        </div>
        <div class="card-body">
          <p class="description">Advanced knowledge base operations</p>
          <div class="usage-info">
            <strong>Used by:</strong> KnowledgeManager (Advanced tab)
          </div>
          <div class="actions">
            <router-link to="/knowledge/manage" class="btn-test">
              <i class="fas fa-play"></i> Test Component
            </router-link>
          </div>
        </div>
      </div>
    </div>

    <!-- Component Viewer Modal -->
    <div v-if="viewingComponent" class="modal-overlay" @click="closeViewer">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h3>{{ viewingComponent }}.vue</h3>
          <button @click="closeViewer" class="close-btn">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-body">
          <p class="text-gray-600 mb-4">This component is not used anywhere in the codebase.</p>
          <p class="text-gray-600 mb-4">File location: <code>src/components/knowledge/{{ viewingComponent }}.vue</code></p>
          <div class="confirmation-actions">
            <button @click="confirmDelete" class="btn-delete-confirm">
              <i class="fas fa-trash"></i> Confirm Delete
            </button>
            <button @click="closeViewer" class="btn-cancel">
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const viewingComponent = ref<string | null>(null)

const viewComponent = (name: string) => {
  viewingComponent.value = name
}

const closeViewer = () => {
  viewingComponent.value = null
}

const deleteComponent = (name: string) => {
  viewComponent(name)
}

const confirmDelete = () => {
  if (viewingComponent.value) {
    alert(`To delete ${viewingComponent.value}.vue, run:\nrm /home/kali/Desktop/AutoBot/autobot-vue/src/components/knowledge/${viewingComponent.value}.vue`)
    closeViewer()
  }
}
</script>

<style scoped>
.component-review {
  padding: 2rem;
  max-height: calc(100vh - 80px);
  overflow-y: auto;
}

.review-header {
  margin-bottom: 2rem;
}

.review-header h1 {
  font-size: 2rem;
  font-weight: 700;
  color: #1f2937;
  margin-bottom: 0.5rem;
}

.review-header p {
  color: #6b7280;
}

.components-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: 1.5rem;
}

.component-card {
  background: white;
  border-radius: 0.75rem;
  border: 2px solid #e5e7eb;
  overflow: hidden;
  transition: all 0.2s;
}

.component-card.active {
  border-color: #10b981;
}

.component-card.unused {
  border-color: #ef4444;
  opacity: 0.8;
}

.component-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  transform: translateY(-2px);
}

.card-header {
  padding: 1.5rem;
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-header h3 {
  font-size: 1.125rem;
  font-weight: 600;
  color: #1f2937;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.status-badge {
  padding: 0.25rem 0.75rem;
  border-radius: 0.375rem;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
}

.status-badge.active {
  background: #d1fae5;
  color: #065f46;
}

.status-badge.unused {
  background: #fee2e2;
  color: #991b1b;
}

.card-body {
  padding: 1.5rem;
}

.description {
  color: #4b5563;
  margin-bottom: 1rem;
  line-height: 1.5;
}

.usage-info {
  margin-bottom: 1.5rem;
  padding: 0.75rem;
  background: #f3f4f6;
  border-radius: 0.375rem;
  font-size: 0.875rem;
}

.usage-info strong {
  color: #374151;
}

.actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.btn-view,
.btn-delete,
.btn-test {
  padding: 0.5rem 1rem;
  border-radius: 0.375rem;
  font-size: 0.875rem;
  font-weight: 500;
  border: none;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  text-decoration: none;
}

.btn-view {
  background: #3b82f6;
  color: white;
}

.btn-view:hover {
  background: #2563eb;
}

.btn-delete {
  background: #ef4444;
  color: white;
}

.btn-delete:hover {
  background: #dc2626;
}

.btn-test {
  background: #10b981;
  color: white;
}

.btn-test:hover {
  background: #059669;
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

.modal-content {
  background: white;
  border-radius: 0.75rem;
  max-width: 600px;
  width: 90%;
  max-height: 80vh;
  overflow-y: auto;
}

.modal-header {
  padding: 1.5rem;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.modal-header h3 {
  font-size: 1.25rem;
  font-weight: 600;
  color: #1f2937;
}

.close-btn {
  width: 2rem;
  height: 2rem;
  border-radius: 0.375rem;
  border: none;
  background: #f3f4f6;
  color: #6b7280;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.close-btn:hover {
  background: #e5e7eb;
  color: #374151;
}

.modal-body {
  padding: 1.5rem;
}

.modal-body code {
  background: #f3f4f6;
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
  font-family: monospace;
  font-size: 0.875rem;
}

.confirmation-actions {
  display: flex;
  gap: 0.75rem;
  margin-top: 1.5rem;
}

.btn-delete-confirm {
  padding: 0.75rem 1.5rem;
  border-radius: 0.375rem;
  font-weight: 500;
  border: none;
  background: #ef4444;
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.btn-delete-confirm:hover {
  background: #dc2626;
}

.btn-cancel {
  padding: 0.75rem 1.5rem;
  border-radius: 0.375rem;
  font-weight: 500;
  border: 1px solid #d1d5db;
  background: white;
  color: #374151;
  cursor: pointer;
}

.btn-cancel:hover {
  background: #f9fafb;
}
</style>
