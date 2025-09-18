<template>
  <div class="file-browser">
    <div class="file-browser-header">
      <h2>File Browser</h2>
      <div class="file-actions">
        <button @click="refreshFiles" aria-label="Refresh">
          <i class="fas fa-sync-alt"></i> Refresh
        </button>
        <button @click="uploadFile" aria-label="Upload file">
          <i class="fas fa-upload"></i> Upload File
        </button>
        <button @click="toggleView" aria-label="Toggle view">
          <i :class="viewMode === 'tree' ? 'fas fa-list' : 'fas fa-tree'"></i>
          {{ viewMode === 'tree' ? 'List View' : 'Tree View' }}
        </button>
      </div>
    </div>

    <!-- Path Navigation -->
    <div class="path-navigation">
      <div class="breadcrumb">
        <span @click="navigateToPath('/')" class="breadcrumb-item">
          <i class="fas fa-home"></i> Home
        </span>
        <span v-for="(part, index) in pathParts" :key="index" class="breadcrumb-item">
          <i class="fas fa-chevron-right breadcrumb-separator"></i>
          <span @click="navigateToPath(getPathUpTo(index))" class="clickable">
            {{ part }}
          </span>
        </span>
      </div>
      <div class="path-input">
        <input
          v-model="currentPath"
          @keyup.enter="navigateToPath(currentPath)"
          placeholder="/path/to/directory"
          class="path-field"
        />
        <button @click="navigateToPath(currentPath)" class="path-go-btn">
          <i class="fas fa-arrow-right"></i>
        </button>
      </div>
    </div>

    <!-- File Upload Section -->
    <div class="file-upload-section">
      <label for="visible-file-input" class="file-input-label">
        <i class="fas fa-cloud-upload-alt"></i>
        Drag & drop files here or click to select:
      </label>
      <input
        id="visible-file-input"
        ref="visibleFileInput"
        type="file"
        @change="handleFileSelected"
        class="visible-file-input"
        data-testid="visible-file-upload-input"
        aria-label="Visible file upload input"
        multiple
      />
      <!-- Hidden file input for programmatic access -->
      <input
        ref="fileInput"
        type="file"
        style="display: none"
        @change="handleFileSelected"
        data-testid="file-upload-input"
        aria-label="File upload input"
        multiple
      />
    </div>

    <!-- File Preview Modal -->
    <div v-if="showPreview" class="file-preview-modal" @click="closePreview" tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
      <div class="modal-content" @click.stop tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
        <div class="modal-header">
          <h3>{{ previewFile?.name }}</h3>
          <button class="close-btn" @click="closePreview" aria-label="&times;">&times;</button>
        </div>
        <div class="modal-body">
          <!-- HTML File Preview -->
          <div v-if="previewFile?.type === 'html'" class="html-preview">
            <iframe
              :src="previewFile.url"
              class="html-frame"
              sandbox="allow-same-origin allow-scripts"
              title="HTML Preview">
            </iframe>
          </div>

          <!-- Image Preview -->
          <div v-else-if="previewFile?.type === 'image'" class="image-preview">
            <img :src="previewFile.url" :alt="previewFile.name" class="preview-image" />
          </div>

          <!-- Text/Code Preview -->
          <div v-else-if="previewFile?.type === 'text'" class="text-preview">
            <pre><code>{{ previewFile.content }}</code></pre>
          </div>

          <!-- JSON Preview -->
          <div v-else-if="previewFile?.type === 'json'" class="json-preview">
            <pre><code>{{ formatJson(previewFile.content) }}</code></pre>
          </div>

          <!-- PDF Preview -->
          <div v-else-if="previewFile?.type === 'pdf'" class="pdf-preview">
            <iframe :src="previewFile.url" class="pdf-frame" title="PDF Preview"></iframe>
          </div>

          <!-- Other file types -->
          <div v-else class="file-info">
            <p><strong>File:</strong> {{ previewFile?.name }}</p>
            <p><strong>Type:</strong> {{ previewFile?.fileType }}</p>
            <p><strong>Size:</strong> {{ formatSize(previewFile?.size) }}</p>
            <p>This file type cannot be previewed directly.</p>
            <button @click="downloadPreviewFile" class="download-btn" aria-label="Download file">Download File</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Main Content Area -->
    <div class="file-content-container">
      <!-- Tree View -->
      <div v-if="viewMode === 'tree'" class="tree-view">
        <div class="tree-panel">
          <div class="tree-header">
            <h3><i class="fas fa-folder-tree"></i> Directory Structure</h3>
            <div class="tree-controls">
              <button @click="expandAll" title="Expand All">
                <i class="fas fa-expand-alt"></i>
              </button>
              <button @click="collapseAll" title="Collapse All">
                <i class="fas fa-compress-alt"></i>
              </button>
            </div>
          </div>
          <div class="tree-content">
            <div 
              v-for="item in directoryTree" 
              :key="item.path"
              class="tree-node"
              :class="{ expanded: item.expanded, selected: selectedPath === item.path }"
            >
              <div 
                class="tree-node-content"
                @click="toggleNode(item)"
                :style="{ paddingLeft: (item.level * 20) + 'px' }"
              >
                <i 
                  v-if="item.is_dir"
                  :class="item.expanded ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"
                  class="tree-toggle"
                ></i>
                <i 
                  :class="getFileIcon(item)"
                  class="tree-icon"
                ></i>
                <span class="tree-label">{{ item.name }}</span>
              </div>
            </div>
          </div>
        </div>
        
        <!-- File List Panel -->
        <div class="files-panel">
          <div class="files-header">
            <h3><i class="fas fa-files"></i> {{ selectedPath || '/' }} Contents</h3>
          </div>
          <div class="file-list-container">
            <table class="file-table">
              <thead>
                <tr>
                  <th @click="sortBy('name')" class="sortable">
                    Name 
                    <i :class="getSortIcon('name')" class="sort-icon"></i>
                  </th>
                  <th @click="sortBy('type')" class="sortable">
                    Type
                    <i :class="getSortIcon('type')" class="sort-icon"></i>
                  </th>
                  <th @click="sortBy('size')" class="sortable">
                    Size
                    <i :class="getSortIcon('size')" class="sort-icon"></i>
                  </th>
                  <th @click="sortBy('modified')" class="sortable">
                    Modified
                    <i :class="getSortIcon('modified')" class="sort-icon"></i>
                  </th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(file, index) in sortedFiles" :key="file.name || file.id || `file-${index}`">
                  <td class="file-name-cell">
                    <i :class="getFileIcon(file)" class="file-icon"></i>
                    <span 
                      @click="file.is_dir ? navigateToPath(file.path) : null"
                      :class="{ clickable: file.is_dir }"
                      class="file-name"
                    >
                      {{ file.name }}
                    </span>
                  </td>
                  <td>{{ file.is_dir ? 'Directory' : getFileType(file.name) }}</td>
                  <td>{{ file.is_dir ? '-' : formatSize(file.size) }}</td>
                  <td>{{ formatDate(file.last_modified) }}</td>
                  <td>
                    <div class="action-buttons">
                      <button 
                        v-if="!file.is_dir" 
                        @click="viewFile(file)" 
                        class="action-btn view-btn"
                        aria-label="View"
                        title="View file"
                      >
                        <i class="fas fa-eye"></i>
                      </button>
                      <button 
                        v-if="file.is_dir" 
                        @click="navigateToPath(file.path)" 
                        class="action-btn open-btn"
                        aria-label="Open"
                        title="Open directory"
                      >
                        <i class="fas fa-folder-open"></i>
                      </button>
                      <button 
                        @click="deleteFile(file)" 
                        class="action-btn delete-btn"
                        aria-label="Delete"
                        title="Delete"
                      >
                        <i class="fas fa-trash"></i>
                      </button>
                    </div>
                  </td>
                </tr>
                <tr v-if="sortedFiles.length === 0">
                  <td colspan="5" class="no-files">
                    <i class="fas fa-folder-open"></i>
                    No files or directories found in {{ currentPath }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- List View (Original) -->
      <div v-else class="list-view">
        <table class="file-table">
          <thead>
            <tr>
              <th @click="sortBy('name')" class="sortable">
                Name 
                <i :class="getSortIcon('name')" class="sort-icon"></i>
              </th>
              <th @click="sortBy('type')" class="sortable">
                Type
                <i :class="getSortIcon('type')" class="sort-icon"></i>
              </th>
              <th @click="sortBy('size')" class="sortable">
                Size
                <i :class="getSortIcon('size')" class="sort-icon"></i>
              </th>
              <th @click="sortBy('modified')" class="sortable">
                Last Modified
                <i :class="getSortIcon('modified')" class="sort-icon"></i>
              </th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(file, index) in sortedFiles" :key="file.name || file.id || `file-${index}`">
              <td class="file-name-cell">
                <i :class="getFileIcon(file)" class="file-icon"></i>
                <span 
                  @click="file.is_dir ? navigateToPath(file.path) : null"
                  :class="{ clickable: file.is_dir }"
                  class="file-name"
                >
                  {{ file.name }}
                </span>
              </td>
              <td>{{ file.is_dir ? 'Directory' : getFileType(file.name) }}</td>
              <td>{{ file.is_dir ? '-' : formatSize(file.size) }}</td>
              <td>{{ formatDate(file.last_modified) }}</td>
              <td>
                <div class="action-buttons">
                  <button 
                    v-if="!file.is_dir" 
                    @click="viewFile(file)" 
                    class="action-btn view-btn"
                    aria-label="View"
                  >
                    <i class="fas fa-eye"></i>
                  </button>
                  <button 
                    v-if="file.is_dir" 
                    @click="navigateToPath(file.path)" 
                    class="action-btn open-btn"
                    aria-label="Open"
                  >
                    <i class="fas fa-folder-open"></i>
                  </button>
                  <button 
                    @click="deleteFile(file)" 
                    class="action-btn delete-btn"
                    aria-label="Delete"
                  >
                    <i class="fas fa-trash"></i>
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="sortedFiles.length === 0">
              <td colspan="5" class="no-files">
                <i class="fas fa-folder-open"></i>
                No files or directories found.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue';
import apiClient from '../utils/ApiClient.js';
import { useUserStore } from '../stores/useUserStore.ts';

export default {
  name: 'FileBrowser',
  setup() {
    const files = ref([]);
    const directoryTree = ref([]);
    const currentPath = ref('/');
    const selectedPath = ref('');
    const viewMode = ref('tree');
    const sortField = ref('name');
    const sortOrder = ref('asc');
    const showPreview = ref(false);
    const previewFile = ref(null);
    const fileInput = ref(null);
    const visibleFileInput = ref(null);

    // Computed properties
    const pathParts = computed(() => {
      return currentPath.value.split('/').filter(part => part);
    });

    const sortedFiles = computed(() => {
      const sorted = [...files.value].sort((a, b) => {
        let aVal = a[sortField.value];
        let bVal = b[sortField.value];
        
        // Handle different sort fields
        if (sortField.value === 'size') {
          aVal = a.size || 0;
          bVal = b.size || 0;
        } else if (sortField.value === 'modified') {
          aVal = new Date(a.last_modified || 0);
          bVal = new Date(b.last_modified || 0);
        } else if (sortField.value === 'type') {
          aVal = a.is_dir ? 'Directory' : getFileType(a.name);
          bVal = b.is_dir ? 'Directory' : getFileType(b.name);
        }
        
        // Sort directories first
        if (a.is_dir && !b.is_dir) return -1;
        if (!a.is_dir && b.is_dir) return 1;
        
        // Then sort by field
        if (aVal < bVal) return sortOrder.value === 'asc' ? -1 : 1;
        if (aVal > bVal) return sortOrder.value === 'asc' ? 1 : -1;
        return 0;
      });
      
      return sorted;
    });

    // Navigation methods
    const navigateToPath = async (path) => {
      currentPath.value = path;
      selectedPath.value = path;
      await refreshFiles();
    };

    const getPathUpTo = (index) => {
      const parts = pathParts.value.slice(0, index + 1);
      return '/' + parts.join('/');
    };

    // Tree view methods
    const toggleView = () => {
      viewMode.value = viewMode.value === 'tree' ? 'list' : 'tree';
      if (viewMode.value === 'tree') {
        buildDirectoryTree();
      }
    };

    const toggleNode = async (node) => {
      if (!node.is_dir) return;
      
      node.expanded = !node.expanded;
      selectedPath.value = node.path;
      
      if (node.expanded && !node.loaded) {
        await loadDirectoryContents(node);
      }
      
      // Update files for the selected directory
      currentPath.value = node.path;
      await refreshFiles();
    };

    const buildDirectoryTree = async () => {
      try {
        const data = await apiClient.get('/api/files/tree');
        directoryTree.value = data.tree || [];
      } catch (error) {
        console.warn('Could not load directory tree, using fallback:', error);
        directoryTree.value = [
          {
            name: 'home',
            path: '/home',
            is_dir: true,
            level: 0,
            expanded: false,
            loaded: false
          }
        ];
      }
    };

    const loadDirectoryContents = async (node) => {
      try {
        const data = await apiClient.get(`/api/files/list?path=${encodeURIComponent(node.path)}`);
        node.children = data.files || [];
        node.loaded = true;
      } catch (error) {
        console.warn('Could not load directory contents:', error);
        node.children = [];
      }
    };

    const expandAll = () => {
      const expandRecursive = (nodes) => {
        nodes.forEach(node => {
          if (node.is_dir) {
            node.expanded = true;
            if (node.children) {
              expandRecursive(node.children);
            }
          }
        });
      };
      expandRecursive(directoryTree.value);
    };

    const collapseAll = () => {
      const collapseRecursive = (nodes) => {
        nodes.forEach(node => {
          if (node.is_dir) {
            node.expanded = false;
            if (node.children) {
              collapseRecursive(node.children);
            }
          }
        });
      };
      collapseRecursive(directoryTree.value);
    };

    // Sorting methods
    const sortBy = (field) => {
      if (sortField.value === field) {
        sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc';
      } else {
        sortField.value = field;
        sortOrder.value = 'asc';
      }
    };

    const getSortIcon = (field) => {
      if (sortField.value !== field) return 'fas fa-sort';
      return sortOrder.value === 'asc' ? 'fas fa-sort-up' : 'fas fa-sort-down';
    };

    // File operations
    const refreshFiles = async () => {
      try {
        const data = await apiClient.get(`/api/files/list?path=${encodeURIComponent(currentPath.value)}`);
        files.value = data.files || [];
      } catch (error) {
        console.warn('Backend not available - using demo files:', error.message);
        files.value = [
          { 
            name: 'sample.txt', 
            path: '/sample.txt',
            size: 1024, 
            is_dir: false, 
            last_modified: Date.now() / 1000
          },
          { 
            name: 'documents', 
            path: '/documents',
            size: 0, 
            is_dir: true, 
            last_modified: Date.now() / 1000
          },
          { 
            name: 'images', 
            path: '/images',
            size: 0, 
            is_dir: true, 
            last_modified: Date.now() / 1000
          }
        ];
      }
    };

    const uploadFile = () => {
      if (fileInput.value) {
        fileInput.value.click();
      } else {
        const input = document.createElement('input');
        input.type = 'file';
        input.multiple = true;
        input.onchange = handleFileSelected;
        input.click();
      }
    };

    const handleFileSelected = async (event) => {
      const selectedFiles = Array.from(event.target.files);
      for (const file of selectedFiles) {
        await processFileUpload(file);
      }
      // Clear the input for next upload
      if (fileInput.value) {
        fileInput.value.value = '';
      }
      if (visibleFileInput.value) {
        visibleFileInput.value.value = '';
      }
    };

    const processFileUpload = async (file) => {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('path', currentPath.value);

      try {
        const userStore = useUserStore();
        const headers = {
          'X-User-Role': userStore.currentUser?.role || 'user'
        };

        const response = await fetch(`${apiClient.baseUrl}/api/files/upload`, {
          method: 'POST',
          headers: headers,
          body: formData
        });

        if (response.ok) {
          alert(`File ${file.name} uploaded successfully.`);
          refreshFiles();
        } else {
          const errorText = await response.text();
          console.error('Upload failed:', response.status, errorText);
          if (response.status === 403) {
            alert('Permission denied. File upload requires admin privileges.');
          } else if (response.status === 413) {
            alert('File too large. Maximum size is 50MB.');
          } else if (response.status === 400) {
            alert('Invalid file type or file not allowed.');
          } else {
            alert(`Failed to upload file: ${response.status} ${response.statusText}`);
          }
        }
      } catch (error) {
        console.error('Error uploading file:', error);
        alert('Error uploading file. Please check your connection and try again.');
      }
    };

    const viewFile = async (file) => {
      try {
        const extension = file.name.split('.').pop()?.toLowerCase() || '';
        const fileType = determineFileType(extension);
        const fileUrl = `${apiClient.baseUrl}/api/files/view/${encodeURIComponent(file.path || file.name)}`;

        if (fileType === 'html') {
          const response = await fetch(fileUrl);
          if (response.ok) {
            const htmlContent = await response.text();
            const blob = new Blob([htmlContent], { type: 'text/html' });
            const blobUrl = URL.createObjectURL(blob);

            previewFile.value = {
              name: file.name,
              type: 'html',
              url: blobUrl,
              size: file.size,
              fileType: extension.toUpperCase()
            };
          } else {
            throw new Error('Failed to load HTML file');
          }
        } else if (fileType === 'text' || fileType === 'json') {
          const response = await fetch(fileUrl);
          if (response.ok) {
            const textContent = await response.text();
            previewFile.value = {
              name: file.name,
              type: fileType,
              content: textContent,
              size: file.size,
              fileType: extension.toUpperCase()
            };
          } else {
            throw new Error('Failed to load text file');
          }
        } else if (fileType === 'image') {
          previewFile.value = {
            name: file.name,
            type: 'image',
            url: fileUrl,
            size: file.size,
            fileType: extension.toUpperCase()
          };
        } else if (fileType === 'pdf') {
          previewFile.value = {
            name: file.name,
            type: 'pdf',
            url: fileUrl,
            size: file.size,
            fileType: extension.toUpperCase()
          };
        } else {
          previewFile.value = {
            name: file.name,
            type: 'other',
            url: fileUrl,
            size: file.size,
            fileType: extension.toUpperCase()
          };
        }

        showPreview.value = true;

      } catch (error) {
        console.error('Error viewing file:', error);
        alert(`Error loading ${file.name}: ${error.message}`);
      }
    };

    const deleteFile = async (file) => {
      if (!confirm(`Are you sure you want to delete ${file.name}?`)) {
        return;
      }

      try {
        const response = await fetch(`${apiClient.baseUrl}/api/files/delete`, {
          method: 'DELETE',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ path: file.path })
        });
        
        if (response.ok) {
          alert(`Deleted ${file.name}.`);
          refreshFiles();
        } else {
          alert(`File ${file.name} would be deleted (API integration pending).`);
          refreshFiles();
        }
      } catch (error) {
        console.warn('Backend not available - simulating delete:', error.message);
        alert(`File ${file.name} would be deleted (API integration pending).`);
        refreshFiles();
      }
    };

    // Utility methods
    const getFileIcon = (file) => {
      if (file.is_dir) return 'fas fa-folder text-yellow-600';
      
      const extension = file.name.split('.').pop()?.toLowerCase() || '';
      
      // Image files
      if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp'].includes(extension)) {
        return 'fas fa-image text-green-500';
      }
      
      // Code files
      if (['js', 'ts', 'jsx', 'tsx', 'vue', 'py', 'java', 'cpp', 'c', 'php', 'rb', 'go', 'rs'].includes(extension)) {
        return 'fas fa-code text-blue-500';
      }
      
      // Document files
      if (['pdf', 'doc', 'docx', 'txt', 'md'].includes(extension)) {
        return 'fas fa-file-alt text-red-500';
      }
      
      // Archive files
      if (['zip', 'rar', '7z', 'tar', 'gz'].includes(extension)) {
        return 'fas fa-file-archive text-purple-500';
      }
      
      return 'fas fa-file text-gray-500';
    };

    const getFileType = (filename) => {
      const extension = filename.split('.').pop()?.toLowerCase() || '';
      
      if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp'].includes(extension)) {
        return 'Image';
      }
      if (['js', 'ts', 'jsx', 'tsx', 'vue', 'py', 'java', 'cpp', 'c', 'php', 'rb', 'go', 'rs'].includes(extension)) {
        return 'Code';
      }
      if (['pdf', 'doc', 'docx'].includes(extension)) {
        return 'Document';
      }
      if (['txt', 'md'].includes(extension)) {
        return 'Text';
      }
      if (['zip', 'rar', '7z', 'tar', 'gz'].includes(extension)) {
        return 'Archive';
      }
      
      return extension.toUpperCase() || 'File';
    };

    const determineFileType = (extension) => {
      const imageTypes = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp'];
      const textTypes = ['txt', 'md', 'js', 'css', 'py', 'java', 'cpp', 'c', 'php', 'rb', 'go', 'rs', 'vue', 'jsx', 'tsx', 'yaml', 'yml', 'xml', 'csv'];
      const jsonTypes = ['json'];
      const htmlTypes = ['html', 'htm'];
      const pdfTypes = ['pdf'];

      if (htmlTypes.includes(extension)) return 'html';
      if (imageTypes.includes(extension)) return 'image';
      if (textTypes.includes(extension)) return 'text';
      if (jsonTypes.includes(extension)) return 'json';
      if (pdfTypes.includes(extension)) return 'pdf';
      return 'other';
    };

    const closePreview = () => {
      showPreview.value = false;
      if (previewFile.value?.url && previewFile.value.url.startsWith('blob:')) {
        URL.revokeObjectURL(previewFile.value.url);
      }
      previewFile.value = null;
    };

    const formatJson = (content) => {
      try {
        return JSON.stringify(JSON.parse(content), null, 2);
      } catch {
        return content;
      }
    };

    const downloadPreviewFile = async () => {
      if (previewFile.value?.url) {
        const link = document.createElement('a');
        link.href = previewFile.value.url;
        link.download = previewFile.value.name;
        link.click();
      }
    };

    const formatSize = (bytes) => {
      if (bytes < 1024) return bytes + ' B';
      if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
      return (bytes / 1048576).toFixed(1) + ' MB';
    };

    const formatDate = (timestamp) => {
      const date = new Date(timestamp * 1000);
      return date.toLocaleString();
    };

    // Initialize
    onMounted(() => {
      refreshFiles();
      if (viewMode.value === 'tree') {
        buildDirectoryTree();
      }
    });

    return {
      files,
      directoryTree,
      currentPath,
      selectedPath,
      viewMode,
      sortField,
      sortOrder,
      showPreview,
      previewFile,
      fileInput,
      visibleFileInput,
      pathParts,
      sortedFiles,
      navigateToPath,
      getPathUpTo,
      toggleView,
      toggleNode,
      buildDirectoryTree,
      expandAll,
      collapseAll,
      sortBy,
      getSortIcon,
      refreshFiles,
      uploadFile,
      handleFileSelected,
      processFileUpload,
      viewFile,
      deleteFile,
      getFileIcon,
      getFileType,
      closePreview,
      formatJson,
      downloadPreviewFile,
      formatSize,
      formatDate
    };
  }
};
</script>

<style scoped>
.file-browser {
  display: flex;
  flex-direction: column;
  height: 100%;
  background-color: #f8fafc;
  border-radius: 8px;
  overflow: hidden;
}

.file-browser-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.5rem;
  background-color: white;
  border-bottom: 1px solid #e5e7eb;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.file-browser-header h2 {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
  color: #1f2937;
}

.file-actions {
  display: flex;
  gap: 0.75rem;
}

.file-actions button {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background-color: #3b82f6;
  color: white;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 0.875rem;
  font-weight: 500;
}

.file-actions button:hover {
  background-color: #2563eb;
  transform: translateY(-1px);
}

.path-navigation {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1.5rem;
  background-color: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
}

.breadcrumb {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.875rem;
  color: #6b7280;
}

.breadcrumb-item {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.breadcrumb-item .clickable {
  cursor: pointer;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  transition: background-color 0.2s ease;
}

.breadcrumb-item .clickable:hover {
  background-color: #e5e7eb;
  color: #1f2937;
}

.breadcrumb-separator {
  margin: 0 0.25rem;
  color: #9ca3af;
}

.path-input {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.path-field {
  padding: 0.5rem;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  font-size: 0.875rem;
  min-width: 200px;
}

.path-go-btn {
  padding: 0.5rem;
  background-color: #6b7280;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.path-go-btn:hover {
  background-color: #4b5563;
}

.file-upload-section {
  margin: 1rem 1.5rem;
  padding: 1rem;
  border: 2px dashed #d1d5db;
  border-radius: 6px;
  background-color: #f9fafb;
  transition: all 0.3s ease;
}

.file-upload-section:hover {
  border-color: #3b82f6;
  background-color: #eff6ff;
}

.file-input-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: #6b7280;
  margin-bottom: 0.5rem;
  text-align: center;
  width: 100%;
  justify-content: center;
}

.visible-file-input {
  width: 100%;
  padding: 0.5rem;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  background-color: white;
  cursor: pointer;
  transition: border-color 0.3s ease;
}

.visible-file-input:hover {
  border-color: #3b82f6;
}

.file-content-container {
  flex: 1;
  display: flex;
  overflow: hidden;
}

/* Tree View Styles */
.tree-view {
  display: flex;
  flex: 1;
}

.tree-panel {
  width: 300px;
  background-color: white;
  border-right: 1px solid #e5e7eb;
  display: flex;
  flex-direction: column;
}

.tree-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  border-bottom: 1px solid #e5e7eb;
  background-color: #f9fafb;
}

.tree-header h3 {
  margin: 0;
  font-size: 0.875rem;
  font-weight: 600;
  color: #374151;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.tree-controls {
  display: flex;
  gap: 0.25rem;
}

.tree-controls button {
  padding: 0.25rem;
  background: none;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s ease;
  color: #6b7280;
}

.tree-controls button:hover {
  background-color: #f3f4f6;
  color: #374151;
}

.tree-content {
  flex: 1;
  overflow-y: auto;
  padding: 0.5rem 0;
}

.tree-node {
  user-select: none;
}

.tree-node-content {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0.75rem;
  cursor: pointer;
  transition: background-color 0.2s ease;
  font-size: 0.875rem;
}

.tree-node-content:hover {
  background-color: #f3f4f6;
}

.tree-node.selected .tree-node-content {
  background-color: #dbeafe;
  color: #1e40af;
}

.tree-toggle {
  width: 12px;
  color: #6b7280;
}

.tree-icon {
  width: 16px;
}

.tree-label {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Files Panel */
.files-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  background-color: white;
}

.files-header {
  padding: 1rem 1.5rem;
  border-bottom: 1px solid #e5e7eb;
  background-color: #f9fafb;
}

.files-header h3 {
  margin: 0;
  font-size: 0.875rem;
  font-weight: 600;
  color: #374151;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

/* Table Styles */
.file-list-container {
  flex: 1;
  overflow-y: auto;
}

.file-table {
  width: 100%;
  border-collapse: collapse;
}

.file-table th {
  background-color: #f9fafb;
  padding: 0.75rem 1rem;
  text-align: left;
  border-bottom: 1px solid #e5e7eb;
  color: #374151;
  font-weight: 600;
  font-size: 0.875rem;
}

.file-table th.sortable {
  cursor: pointer;
  user-select: none;
  transition: background-color 0.2s ease;
}

.file-table th.sortable:hover {
  background-color: #f3f4f6;
}

.sort-icon {
  margin-left: 0.25rem;
  color: #6b7280;
}

.file-table td {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #f3f4f6;
  font-size: 0.875rem;
  color: #374151;
}

.file-table tr:hover {
  background-color: #f8fafc;
}

.file-name-cell {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.file-icon {
  width: 16px;
}

.file-name {
  font-weight: 500;
}

.file-name.clickable {
  cursor: pointer;
  color: #3b82f6;
}

.file-name.clickable:hover {
  text-decoration: underline;
}

.action-buttons {
  display: flex;
  gap: 0.25rem;
}

.action-btn {
  padding: 0.375rem;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  background-color: white;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 0.75rem;
}

.action-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.view-btn {
  color: #3b82f6;
  border-color: #3b82f6;
}

.view-btn:hover {
  background-color: #eff6ff;
}

.open-btn {
  color: #059669;
  border-color: #059669;
}

.open-btn:hover {
  background-color: #ecfdf5;
}

.delete-btn {
  color: #dc2626;
  border-color: #dc2626;
}

.delete-btn:hover {
  background-color: #fef2f2;
}

.no-files {
  text-align: center;
  color: #9ca3af;
  font-style: italic;
  padding: 2rem;
}

.no-files i {
  margin-right: 0.5rem;
  font-size: 1.25rem;
}

.clickable {
  cursor: pointer;
}

/* List View */
.list-view {
  flex: 1;
  background-color: white;
  margin: 1rem 1.5rem;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

/* Modal Styles (keeping original) */
.file-preview-modal {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.8);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 9999;
}

.modal-content {
  background: white;
  border-radius: 8px;
  max-width: 90vw;
  max-height: 90vh;
  width: 800px;
  height: 600px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
}

.modal-header {
  padding: 16px 24px;
  border-bottom: 1px solid #e9ecef;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: #f8f9fa;
}

.modal-header h3 {
  margin: 0;
  font-size: 18px;
  color: #333;
  word-break: break-all;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  color: #666;
  cursor: pointer;
  padding: 0;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.close-btn:hover {
  background-color: #e9ecef;
  color: #333;
}

.modal-body {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* Preview styles (keeping original) */
.html-preview,
.pdf-preview {
  flex: 1;
  display: flex;
}

.html-frame,
.pdf-frame {
  width: 100%;
  height: 100%;
  border: none;
}

.image-preview {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 20px;
  background-color: #f8f9fa;
}

.preview-image {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.text-preview,
.json-preview {
  flex: 1;
  overflow: auto;
  padding: 20px;
}

.text-preview pre,
.json-preview pre {
  margin: 0;
  font-family: 'Courier New', Courier, monospace;
  font-size: 14px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  background-color: #f8f9fa;
  padding: 16px;
  border-radius: 4px;
  border: 1px solid #e9ecef;
}

.json-preview pre {
  background-color: #f1f8ff;
  border-color: #c8e1ff;
}

.file-info {
  flex: 1;
  padding: 40px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
  background-color: #f8f9fa;
}

.file-info p {
  margin: 8px 0;
  font-size: 16px;
  color: #333;
}

.file-info p strong {
  color: #007bff;
}

.download-btn {
  margin-top: 20px;
  padding: 10px 20px;
  background-color: #007bff;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 16px;
  transition: background-color 0.2s;
}

.download-btn:hover {
  background-color: #0056b3;
}
</style>