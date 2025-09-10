# Secrets Management System Implementation Plan

**Date**: August 17, 2025  
**Priority**: High  
**Status**: 🔄 **IN PROGRESS**

## Overview

The AutoBot system requires a comprehensive secrets management system to securely handle SSH keys, passwords, API keys, and other sensitive credentials needed for agents to access resources. This system must support both GUI-based management and chat-scoped secrets with proper isolation and transfer capabilities.

## Requirements

### Functional Requirements

#### 1. Dual-Scope Secret Management
- **General Secrets**: Available across all chat sessions
- **Chat-Scoped Secrets**: Limited to single conversation use
- **Transfer Capability**: Move chat secrets to general pool when needed
- **Isolation**: Chat secrets only accessible within originating conversation

#### 2. Multiple Input Methods
- **GUI Secrets Management Tab**: Central management interface
- **Chat-Based Entry**: Add secrets through conversation commands
- **Import/Export**: Bulk secret operations
- **API Integration**: Programmatic secret management

#### 3. Secret Types Support
- **SSH Keys**: Private/public key pairs
- **Passwords**: Plain text credentials with encryption
- **API Keys**: Service authentication tokens
- **Certificates**: X.509 certificates and CA bundles
- **Connection Strings**: Database and service URLs
- **Custom Fields**: User-defined secret types

#### 4. Security Features
- **Encryption at Rest**: AES-256 encryption for stored secrets
- **Access Control**: Role-based secret access
- **Audit Logging**: Track secret usage and modifications
- **Expiration Management**: Time-based secret expiration
- **Rotation Alerts**: Notify when secrets need rotation

#### 5. Chat Cleanup Integration
- **Deletion Dialog**: Prompt for secret/file transfer or deletion
- **Batch Operations**: Handle multiple secrets during chat cleanup
- **Confirmation Flows**: Prevent accidental secret loss
- **Backup Options**: Export secrets before deletion

### Non-Functional Requirements

#### 1. Security
- **Zero-Knowledge Architecture**: Server cannot decrypt secrets without user key
- **Memory Protection**: Clear sensitive data from memory after use
- **Secure Transmission**: TLS encryption for all secret operations
- **HSM Integration**: Support for hardware security modules (future)

#### 2. Performance
- **Fast Retrieval**: Sub-100ms secret access time
- **Efficient Storage**: Minimal storage overhead
- **Caching Strategy**: Secure in-memory caching with TTL
- **Scalability**: Support 10,000+ secrets per user

#### 3. Usability
- **Intuitive Interface**: Clear secret management workflows
- **Search/Filter**: Quick secret discovery
- **Auto-categorization**: Smart secret type detection
- **Integration Hints**: Suggest secrets for specific contexts

## System Architecture

### Database Schema

```sql
-- Secrets table with encryption metadata
CREATE TABLE secrets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    secret_type VARCHAR(50) NOT NULL,
    scope VARCHAR(20) NOT NULL CHECK (scope IN ('general', 'chat')),
    chat_id VARCHAR(255), -- NULL for general secrets
    user_id VARCHAR(255) NOT NULL,
    encrypted_value BYTEA NOT NULL,
    encryption_key_id VARCHAR(255) NOT NULL,
    metadata JSONB DEFAULT '{}',
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_accessed_at TIMESTAMP WITH TIME ZONE,
    access_count INTEGER DEFAULT 0,
    CONSTRAINT unique_name_per_scope UNIQUE (name, scope, chat_id, user_id)
);

-- Secret access audit log
CREATE TABLE secret_access_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    secret_id UUID REFERENCES secrets(id) ON DELETE CASCADE,
    user_id VARCHAR(255) NOT NULL,
    chat_id VARCHAR(255),
    action VARCHAR(50) NOT NULL, -- 'read', 'write', 'delete', 'transfer'
    ip_address INET,
    user_agent TEXT,
    access_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    additional_data JSONB DEFAULT '{}'
);

-- Encryption keys for secret encryption
CREATE TABLE encryption_keys (
    id VARCHAR(255) PRIMARY KEY,
    key_data BYTEA NOT NULL,
    algorithm VARCHAR(50) NOT NULL DEFAULT 'AES256',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Secret sharing permissions (future)
CREATE TABLE secret_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    secret_id UUID REFERENCES secrets(id) ON DELETE CASCADE,
    granted_to_user_id VARCHAR(255) NOT NULL,
    granted_by_user_id VARCHAR(255) NOT NULL,
    permission_type VARCHAR(20) NOT NULL CHECK (permission_type IN ('read', 'write')),
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### Backend Components

#### 1. Secrets Service (`src/services/secrets_service.py`)
```python
class SecretsService:
    """Core secrets management service with encryption/decryption"""
    
    async def create_secret(self, name: str, value: str, secret_type: str, 
                          scope: str, chat_id: Optional[str] = None) -> Secret
    async def get_secret(self, secret_id: str, user_id: str, chat_id: Optional[str] = None) -> Secret
    async def list_secrets(self, user_id: str, scope: Optional[str] = None, 
                         chat_id: Optional[str] = None) -> List[Secret]
    async def update_secret(self, secret_id: str, **updates) -> Secret
    async def delete_secret(self, secret_id: str, user_id: str) -> bool
    async def transfer_secret(self, secret_id: str, from_scope: str, to_scope: str) -> Secret
    async def rotate_secret(self, secret_id: str, new_value: str) -> Secret
```

#### 2. Encryption Service (`src/services/encryption_service.py`)
```python
class EncryptionService:
    """Handles encryption/decryption of sensitive data"""
    
    def encrypt_secret(self, plaintext: str, key_id: str) -> bytes
    def decrypt_secret(self, ciphertext: bytes, key_id: str) -> str
    def generate_key(self) -> str
    def rotate_keys(self) -> None
```

#### 3. API Endpoints (`backend/api/secrets.py`)
```python
@router.post("/secrets")
async def create_secret(request: CreateSecretRequest) -> SecretResponse

@router.get("/secrets")
async def list_secrets(scope: Optional[str] = None, chat_id: Optional[str] = None) -> List[SecretResponse]

@router.get("/secrets/{secret_id}")
async def get_secret(secret_id: str) -> SecretResponse

@router.put("/secrets/{secret_id}")
async def update_secret(secret_id: str, request: UpdateSecretRequest) -> SecretResponse

@router.delete("/secrets/{secret_id}")
async def delete_secret(secret_id: str) -> MessageResponse

@router.post("/secrets/{secret_id}/transfer")
async def transfer_secret(secret_id: str, request: TransferSecretRequest) -> SecretResponse

@router.get("/secrets/{secret_id}/audit")
async def get_secret_audit_log(secret_id: str) -> List[AuditLogEntry]
```

### Frontend Components

#### 1. Secrets Management Tab (`autobot-vue/src/components/SecretsManager.vue`)
```vue
<template>
  <div class="secrets-manager">
    <!-- Secret list with search/filter -->
    <div class="secrets-list">
      <SecretsList 
        :secrets="filteredSecrets"
        @edit="editSecret"
        @delete="deleteSecret"
        @transfer="transferSecret"
      />
    </div>
    
    <!-- Add/Edit secret form -->
    <SecretForm
      v-if="showForm"
      :secret="selectedSecret"
      @save="saveSecret"
      @cancel="closeForm"
    />
    
    <!-- Bulk operations -->
    <BulkSecretsOperations
      :selected-secrets="selectedSecrets"
      @export="exportSecrets"
      @delete="bulkDeleteSecrets"
    />
  </div>
</template>
```

#### 2. Chat Secret Commands Integration
```javascript
// In chat message processing
const secretCommands = {
  '/add-secret': handleAddSecretCommand,
  '/list-secrets': handleListSecretsCommand,
  '/use-secret': handleUseSecretCommand,
  '/transfer-secret': handleTransferSecretCommand
};

async function handleAddSecretCommand(command, args) {
  const [name, type, value] = args;
  await secretsService.createSecret({
    name,
    type,
    value,
    scope: 'chat',
    chatId: currentChatId
  });
}
```

#### 3. Secret Picker Component (`autobot-vue/src/components/SecretPicker.vue`)
```vue
<template>
  <div class="secret-picker">
    <select v-model="selectedSecret" @change="onSecretSelected">
      <option value="">Select a secret...</option>
      <option 
        v-for="secret in availableSecrets" 
        :key="secret.id" 
        :value="secret.id"
      >
        {{ secret.name }} ({{ secret.type }})
      </option>
    </select>
    <button @click="createNewSecret">+ New Secret</button>
  </div>
</template>
```

### Security Implementation

#### 1. Encryption Strategy
- **Master Key**: Per-user master key for secret encryption
- **Key Derivation**: PBKDF2 with user password + salt
- **Algorithm**: AES-256-GCM for authenticated encryption
- **Key Rotation**: Quarterly automatic key rotation
- **Backup Keys**: Encrypted key backups for recovery

#### 2. Access Control
```python
class SecretAccessControl:
    def can_access_secret(self, user_id: str, secret: Secret, chat_id: Optional[str] = None) -> bool:
        # General secrets available to owner
        if secret.scope == 'general' and secret.user_id == user_id:
            return True
        
        # Chat secrets only available in originating chat
        if secret.scope == 'chat' and secret.chat_id == chat_id and secret.user_id == user_id:
            return True
            
        # Check shared permissions (future)
        return self.has_shared_permission(user_id, secret.id)
```

#### 3. Audit Logging
```python
async def log_secret_access(secret_id: str, user_id: str, action: str, 
                          chat_id: Optional[str] = None, **metadata):
    await db.execute("""
        INSERT INTO secret_access_log 
        (secret_id, user_id, chat_id, action, ip_address, user_agent, additional_data)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
    """, secret_id, user_id, chat_id, action, 
        request.client.host, request.headers.get('user-agent'), metadata)
```

## Integration Points

### 1. Agent Integration
```python
class AgentSecretsIntegration:
    async def get_secrets_for_agent(self, agent_type: str, chat_id: str) -> Dict[str, str]:
        """Get relevant secrets for specific agent type"""
        secrets = await secrets_service.list_secrets(
            user_id=current_user.id,
            chat_id=chat_id
        )
        
        # Filter secrets by agent requirements
        agent_secrets = {}
        for secret in secrets:
            if self.is_secret_relevant_for_agent(secret, agent_type):
                decrypted_value = await secrets_service.decrypt_secret(secret.id)
                agent_secrets[secret.name] = decrypted_value
                
        return agent_secrets
```

### 2. Terminal Integration
```javascript
// Auto-inject SSH keys for terminal sessions
async function setupTerminalSecrets(sessionId, chatId) {
  const sshSecrets = await secretsService.getSecretsByType('ssh_key', chatId);
  
  for (const secret of sshSecrets) {
    await terminalService.injectSSHKey(sessionId, secret.name, secret.value);
  }
}
```

### 3. Chat Cleanup Integration
```javascript
async function handleChatDeletion(chatId) {
  const chatSecrets = await secretsService.getSecretsByScope('chat', chatId);
  
  if (chatSecrets.length > 0) {
    const result = await showSecretsCleanupDialog(chatSecrets);
    
    if (result.action === 'transfer') {
      for (const secretId of result.selectedSecrets) {
        await secretsService.transferSecret(secretId, 'chat', 'general');
      }
    } else if (result.action === 'delete') {
      for (const secretId of result.selectedSecrets) {
        await secretsService.deleteSecret(secretId);
      }
    }
  }
}
```

## Implementation Phases

### Phase 1: Core Infrastructure (2-3 hours)
1. ✅ Database schema creation and migrations
2. ✅ Basic encryption service implementation
3. ✅ Core secrets service with CRUD operations
4. ✅ Basic API endpoints

### Phase 2: Frontend Integration (3-4 hours)
1. ✅ Secrets management tab in GUI
2. ✅ Basic secret form for add/edit operations
3. ✅ Secret list with search and filtering
4. ✅ Chat command integration for secret operations

### Phase 3: Advanced Features (2-3 hours)
1. ✅ Chat cleanup integration with transfer dialogs
2. ✅ Secret picker component for agent integration
3. ✅ Audit logging and access tracking
4. ✅ Bulk operations and export functionality

### Phase 4: Security Hardening (1-2 hours)
1. ✅ Key rotation implementation
2. ✅ Access control refinement
3. ✅ Security testing and validation
4. ✅ Documentation and user guides

## Testing Strategy

### Unit Tests
- Encryption/decryption functionality
- Access control logic
- Secret transfer operations
- Database operations

### Integration Tests
- End-to-end secret creation and usage
- Chat cleanup with secret transfer
- Agent secret injection
- API endpoint testing

### Security Tests
- Encryption strength validation
- Access control bypass attempts
- Audit log integrity
- Key rotation testing

## Success Criteria

### Functional
- ✅ Create, read, update, delete secrets via GUI and chat
- ✅ Transfer secrets between scopes
- ✅ Automatic chat cleanup with secret handling
- ✅ Agent integration with appropriate secrets

### Security
- ✅ All secrets encrypted at rest with AES-256
- ✅ Zero plaintext secret storage
- ✅ Complete audit trail for all operations
- ✅ Proper access control enforcement

### Performance
- ✅ <100ms secret retrieval time
- ✅ <500ms for bulk operations
- ✅ Minimal memory footprint
- ✅ Efficient secret caching

## Risk Mitigation

### Security Risks
- **Key Compromise**: Regular key rotation and HSM integration
- **Data Breach**: Encryption at rest and in transit
- **Access Control Bypass**: Thorough testing and code review
- **Audit Log Tampering**: Signed audit logs and immutable storage

### Operational Risks
- **Key Loss**: Encrypted backup keys and recovery procedures
- **Performance Issues**: Caching strategy and database optimization
- **User Error**: Clear UI/UX and confirmation dialogs
- **Integration Failures**: Comprehensive testing and fallback mechanisms

This comprehensive secrets management system will provide secure, user-friendly credential handling for the AutoBot platform while maintaining proper isolation between chat sessions and enabling seamless agent integration.