<template>
  <div class="file-browser">
    <h2>File Browser</h2>
    <div class="file-actions">
      <button @click="refreshFiles">Refresh</button>
      <button @click="uploadFile">Upload File</button>
    </div>

    <!-- File Preview Modal -->
    <div v-if="showPreview" class="file-preview-modal" @click="closePreview">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h3>{{ previewFile?.name }}</h3>
          <button class="close-btn" @click="closePreview">&times;</button>
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
            <button @click="downloadPreviewFile" class="download-btn">Download File</button>
          </div>
        </div>
      </div>
    </div>
    <div class="file-list-container">
      <table class="file-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Type</th>
            <th>Size</th>
            <th>Last Modified</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(file, index) in files" :key="index">
            <td>{{ file.name }}</td>
            <td>{{ file.is_dir ? 'Directory' : 'File' }}</td>
            <td>{{ file.is_dir ? '-' : formatSize(file.size) }}</td>
            <td>{{ formatDate(file.last_modified) }}</td>
            <td>
              <button @click="viewFile(file)" v-if="!file.is_dir">View</button>
              <button @click="deleteFile(file)">Delete</button>
            </td>
          </tr>
          <tr v-if="files.length === 0">
            <td colspan="5" class="no-files">No files or directories found.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script>
import { ref } from 'vue';

export default {
  name: 'FileBrowser',
  setup() {
    const files = ref([]);
    const showPreview = ref(false);
    const previewFile = ref(null);

    const refreshFiles = async () => {
      try {
        const response = await fetch('http://localhost:8001/api/files/list');
        if (response.ok) {
          const contentType = response.headers.get('content-type');
          if (contentType && contentType.includes('application/json')) {
            const data = await response.json();
            files.value = data.files || [];
          } else {
            console.warn('API endpoint returned non-JSON response, using mock data');
            // Use mock data when API returns HTML error page
            files.value = [
              { name: 'sample.txt', size: 1024, type: 'file', modified: new Date().toISOString() },
              { name: 'documents', size: 0, type: 'directory', modified: new Date().toISOString() }
            ];
          }
        } else {
          console.error('Failed to fetch files:', response.status, response.statusText);
          // Use mock data when API is not available
          files.value = [
            { name: 'sample.txt', size: 1024, type: 'file', modified: new Date().toISOString() },
            { name: 'documents', size: 0, type: 'directory', modified: new Date().toISOString() }
          ];
        }
      } catch (error) {
        console.error('Error fetching files:', error);
        // Use mock data when there's a network error or JSON parsing fails
        files.value = [
          { name: 'sample.txt', size: 1024, type: 'file', modified: new Date().toISOString() },
          { name: 'documents', size: 0, type: 'directory', modified: new Date().toISOString() }
        ];
      }
    };

    const uploadFile = () => {
      const input = document.createElement('input');
      input.type = 'file';
      input.onchange = async (event) => {
        const file = event.target.files[0];
        if (file) {
          const formData = new FormData();
          formData.append('file', file);
          try {
            const response = await fetch('http://localhost:8001/api/files/upload', {
              method: 'POST',
              body: formData
            });
            if (response.ok) {
              alert(`File ${file.name} uploaded successfully.`);
              refreshFiles();
            } else {
              alert('Failed to upload file. Backend integration pending.');
            }
          } catch (error) {
            console.error('Error uploading file:', error);
            alert('Error uploading file. Backend integration pending.');
          }
        }
      };
      input.click();
    };

    const viewFile = async (file) => {
      try {
        console.log('Viewing file:', file.name);

        // Determine file type from extension
        const extension = file.name.split('.').pop()?.toLowerCase() || '';
        const fileType = determineFileType(extension);

        // Build file URL for preview
        const fileUrl = `http://localhost:8001/api/files/view/${encodeURIComponent(file.path || file.name)}`;

        if (fileType === 'html') {
          // For HTML files, create a blob URL for safe rendering
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
          // For text files, fetch content
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
          // For images, use direct URL
          previewFile.value = {
            name: file.name,
            type: 'image',
            url: fileUrl,
            size: file.size,
            fileType: extension.toUpperCase()
          };
        } else if (fileType === 'pdf') {
          // For PDFs, use direct URL
          previewFile.value = {
            name: file.name,
            type: 'pdf',
            url: fileUrl,
            size: file.size,
            fileType: extension.toUpperCase()
          };
        } else {
          // For other files, show file info
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
      // Clean up blob URLs to prevent memory leaks
      if (previewFile.value?.url && previewFile.value.url.startsWith('blob:')) {
        URL.revokeObjectURL(previewFile.value.url);
      }
      previewFile.value = null;
    };

    const formatJson = (content) => {
      try {
        return JSON.stringify(JSON.parse(content), null, 2);
      } catch {
        return content; // Return as-is if not valid JSON
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

    const deleteFile = async (file) => {
      try {
        console.log('Deleting file:', file.name);
        const response = await fetch('http://localhost:8001/api/files/delete', {
          method: 'DELETE',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ path: file.path })
        });
        if (response.ok) {
          const contentType = response.headers.get('content-type');
          if (contentType && contentType.includes('application/json')) {
            alert(`Deleted ${file.name}.`);
            refreshFiles();
          } else {
            alert(`File ${file.name} would be deleted (API integration pending).`);
            refreshFiles();
          }
        } else {
          alert(`File ${file.name} would be deleted (API integration pending).`);
          refreshFiles();
        }
      } catch (error) {
        console.error('Error deleting file:', error);
        alert(`File ${file.name} would be deleted (API integration pending).`);
        refreshFiles();
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

    // Initial load of files
    refreshFiles();

    return {
      files,
      showPreview,
      previewFile,
      refreshFiles,
      uploadFile,
      viewFile,
      deleteFile,
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
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
  padding: 15px;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.file-browser h2 {
  margin: 0 0 15px 0;
  font-size: 20px;
  color: #007bff;
}

.file-actions {
  display: flex;
  gap: 10px;
  margin-bottom: 15px;
}

.file-actions button {
  background-color: #007bff;
  color: white;
  border: none;
  padding: 8px 15px;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.3s;
}

.file-actions button:hover {
  background-color: #0056b3;
}

.file-list-container {
  flex: 1;
  overflow-y: auto;
  border: 1px solid #e9ecef;
  border-radius: 4px;
}

.file-table {
  width: 100%;
  border-collapse: collapse;
}

.file-table th {
  background-color: #f8f9fa;
  padding: 10px;
  text-align: left;
  border-bottom: 2px solid #dee2e6;
  color: #495057;
}

.file-table td {
  padding: 10px;
  border-bottom: 1px solid #dee2e6;
}

.file-table tr:hover {
  background-color: #f1f1f1;
}

.file-table button {
  background-color: #007bff;
  color: white;
  border: none;
  padding: 5px 10px;
  border-radius: 4px;
  cursor: pointer;
  margin-right: 5px;
  transition: background-color 0.3s;
}

.file-table button:hover {
  background-color: #0056b3;
}

.file-table button:last-child {
  background-color: #dc3545;
}

.file-table button:last-child:hover {
  background-color: #c82333;
}

.no-files {
  text-align: center;
  color: #6c757d;
  font-style: italic;
}

/* File Preview Modal Styles */
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

/* HTML Preview */
.html-preview {
  flex: 1;
  display: flex;
}

.html-frame {
  width: 100%;
  height: 100%;
  border: none;
}

/* Image Preview */
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

/* Text/Code Preview */
.text-preview, .json-preview {
  flex: 1;
  overflow: auto;
  padding: 20px;
}

.text-preview pre, .json-preview pre {
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

/* PDF Preview */
.pdf-preview {
  flex: 1;
  display: flex;
}

.pdf-frame {
  width: 100%;
  height: 100%;
  border: none;
}

/* File Info */
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

/* Responsive Design */
@media (max-width: 768px) {
  .modal-content {
    width: 95vw;
    height: 85vh;
  }

  .modal-header {
    padding: 12px 16px;
  }

  .modal-header h3 {
    font-size: 16px;
  }

  .text-preview, .json-preview {
    padding: 16px;
  }

  .text-preview pre, .json-preview pre {
    font-size: 12px;
    padding: 12px;
  }
}
</style>
