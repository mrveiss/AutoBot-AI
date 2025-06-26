// old_dashboard/index.js - Non-module version for old dashboard

// Global variables for redirection
let redirectTimer;
let countdownInterval;

// Get context window content 
function getContext() {
  return fetch('/ctx_window_get')
    .then(response => response.json())
    .then(data => {
      return {
        content: data.content,
        tokens: data.tokens
      };
    })
    .catch(error => {
      console.error('Error fetching context window:', error);
      return {
        content: "Error fetching context window",
        tokens: 0
      };
    });
}

// File browser modal component
const fileBrowserModal = {
  // Method to initialize the file browser modal
  init: function() {
    console.log('Initializing file browser modal');
    this.setupEventListeners();
    return this;
  },

  // Show the file browser modal dialog
  show: function(options = {}) {
    const modal = document.getElementById('file-browser-modal');
    if (!modal) {
      console.error('File browser modal element not found');
      return;
    }
    
    // Set title if provided
    if (options.title) {
      const titleEl = modal.querySelector('.modal-title');
      if (titleEl) titleEl.textContent = options.title;
    }
    
    // Fetch and display files
    this.loadFiles(options.path || '');
    
    // Display the modal
    modal.classList.add('show');
    modal.style.display = 'block';
  },
  
  // Hide the file browser modal
  hide: function() {
    const modal = document.getElementById('file-browser-modal');
    if (modal) {
      modal.classList.remove('show');
      modal.style.display = 'none';
    }
  },
  
  // Load files from the specified path
  loadFiles: function(path = '') {
    const fileListContainer = document.querySelector('#file-browser-files');
    if (!fileListContainer) {
      console.error('File list container not found');
      return;
    }
    
    // Show loading indicator
    fileListContainer.innerHTML = '<div class="text-center"><div class="spinner-border" role="status"><span class="visually-hidden">Loading...</span></div></div>';
    
    // Fetch files from API
    fetch(`/api/files?path=${encodeURIComponent(path)}`)
      .then(response => response.json())
      .then(data => {
        if (data.files && Array.isArray(data.files)) {
          this.renderFileList(data.files, fileListContainer);
        } else {
          fileListContainer.innerHTML = '<div class="alert alert-warning">No files found</div>';
        }
      })
      .catch(error => {
        console.error('Error loading files:', error);
        fileListContainer.innerHTML = '<div class="alert alert-danger">Error loading files</div>';
      });
  },
  
  // Render the file list in the container
  renderFileList: function(files, container) {
    if (files.length === 0) {
      container.innerHTML = '<div class="alert alert-info">Directory is empty</div>';
      return;
    }
    
    // Create file list HTML
    const html = files.map(file => {
      const icon = file.is_dir ? 'folder' : 'file';
      const size = file.is_dir ? '-' : this.formatFileSize(file.size);
      const date = new Date(file.last_modified * 1000).toLocaleString();
      
      return `
        <div class="file-item" data-path="${file.path}" data-is-dir="${file.is_dir}">
          <div class="file-icon"><i class="fas fa-${icon}"></i></div>
          <div class="file-name">${file.name}</div>
          <div class="file-size">${size}</div>
          <div class="file-date">${date}</div>
          <div class="file-actions">
            ${file.is_dir ? '<button class="btn btn-sm btn-primary open-dir">Open</button>' : 
             '<button class="btn btn-sm btn-secondary select-file">Select</button>'}
          </div>
        </div>
      `;
    }).join('');
    
    container.innerHTML = html;
    this.setupFileListEventListeners();
  },
  
  // Format file size into human-readable format
  formatFileSize: function(bytes) {
    if (bytes === 0 || bytes === null) return '0 B';
    
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  },
  
  // Set up event listeners for the file browser
  setupEventListeners: function() {
    // Close button click
    document.querySelectorAll('.file-browser-close').forEach(el => {
      el.addEventListener('click', () => this.hide());
    });
    
    // Navigate up button click
    const upButton = document.querySelector('#file-browser-up');
    if (upButton) {
      upButton.addEventListener('click', () => {
        const currentPath = document.querySelector('#file-browser-path').value;
        const parentPath = this.getParentPath(currentPath);
        this.loadFiles(parentPath);
      });
    }
  },
  
  // Set up event listeners for the file list items
  setupFileListEventListeners: function() {
    // Open directory button click
    document.querySelectorAll('.open-dir').forEach(el => {
      el.addEventListener('click', (e) => {
        const fileItem = e.target.closest('.file-item');
        const path = fileItem.dataset.path;
        this.loadFiles(path);
      });
    });
    
    // Select file button click
    document.querySelectorAll('.select-file').forEach(el => {
      el.addEventListener('click', (e) => {
        const fileItem = e.target.closest('.file-item');
        const path = fileItem.dataset.path;
        const name = fileItem.querySelector('.file-name').textContent;
        
        if (this.onFileSelected) {
          this.onFileSelected({
            path: path,
            name: name
          });
        }
        
        this.hide();
      });
    });
  },
  
  // Get parent directory path
  getParentPath: function(path) {
    if (!path || path === '') return '';
    
    const parts = path.split('/');
    parts.pop();
    return parts.join('/');
  },
  
  // Set callback for when a file is selected
  onFileSelected: null
};

// Initialize components when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
  console.log('Old dashboard initialized');
  
  // Initialize file browser modal
  if (typeof fileBrowserModal !== 'undefined') {
    fileBrowserModal.init();
  }
  
  // Add redirect to new dashboard with a button
  const dashboardEl = document.getElementById('dashboard-container');
  if (dashboardEl) {
    const redirectBtn = document.createElement('div');
    redirectBtn.className = 'redirect-banner';
    redirectBtn.innerHTML = `
      <div class="alert alert-primary" role="alert">
        <h4 class="alert-heading">New Dashboard Available!</h4>
        <p>We've upgraded to a new and improved dashboard with more features.</p>
        <hr>
        <a href="/" class="btn btn-primary">Go to New Dashboard</a>
        <button class="btn btn-secondary ms-2" onclick="window.cancelRedirect()">Stay Here</button>
      </div>
    `;
    const placeholder = dashboardEl.querySelector('.redirect-banner-placeholder');
    if (placeholder) {
      placeholder.replaceWith(redirectBtn);
    } else {
      dashboardEl.prepend(redirectBtn);
    }
  }
  
  // Set up redirection timer (10 seconds)
  redirectTimer = setTimeout(() => {
    window.location.href = '/';
  }, 10000);
  
  // Display countdown
  let countdown = 10;
  const countdownContainer = document.querySelector('.countdown-timer');
  if (countdownContainer) {
    countdownContainer.textContent = `Redirecting to new dashboard in ${countdown} seconds...`;

    countdownInterval = setInterval(() => {
      countdown--;
      if (countdown <= 0) {
        clearInterval(countdownInterval);
      } else {
        countdownContainer.textContent = `Redirecting to new dashboard in ${countdown} seconds...`;
      }
    }, 1000);
  }
});

// Allow users to cancel automatic redirect
window.cancelRedirect = function() {
  clearTimeout(redirectTimer);
  clearInterval(countdownInterval);
  
  const countdownEl = document.querySelector('.countdown-timer');
  if (countdownEl) {
    countdownEl.innerHTML = 'Redirect canceled';
    setTimeout(() => {
      countdownEl.style.display = 'none';
    }, 2000);
  }
  
  // Show message
  const messageEl = document.createElement('div');
  messageEl.className = 'alert alert-info mt-3';
  messageEl.style.position = 'fixed';
  messageEl.style.bottom = '20px';
  messageEl.style.right = '20px';
  messageEl.style.maxWidth = '300px';
  messageEl.style.zIndex = '1000';
  messageEl.innerHTML = 'Automatic redirect canceled. You can still use the button above to go to the new dashboard.';
  document.body.appendChild(messageEl);
  
  // Remove after 5 seconds
  setTimeout(() => {
    messageEl.remove();
  }, 5000);
};

// Make these functions accessible globally
window.getContext = getContext;
window.fileBrowserModal = fileBrowserModal;
