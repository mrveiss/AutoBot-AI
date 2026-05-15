# Stub Functions Remediation Plan

**Date**: 2025-11-09
**Status**: Action Plan Created
**Total Stubs Identified**: 13 distinct implementations
**Estimated Effort**: 3-5 days

---

## Executive Summary

Analysis of the AutoBot Vue frontend identified **13 stub functions** across 3 priority levels. Most critically, several features use `setTimeout()` to simulate async operations instead of implementing real backend integrations, creating a poor user experience and technical debt.

**Key Issue**: Backend API endpoints missing for vectorization, file uploads, and hardware testing.

---

## Priority 1: HIGH PRIORITY (Core Functionality Missing)

### 1.1 Tab Completion - UNIMPLEMENTED ⚠️

**Impact**: Users cannot autocomplete commands/paths in terminal
**Effort**: Medium (2-3 hours)
**Dependencies**: None

**Affected Files**:
- `src/components/Terminal.vue:412`
- `src/components/terminal/TerminalInput.vue:133`

**Current Code**:
```javascript
case 'Tab':
  event.preventDefault()
  // TODO: Implement tab completion
  break
```

**Remediation Steps**:
1. Implement command history tracking
2. Build autocomplete suggestion engine
3. Add path completion for file system navigation
4. Create UI dropdown for suggestions
5. Handle Tab key to cycle through suggestions

**Backend API Needed**:
- `GET /api/terminal/autocomplete?prefix={input}&context={current_dir}`
  - Returns: `{ suggestions: string[], type: 'command' | 'path' | 'file' }`

**Testing**:
- [ ] Tab completes common commands (ls, cd, git, npm)
- [ ] Tab completes file paths
- [ ] Shift+Tab cycles backward through suggestions
- [ ] Works with partial input

---

### 1.2 Edit Host Modal - UNIMPLEMENTED ⚠️

**Impact**: Cannot modify infrastructure host configurations
**Effort**: Low (1-2 hours)
**Dependencies**: None

**Affected Files**:
- `src/views/InfrastructureManager.vue:288`

**Current Code**:
```javascript
async function handleEditHost(host: Host) {
  // TODO: Implement edit modal
  console.log('Edit host:', host)
}
```

**Remediation Steps**:
1. Create `EditHostModal.vue` component
2. Add form fields for host configuration (IP, port, credentials, services)
3. Implement validation (IP format, port range)
4. Call backend API to update host
5. Refresh host list on success
6. Show success/error notifications

**Backend API Needed**:
- `PUT /api/infrastructure/hosts/{host_id}`
  - Body: `{ ip: string, port: number, name: string, services: string[] }`
  - Returns: `{ success: boolean, host: Host }`

**Testing**:
- [ ] Modal opens with pre-filled host data
- [ ] Form validation works (invalid IP/port rejected)
- [ ] Successful edit updates host list
- [ ] Error handling shows user-friendly messages
- [ ] Modal closes on cancel/success

---

### 1.3 Vectorization Backend Hooks - PLACEHOLDER ⚠️⚠️

**Impact**: Knowledge base vectorization inefficient/incomplete
**Effort**: High (4-6 hours backend + 2 hours frontend)
**Dependencies**: **Backend API implementation required**

**Affected Files**:
- `src/composables/useKnowledgeVectorization.ts:220-321`

**Current Issues**:
1. **Individual vectorization** - Uses polling workaround (60s timeout)
2. **Batch vectorization** - Processes sequentially (very slow for multiple docs)

**Current Code (Individual)**:
```javascript
// TODO: Replace with actual backend call when individual vectorization endpoint is available
// Expected endpoint: POST /api/knowledge_base/vectorize_document/{document_id}

// Temporary workaround: Poll status endpoint
const checkInterval = setInterval(async () => {
  const statusResponse = await apiClient.get(`/api/knowledge_base/vectorization/status/${documentId}`)
  // ... polling logic ...
}, 1000)

setTimeout(() => {
  clearInterval(checkInterval)
  throw new Error('Vectorization timeout after 60 seconds')
}, 60000)
```

**Current Code (Batch)**:
```javascript
// TODO: Replace with actual backend call when batch vectorization endpoint is available
// PLACEHOLDER - Replace with actual batch API call
// const response = await apiClient.post('/api/knowledge_base/vectorize_documents', {
//   document_ids: documentIds
// })

// Temporary: Process individually (inefficient)
for (const docId of documentIds) {
  await vectorizeDocument(docId)
}
```

**Backend APIs Needed**:

1. **Individual Vectorization** (POST):
   ```
   POST /api/knowledge_base/vectorize_document/{document_id}
   Response: {
     success: boolean,
     job_id: string,
     status: 'queued' | 'processing' | 'completed' | 'failed',
     progress: number (0-100),
     error?: string
   }
   ```

2. **Batch Vectorization** (POST):
   ```
   POST /api/knowledge_base/vectorize_documents
   Body: { document_ids: string[] }
   Response: {
     success: boolean,
     job_id: string,
     total: number,
     queued: number,
     batch_status: 'queued' | 'processing' | 'completed' | 'failed'
   }
   ```

3. **Vectorization Status** (GET) - Already exists but may need enhancement:
   ```
   GET /api/knowledge_base/vectorization/status/{job_id}
   Response: {
     status: 'queued' | 'processing' | 'completed' | 'failed',
     progress: number,
     total_documents: number,
     completed_documents: number,
     failed_documents: number,
     error?: string
   }
   ```

**Remediation Steps**:

**Backend Work (Python FastAPI)**:
1. Implement `POST /api/knowledge_base/vectorize_document/{document_id}`
   - Queue document for vectorization
   - Return job ID immediately (non-blocking)
   - Use Celery/background task queue
2. Implement `POST /api/knowledge_base/vectorize_documents` (batch)
   - Accept array of document IDs
   - Queue all documents as single batch job
   - Return batch job ID
3. Enhance status endpoint to support job IDs
   - Track job progress in Redis
   - Return real-time progress percentage
4. Add WebSocket support for real-time progress updates (optional)

**Frontend Work (Vue/TypeScript)**:
1. Replace polling workaround with proper API call
2. Use job ID to track progress
3. Implement WebSocket listener for real-time updates (if backend supports)
4. Add proper error handling for failed vectorization
5. Show progress bar with real backend data

**Testing**:
- [ ] Individual document vectorization works
- [ ] Batch vectorization processes all documents
- [ ] Progress updates are accurate
- [ ] Failed documents are reported with errors
- [ ] Timeout handling works (for truly stuck jobs)
- [ ] Concurrent vectorization jobs don't conflict

---

### 1.4 File Upload Simulation - FAKE IMPLEMENTATION ⚠️⚠️

**Impact**: Users see fake upload progress, files may not upload correctly
**Effort**: Medium (3-4 hours)
**Dependencies**: Backend file upload endpoint must exist

**Affected Files**:
- `src/components/chat/ChatInput.vue:560-593`

**Current Code**:
```javascript
const simulateUpload = async (upload: any, file: File) => {
  upload.status = 'Uploading...'

  // Simulate network delay
  await new Promise(resolve => setTimeout(resolve, 100))

  const totalChunks = 10
  for (let i = 1; i <= totalChunks; i++) {
    upload.progress = (i / totalChunks) * 100
    upload.current = Math.floor((i / totalChunks) * file.size)
    upload.status = `Uploading... ${Math.round(upload.progress)}%`

    // Simulate chunk upload time
    await new Promise(resolve => setTimeout(resolve, 500))
  }

  upload.status = 'Complete'
  upload.progress = 100
}
```

**Backend API Needed**:
- `POST /api/conversation-files/upload`
  - Multipart form data with file
  - Returns: `{ success: boolean, file_id: string, filename: string, size: number, url: string }`
- OR use existing endpoint if available (check `/api/conversation-files/` routes)

**Remediation Steps**:
1. Replace `simulateUpload()` with real `uploadFile()` function
2. Use `XMLHttpRequest` or `fetch` with progress events
3. Track real upload progress via `event.loaded / event.total`
4. Handle upload errors (network failure, file too large, etc.)
5. Implement retry mechanism for failed chunks
6. Store uploaded file metadata in attachedFiles array
7. Pass file IDs to backend when sending messages

**Real Implementation**:
```javascript
const uploadFile = async (upload: any, file: File) => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('conversation_id', store.currentSessionId)

  try {
    // Use XMLHttpRequest for progress tracking
    await new Promise<void>((resolve, reject) => {
      const xhr = new XMLHttpRequest()

      xhr.upload.addEventListener('progress', (event) => {
        if (event.lengthComputable) {
          upload.progress = (event.loaded / event.total) * 100
          upload.current = event.loaded
          upload.total = event.total
          upload.status = `Uploading... ${Math.round(upload.progress)}%`
        }
      })

      xhr.addEventListener('load', () => {
        if (xhr.status === 200) {
          const response = JSON.parse(xhr.responseText)
          upload.fileId = response.file_id
          upload.status = 'Complete'
          upload.progress = 100
          resolve()
        } else {
          reject(new Error(`Upload failed: ${xhr.status}`))
        }
      })

      xhr.addEventListener('error', () => {
        reject(new Error('Network error during upload'))
      })

      xhr.open('POST', '/api/conversation-files/upload')
      xhr.send(formData)
    })
  } catch (error) {
    upload.error = error.message
    upload.status = 'Failed'
    throw error
  }
}
```

**Testing**:
- [ ] Real upload progress matches actual transfer
- [ ] Large files (>10MB) upload correctly
- [ ] Failed uploads show error messages
- [ ] Retry works for failed uploads
- [ ] Multiple simultaneous uploads work
- [ ] Uploaded files are attached to messages

---

## Priority 2: MEDIUM PRIORITY (Using Workarounds)

### 2.1 System Reload - SIMULATED ⚠️

**Impact**: Users think system reloaded but nothing happened
**Effort**: Low (1 hour)
**Dependencies**: Backend reload endpoint

**Affected Files**:
- `src/components/chat/ChatSidebar.vue:470-484`

**Current Code**:
```javascript
const reloadSystem = async () => {
  isSystemReloading.value = true
  systemStatus.value = 'Reloading...'

  try {
    // This would call system reload API
    await new Promise(resolve => setTimeout(resolve, 2000)) // Simulate reload
    systemStatus.value = 'Ready'
  } catch (error) {
    systemStatus.value = 'Error'
    console.error('System reload failed:', error)
  } finally {
    isSystemReloading.value = false
  }
}
```

**Backend API Needed**:
- `POST /api/system/reload`
  - Returns: `{ success: boolean, message: string, reloaded_modules: string[] }`

**Remediation**:
```javascript
const reloadSystem = async () => {
  isSystemReloading.value = true
  systemStatus.value = 'Reloading...'

  try {
    const response = await ApiClient.post('/api/system/reload')
    systemStatus.value = response.data.success ? 'Ready' : 'Error'

    if (response.data.reloaded_modules) {
      console.log('Reloaded modules:', response.data.reloaded_modules)
    }
  } catch (error) {
    systemStatus.value = 'Error'
    console.error('System reload failed:', error)
    throw error
  } finally {
    isSystemReloading.value = false
  }
}
```

---

### 2.2 Knowledge Base Population Progress - FAKE PROGRESS ⚠️

**Impact**: Users see fake progress bar, can't track real status
**Effort**: Medium (2-3 hours)
**Dependencies**: Backend real-time progress support

**Affected Files**:
- `src/components/knowledge/KnowledgeBrowser.vue:861-888`

**Current Code**:
```javascript
// Simulate progress updates (since backend doesn't provide real-time progress)
const progressInterval = setInterval(() => {
  if (populationStates.value[categoryId].progress < 90) {
    populationStates.value[categoryId].progress += 10
  }
}, 500)

// Wait for result (assuming it takes some time)
await new Promise(resolve => setTimeout(resolve, 3000))
```

**Backend Enhancement Needed**:
- `POST /api/knowledge_base/populate/{category_id}` should return job ID
- `GET /api/knowledge_base/populate/status/{job_id}` for progress
- OR: WebSocket endpoint for real-time progress: `ws://backend/knowledge/populate/{job_id}`

**Remediation**:
1. Remove fake progress interval
2. Poll status endpoint every 1 second
3. Update progress bar with real backend data
4. OR: Use WebSocket for push-based updates (preferred)
5. Clear interval/close WebSocket when complete

---

### 2.3 Hardware Testing - HARDCODED FAKE RESULTS ⚠️

**Impact**: Users see fake hardware stats, can't diagnose real issues
**Effort**: Medium (2-3 hours backend + 1 hour frontend)
**Dependencies**: **Backend hardware detection APIs required**

**Affected Files**:
- `src/components/settings/BackendSettings.vue:1090-1161`

**Current Code (GPU)**:
```javascript
const testGPU = async () => {
  hardwareStatus.gpu.testing = true
  try {
    // Implement GPU testing logic
    await new Promise(resolve => setTimeout(resolve, 2000))
    hardwareStatus.gpu.status = 'available'
    hardwareStatus.gpu.message = 'GPU acceleration available'
    hardwareStatus.gpu.details = {
      utilization: 15,
      memory: '4GB / 8GB'
    }
  } catch (error) {
    hardwareStatus.gpu.status = 'unavailable'
    hardwareStatus.gpu.message = error.message
  } finally {
    hardwareStatus.gpu.testing = false
  }
}
```

**Backend APIs Needed**:

1. **GPU Status**:
   ```
   GET /api/system/hardware/gpu
   Response: {
     available: boolean,
     device_name: string,
     memory_total: number,
     memory_used: number,
     utilization: number,
     driver_version: string,
     cuda_version?: string
   }
   ```

2. **Memory Status**:
   ```
   GET /api/system/hardware/memory
   Response: {
     total: number,
     available: number,
     used: number,
     percent: number
   }
   ```

3. **CPU Status**:
   ```
   GET /api/system/hardware/cpu
   Response: {
     cores: number,
     threads: number,
     usage_percent: number,
     model: string
   }
   ```

**Remediation**:
Replace fake implementations with real API calls to backend endpoints that use `psutil`, `GPUtil`, or `nvidia-smi` for actual hardware detection.

---

### 2.4 Terminal Modal Async Operations - SIMULATED ⚠️

**Impact**: Modals close before operations complete
**Effort**: Low (1-2 hours)
**Dependencies**: Backend must return completion status

**Affected Files**:
- `src/components/terminal/TerminalModals.vue:370-509`

**Current Issues** (5 functions):
- Reconnect: `setTimeout(resolve, 1000)`
- Execute: `setTimeout(resolve, 1500)`
- Emergency Kill: `setTimeout(resolve, 2000)`
- Workflow Step: `setTimeout(resolve, 1200)`
- Skip: `setTimeout(resolve, 800)`

**Remediation**:
Replace all `setTimeout()` with actual await of backend operation completion:

```javascript
// Before
const reconnectPromise = new Promise<void>((resolve) => {
  emit('reconnect')
  setTimeout(resolve, 1000) // FAKE
})

// After
const reconnectPromise = new Promise<void>(async (resolve, reject) => {
  emit('reconnect')
  try {
    // Wait for actual reconnection confirmation from parent
    // Parent component should emit 'reconnected' event
    const handleReconnected = () => {
      resolve()
      emit('off', 'reconnected', handleReconnected)
    }
    emit('on', 'reconnected', handleReconnected)
  } catch (error) {
    reject(error)
  }
})
```

Or better: Use async/await with proper event listeners or backend API calls.

---

### 2.5 Retry Upload - SIMPLIFIED ⚠️

**Impact**: Cannot retry failed uploads
**Effort**: Low (1 hour)
**Dependencies**: Must track original file references

**Affected Files**:
- `src/components/chat/ChatInput.vue:595-609`

**Current Code**:
```javascript
const retryUpload = async (uploadId: string) => {
  const upload = uploadProgress.value.find(u => u.id === uploadId)
  if (!upload) return

  // Find corresponding file and retry upload
  // This is a simplified retry - in production, you'd need to track the original file
  upload.error = undefined
  upload.progress = 0
  upload.status = 'Retrying...'

  await new Promise(resolve => setTimeout(resolve, 1000))
  upload.status = 'Complete'
  upload.progress = 100
}
```

**Remediation**:
1. Store original `File` object reference in upload state
2. Re-call real upload function with original file
3. Handle errors properly

```javascript
// Add to upload state
interface UploadState {
  id: string
  filename: string
  progress: number
  status: string
  file: File  // ADD THIS - store original file
  fileId?: string
  error?: string
}

// Retry implementation
const retryUpload = async (uploadId: string) => {
  const upload = uploadProgress.value.find(u => u.id === uploadId)
  if (!upload || !upload.file) return

  upload.error = undefined
  upload.progress = 0
  upload.status = 'Retrying...'

  try {
    await uploadFile(upload, upload.file)  // Use real upload
    attachedFiles.value.push(upload.file)
  } catch (error) {
    upload.error = error.message
    upload.status = 'Failed'
  }
}
```

---

## Priority 3: LOW PRIORITY (UX Polish)

### 3.1 MCP Dashboard - MOCK DATA

**Effort**: Medium (2-3 hours backend + 1 hour frontend)
**Files**: `src/components/MCPDashboard.vue:250-274`

**Remediation**: Create real MCP server monitoring endpoints

---

### 3.2 Error Handler Notifications - NOT INTEGRATED

**Effort**: Low (1 hour)
**Files**: `src/utils/ErrorHandler.js:238`

**Remediation**: Integrate with toast notification system (already exists in codebase)

---

### 3.3 Router Health Verification - ALWAYS SUCCEEDS

**Effort**: Low (1 hour)
**Files**: `src/utils/RouterHealthMonitor.js:97-119`

**Remediation**: Implement actual route load verification checks

---

## Implementation Roadmap

### Week 1: High Priority (Core Functionality)

**Day 1-2: Backend APIs**
- [ ] Implement vectorization endpoints (individual + batch)
- [ ] Implement file upload endpoint (or verify existing)
- [ ] Implement hardware detection endpoints (GPU, Memory, CPU)

**Day 3: Frontend Integration**
- [ ] Replace vectorization stubs with real API calls
- [ ] Implement real file upload with progress tracking
- [ ] Implement tab completion

**Day 4: Testing & Polish**
- [ ] Test vectorization with real documents
- [ ] Test file uploads with various sizes
- [ ] Test tab completion edge cases

**Day 5: Edit Host Modal**
- [ ] Create EditHostModal component
- [ ] Implement backend endpoint
- [ ] Integration testing

### Week 2: Medium Priority (Workarounds)

**Day 1: Hardware & System**
- [ ] Integrate real hardware testing
- [ ] Implement system reload
- [ ] Real progress for knowledge base population

**Day 2: Terminal Modals**
- [ ] Fix all 5 terminal modal async operations
- [ ] Implement retry upload properly

**Day 3-5: Testing & Documentation**
- [ ] End-to-end testing of all fixes
- [ ] Update API documentation
- [ ] Update user documentation

### Optional: Week 3 (Low Priority Polish)

---

## Testing Strategy

### Unit Tests
- Each remediated function needs unit tests
- Mock backend responses
- Test error handling

### Integration Tests
- Test full upload workflow
- Test vectorization pipeline
- Test hardware detection

### E2E Tests
- User uploads file → sees real progress → file appears in chat
- User vectorizes document → sees real progress → document searchable
- User tests hardware → sees actual GPU/memory stats

---

## Backend API Specification Summary

### New Endpoints Needed:

1. `POST /api/knowledge_base/vectorize_document/{document_id}`
2. `POST /api/knowledge_base/vectorize_documents` (batch)
3. `GET /api/knowledge_base/vectorization/status/{job_id}` (enhance existing)
4. `GET /api/terminal/autocomplete?prefix={input}&context={dir}`
5. `PUT /api/infrastructure/hosts/{host_id}`
6. `POST /api/system/reload`
7. `GET /api/system/hardware/gpu`
8. `GET /api/system/hardware/memory`
9. `GET /api/system/hardware/cpu`
10. `POST /api/conversation-files/upload` (verify if exists)

### WebSocket Endpoints (Optional but Recommended):
- `ws://backend/knowledge/populate/{job_id}` - Real-time progress
- `ws://backend/vectorization/{job_id}` - Real-time vectorization progress
- `ws://backend/upload/{upload_id}` - Real-time upload progress

---

## Success Criteria

- [ ] No `setTimeout()` used to simulate async operations
- [ ] All TODO/FIXME comments addressed
- [ ] Real progress bars show actual backend progress
- [ ] Hardware stats show real system data
- [ ] Tab completion works in terminal
- [ ] File uploads tracked with real progress
- [ ] All stubs replaced with functional code
- [ ] Test coverage ≥80% for remediated code

---

## Estimated Total Effort

- **Backend Work**: 16-20 hours
- **Frontend Work**: 12-16 hours
- **Testing**: 8-12 hours
- **Total**: 3-5 days (1 senior developer) or 2-3 days (2 developers in parallel)

---

**Priority Order**:
1. Vectorization backend (blocks knowledge base)
2. File upload real implementation (blocks chat attachments)
3. Tab completion (UX improvement)
4. Edit host modal (infrastructure management)
5. Everything else in medium/low priority

**Next Steps**: Begin with backend API implementation for vectorization and file uploads, then integrate on frontend side.
