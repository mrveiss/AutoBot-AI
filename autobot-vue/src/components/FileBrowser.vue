<template>
  <div class="file-browser">
    <h2>File Browser</h2>
    <div class="file-actions">
      <button @click="refreshFiles">Refresh</button>
      <button @click="uploadFile">Upload File</button>
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

    const refreshFiles = async () => {
      try {
        console.log('Refreshing file list');
        const response = await fetch('/api/files');
        if (response.ok) {
          files.value = await response.json();
        } else {
          console.error('Failed to fetch files:', response.statusText);
          alert('Failed to refresh file list. Backend integration pending.');
        }
      } catch (error) {
        console.error('Error fetching files:', error);
        alert('Error refreshing file list. Backend integration pending.');
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
            const response = await fetch('/api/files/upload', {
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
        const response = await fetch(`/api/files/view?path=${encodeURIComponent(file.path)}`);
        if (response.ok) {
          const content = await response.text();
          alert(`Content of ${file.name}:\n${content.substring(0, 200)}...`);
        } else {
          alert(`Failed to view ${file.name}. Backend integration pending.`);
        }
      } catch (error) {
        console.error('Error viewing file:', error);
        alert(`Error viewing ${file.name}. Backend integration pending.`);
      }
    };

    const deleteFile = async (file) => {
      try {
        console.log('Deleting file:', file.name);
        const response = await fetch(`/api/files/delete?path=${encodeURIComponent(file.path)}`, {
          method: 'DELETE'
        });
        if (response.ok) {
          alert(`Deleted ${file.name}.`);
          refreshFiles();
        } else {
          alert(`Failed to delete ${file.name}. Backend integration pending.`);
        }
      } catch (error) {
        console.error('Error deleting file:', error);
        alert(`Error deleting ${file.name}. Backend integration pending.`);
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
      refreshFiles,
      uploadFile,
      viewFile,
      deleteFile,
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
</style>
