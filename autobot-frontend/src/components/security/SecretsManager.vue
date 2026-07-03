<template>
  <div class="secrets-manager-n8n">
    <!-- Sidebar Navigation -->
    <aside class="secrets-sidebar">
      <div class="sidebar-header">
        <h3><Icon name="key" /> {{ $t('security.secretsManager.sidebarTitle') }}</h3>
      </div>

      <!-- Search -->
      <div class="sidebar-search">
        <div class="search-wrapper">
          <Icon name="search" />
          <input
            type="text"
            v-model="searchQuery"
            :placeholder="$t('security.secretsManager.searchPlaceholder')"
            class="search-input"
          />
          <button v-if="searchQuery" @click="searchQuery = ''" class="clear-search">
            <Icon name="times" />
          </button>
        </div>
      </div>

      <!-- Category Navigation -->
      <nav class="category-nav">
        <div
          class="category-item"
          :class="{ active: selectedCategory === 'all' }"
          @click="selectCategory('all')"
        >
          <Icon name="layer-group" />
          <span>{{ $t('security.secretsManager.allCredentials') }}</span>
          <span class="count">{{ secrets.length }}</span>
        </div>

        <div class="category-divider">
          <span>{{ $t('security.secretsManager.byType') }}</span>
        </div>

        <div
          v-for="category in credentialCategories"
          :key="category.type"
          class="category-item"
          :class="{ active: selectedCategory === category.type }"
          @click="selectCategory(category.type)"
        >
          <Icon :name="category.icon" />
          <span>{{ category.label }}</span>
          <span class="count">{{ getCategoryCount(category.type) }}</span>
        </div>

        <div class="category-divider">
          <span>{{ $t('security.secretsManager.byScope') }}</span>
        </div>

        <div
          class="category-item"
          :class="{ active: selectedScope === 'general' }"
          @click="selectScope('general')"
        >
          <Icon name="globe" />
          <span>{{ $t('security.secretsManager.scopeGeneral') }}</span>
          <span class="count">{{ stats?.by_scope?.general || 0 }}</span>
        </div>

        <div
          class="category-item"
          :class="{ active: selectedScope === 'chat' }"
          @click="selectScope('chat')"
        >
          <Icon name="comments" />
          <span>{{ $t('security.secretsManager.scopeChat') }}</span>
          <span class="count">{{ stats?.by_scope?.chat || 0 }}</span>
        </div>

        <div class="category-divider" v-if="stats?.expired_count > 0">
          <span>{{ $t('security.secretsManager.scopeAlerts') }}</span>
        </div>

        <div
          v-if="stats?.expired_count > 0"
          class="category-item alert"
          :class="{ active: showExpiredOnly }"
          @click="toggleExpiredFilter"
        >
          <Icon name="exclamation-triangle" />
          <span>{{ $t('security.secretsManager.scopeExpired') }}</span>
          <span class="count alert">{{ stats.expired_count }}</span>
        </div>
      </nav>

      <!-- Quick Actions -->
      <div class="sidebar-actions">
        <button @click="openCreateModal" class="btn-create">
          <Icon name="plus" /> {{ $t('security.secretsManager.newCredential') }}
        </button>
      </div>
    </aside>

    <!-- Main Content -->
    <main class="secrets-content">
      <!-- Header -->
      <header class="content-header">
        <div class="header-left">
          <h2>{{ currentCategoryLabel }}</h2>
          <span class="subtitle">{{ t('security.secretsManager.credentialCount', { count: filteredSecrets.length }, filteredSecrets.length) }}</span>
        </div>
        <div class="header-actions">
          <button @click="loadSecrets" class="btn-icon" :disabled="loading" :title="t('security.secretsManager.refresh')" :aria-label="t('security.secretsManager.refresh')">
            <Icon name="sync-alt" />
          </button>
          <button @click="toggleView" class="btn-icon" :title="viewMode === 'grid' ? t('security.secretsManager.listView') : t('security.secretsManager.gridView')" :aria-label="viewMode === 'grid' ? t('security.secretsManager.listView') : t('security.secretsManager.gridView')">
            <Icon :name="viewMode === 'grid' ? 'list' : 'th'" />
          </button>
        </div>
      </header>

      <!-- Stats Bar -->
      <div class="stats-bar" v-if="stats">
        <div class="stat-item">
          <Icon name="key" />
          <span class="stat-value">{{ stats.total_secrets }}</span>
          <span class="stat-label">{{ $t('security.secretsManager.statsTotal') }}</span>
        </div>
        <div class="stat-item">
          <Icon name="globe" />
          <span class="stat-value">{{ stats.by_scope?.general || 0 }}</span>
          <span class="stat-label">{{ $t('security.secretsManager.scopeGeneral') }}</span>
        </div>
        <div class="stat-item">
          <Icon name="comments" />
          <span class="stat-value">{{ stats.by_scope?.chat || 0 }}</span>
          <span class="stat-label">{{ $t('security.secretsManager.scopeChat') }}</span>
        </div>
        <div class="stat-item warning" v-if="stats.expired_count > 0">
          <Icon name="clock" />
          <span class="stat-value">{{ stats.expired_count }}</span>
          <span class="stat-label">{{ $t('security.secretsManager.scopeExpired') }}</span>
        </div>
      </div>

      <!-- Loading State -->
      <div v-if="loading" class="loading-container">
        <LoadingSpinner size="lg" />
        <p>{{ $t('security.secretsManager.loading') }}</p>
      </div>

      <!-- Empty State -->
      <EmptyState
        v-else-if="filteredSecrets.length === 0"
        :icon="emptyStateIcon"
        :message="emptyStateMessage"
      >
        <template #actions>
          <button @click="openCreateModal()" class="btn-primary">
            <Icon name="plus" /> {{ $t('security.secretsManager.createCredential') }}
          </button>
          <button v-if="hasActiveFilters" @click="clearFilters" class="btn-secondary">
            {{ $t('security.secretsManager.clearFilters') }}
          </button>
        </template>
      </EmptyState>

      <!-- Credentials Grid/List -->
      <div v-else :class="['credentials-container', viewMode]">
        <div
          v-for="secret in filteredSecrets"
          :key="secret.id"
          class="credential-card"
          :class="{ expired: isExpired(secret), selected: selectedSecretId === secret.id }"
          @click="selectSecret(secret)"
        >
          <!-- Card Icon -->
          <div class="card-icon" :style="{ backgroundColor: getTypeColor(secret.type) }">
            <Icon :name="getTypeIcon(secret.type)" />
          </div>

          <!-- Card Content -->
          <div class="card-content">
            <div class="card-header">
              <h4>{{ secret.name }}</h4>
              <div class="card-badges">
                <span class="badge" :class="secret.scope">{{ secret.scope }}</span>
                <!-- Issue #685: Visibility badge -->
                <span v-if="getVisibility(secret)" class="badge visibility" :class="`visibility-${getVisibility(secret)}`">
                  <Icon :name="getVisibilityIcon(secret)" />
                  {{ formatVisibility(secret) }}
                </span>
                <span v-if="isExpired(secret)" class="badge expired">
                  <Icon name="exclamation-triangle" /> {{ $t('security.secretsManager.expired') }}
                </span>
              </div>
            </div>

            <p class="card-description" v-if="secret.description">
              {{ truncate(secret.description, 80) }}
            </p>

            <div class="card-meta">
              <span class="meta-item">
                <Icon name="clock" />
                {{ formatRelativeTime(secret.created_at) }}
              </span>
              <span v-if="secret.expires_at" class="meta-item" :class="{ 'text-warning': isExpiringSoon(secret) }">
                <Icon name="clock" />
                {{ t('security.secretsManager.expiresIn', { time: formatRelativeTime(secret.expires_at) }) }}
              </span>
            </div>

            <div class="card-tags" v-if="secret.tags?.length">
              <span v-for="tag in secret.tags.slice(0, 3)" :key="tag" class="tag">{{ tag }}</span>
              <span v-if="secret.tags.length > 3" class="tag more">+{{ secret.tags.length - 3 }}</span>
            </div>

            <!-- Workflow usage (#1415) -->
            <div class="card-workflow-usage" v-if="getWorkflowUsage(secret).length">
              <span class="usage-label"><Icon name="project-diagram" /> Used by:</span>
              <span v-for="usage in getWorkflowUsage(secret)" :key="usage.template_id" class="usage-tag">
                {{ usage.template_name }}
              </span>
            </div>
          </div>

          <!-- Card Actions -->
          <div class="card-actions">
            <button @click.stop="viewSecret(secret)" class="action-btn" :title="t('security.secretsManager.view')">
              <Icon name="eye" />
            </button>
            <button @click.stop="editSecret(secret)" class="action-btn" :title="t('security.secretsManager.edit')">
              <Icon name="edit" />
            </button>
            <button
              v-if="secret.scope === 'chat'"
              @click.stop="transferSecret(secret)"
              class="action-btn"
              :title="t('security.secretsManager.makeGeneral')"
            >
              <Icon name="share-alt" />
            </button>
            <button @click.stop="confirmDelete(secret)" class="action-btn delete" :title="t('security.secretsManager.delete')">
              <Icon name="trash" />
            </button>
          </div>
        </div>
      </div>

      <!-- Templates Section -->
      <div v-if="showTemplates && filteredSecrets.length === 0" class="templates-section">
        <h3><Icon name="magic" /> {{ $t('security.secretsManager.quickAddTemplates') }}</h3>
        <p class="templates-subtitle">{{ $t('security.secretsManager.quickAddTemplatesHint') }}</p>
        <div class="templates-grid">
          <div
            v-for="template in credentialTemplates"
            :key="template.id"
            class="template-card"
            @click="useTemplate(template)"
          >
            <div class="template-icon" :style="{ backgroundColor: template.color }">
              <Icon :name="template.icon" />
            </div>
            <div class="template-info">
              <h4>{{ template.name }}</h4>
              <p>{{ template.description }}</p>
            </div>
          </div>
        </div>
      </div>
    </main>

    <!-- Create/Edit Modal -->
    <BaseModal
      :modelValue="showCreateModal || showEditModal"
      @update:modelValue="val => !val && closeModals()"
      :title="modalTitle"
      size="lg"
      :closeOnOverlay="!saving"
    >
      <form @submit.prevent="saveSecret" class="credential-form">
        <!-- Template Selection (only for new) -->
        <div v-if="!showEditModal && !secretForm.type" class="template-selection">
          <h4>{{ $t('security.secretsManager.chooseType') }}</h4>
          <div class="type-grid">
            <div
              v-for="category in credentialCategories"
              :key="category.type"
              class="type-option"
              @click="selectType(category.type)"
            >
              <div class="type-icon" :style="{ backgroundColor: category.color }">
                <Icon :name="category.icon" />
              </div>
              <span>{{ category.label }}</span>
            </div>
          </div>
        </div>

        <!-- Form Fields -->
        <div v-else class="form-fields">
          <!-- Selected Type Display -->
          <div class="selected-type">
            <div class="type-icon" :style="{ backgroundColor: getTypeColor(secretForm.type) }">
              <Icon :name="getTypeIcon(secretForm.type)" />
            </div>
            <div class="type-info">
              <span class="type-label">{{ getTypeLabel(secretForm.type) }}</span>
              <button v-if="!showEditModal" type="button" @click="secretForm.type = ''" class="change-type">
                {{ $t('security.secretsManager.changeType') }}
              </button>
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>{{ $t('security.secretsManager.name') }} <span class="required">*</span></label>
              <input
                type="text"
                v-model="secretForm.name"
                required
                :placeholder="$t('security.secretsManager.namePlaceholder')"
                class="form-input"
              />
            </div>
          </div>

          <!-- Issue #685: Hierarchical Access Controls -->
          <div class="form-row two-col">
            <div class="form-group">
              <label for="secret-scope">{{ $t('security.secretsManager.scope') }} <span class="required">*</span></label>
              <select id="secret-scope" v-model="secretForm.scope" class="form-input">
                <option value="general">{{ $t('security.secretsManager.scopeGeneral') }}</option>
                <option value="chat">{{ $t('security.secretsManager.scopeChat') }}</option>
                <option value="user">{{ t('security.secretsManager.scopeUser') }}</option>
                <option value="session">{{ t('security.secretsManager.scopeSession') }}</option>
                <option value="shared">{{ $t('security.secretsManager.visibilityShared') }}</option>
              </select>
              <small class="input-hint">{{ t('security.secretsManager.scopeHint') }}</small>
            </div>
            <div class="form-group">
              <label for="secret-visibility">{{ $t('security.secretsManager.visibility') }} <span class="required">*</span></label>
              <select id="secret-visibility" v-model="secretForm.visibility" class="form-input">
                <option value="private">{{ $t('security.secretsManager.visibilityPrivate') }}</option>
                <option value="shared">{{ $t('security.secretsManager.visibilityShared') }}</option>
                <option value="group">{{ $t('security.secretsManager.visibilityGroup') }}</option>
                <option value="organization">{{ $t('security.secretsManager.visibilityOrganization') }}</option>
                <option value="system">{{ $t('security.secretsManager.visibilitySystem') }}</option>
              </select>
              <small class="input-hint">{{ $t('security.secretsManager.visibilityHint') }}</small>
            </div>
          </div>

          <!-- Conditional Organization/Team Fields -->
          <div class="form-row two-col" v-if="secretForm.visibility === 'organization' || secretForm.visibility === 'group'">
            <div class="form-group" v-if="secretForm.visibility === 'organization'">
              <label for="secret-org-id">{{ t('security.secretsManager.organizationId') }}</label>
              <input
                id="secret-org-id"
                type="text"
                v-model="secretForm.org_id"
                :placeholder="t('security.secretsManager.orgIdPlaceholder')"
                class="form-input"
              />
              <small class="input-hint">{{ t('security.secretsManager.orgIdHint') }}</small>
            </div>
            <div class="form-group" v-if="secretForm.visibility === 'group'">
              <label for="secret-team-ids">{{ t('security.secretsManager.teamIds') }}</label>
              <input
                id="secret-team-ids"
                type="text"
                v-model="teamIdsInput"
                :placeholder="t('security.secretsManager.teamIdsPlaceholder')"
                class="form-input"
                @input="updateTeamIds"
              />
              <small class="input-hint">{{ t('security.secretsManager.teamIdsHint') }}</small>
            </div>
          </div>

          <!-- Shared With Field (for visibility=shared) -->
          <div class="form-row" v-if="secretForm.visibility === 'shared'">
            <div class="form-group">
              <label for="secret-shared-with">{{ t('security.secretsManager.shareWithUsers') }}</label>
              <input
                id="secret-shared-with"
                type="text"
                v-model="sharedWithInput"
                :placeholder="t('security.secretsManager.sharedWithPlaceholder')"
                class="form-input"
                @input="updateSharedWith"
              />
              <small class="input-hint">{{ t('security.secretsManager.sharedWithHint') }}</small>
            </div>
          </div>

          <!-- Infrastructure Host Form Fields -->
          <template v-if="secretForm.type === 'infrastructure_host'">
            <!-- Host & Port Row -->
            <div class="form-row two-col">
              <div class="form-group">
                <label>{{ $t('security.secretsManager.host') }} <span class="required">*</span></label>
                <input
                  type="text"
                  v-model="secretForm.host"
                  required
                  :placeholder="$t('security.secretsManager.hostPlaceholder')"
                  class="form-input"
                />
              </div>
              <div class="form-group">
                <label>{{ $t('security.secretsManager.sshPort') }}</label>
                <input
                  type="number"
                  v-model.number="secretForm.ssh_port"
                  placeholder="22"
                  class="form-input"
                  min="1"
                  max="65535"
                />
              </div>
            </div>

            <!-- Username & Auth Type -->
            <div class="form-row two-col">
              <div class="form-group">
                <label>{{ $t('security.secretsManager.username') }} <span class="required">*</span></label>
                <input
                  type="text"
                  v-model="secretForm.username"
                  required
                  :placeholder="$t('security.secretsManager.usernamePlaceholder')"
                  class="form-input"
                />
              </div>
              <div class="form-group">
                <label>{{ $t('security.secretsManager.authType') }} <span class="required">*</span></label>
                <select v-model="secretForm.auth_type" class="form-input">
                  <option value="ssh_key">{{ $t('security.secretsManager.authSshKey') }}</option>
                  <option value="password">{{ $t('security.secretsManager.authPassword') }}</option>
                </select>
              </div>
            </div>

            <!-- SSH Key (if auth_type is ssh_key) -->
            <div class="form-row" v-if="secretForm.auth_type === 'ssh_key' && !showEditModal">
              <div class="form-group">
                <label>{{ $t('security.secretsManager.sshKey') }} <span class="required">*</span></label>
                <div class="secret-input-wrapper">
                  <textarea
                    v-model="secretForm.ssh_key"
                    required
                    placeholder="-----BEGIN OPENSSH PRIVATE KEY-----&#10;..."
                    class="form-input secret-input"
                    :class="{ 'secret-masked': !showValue }"
                    rows="6"
                  ></textarea>
                  <button
                    type="button"
                    @click="toggleValueVisibility"
                    class="toggle-visibility"
                    :title="showValue ? t('security.secretsManager.hideKey') : t('security.secretsManager.showKey')"
                  >
                    <Icon :name="showValue ? 'eye-slash' : 'eye'" />
                  </button>
                </div>
                <small class="input-hint">{{ t('security.secretsManager.sshKeyHint') }}</small>
              </div>
            </div>

            <!-- SSH Password (if auth_type is password) -->
            <div class="form-row" v-if="secretForm.auth_type === 'password' && !showEditModal">
              <div class="form-group">
                <label>{{ $t('security.secretsManager.password') }} <span class="required">*</span></label>
                <div class="secret-input-wrapper">
                  <input
                    type="password"
                    v-model="secretForm.ssh_password"
                    required
                    :placeholder="t('security.secretsManager.sshPasswordPlaceholder')"
                    class="form-input secret-input"
                    autocomplete="new-password"
                  />
                  <button
                    type="button"
                    @click="toggleValueVisibility"
                    class="toggle-visibility"
                    :title="showValue ? t('security.secretsManager.hidePassword') : t('security.secretsManager.showPassword')"
                  >
                    <Icon :name="showValue ? 'eye-slash' : 'eye'" />
                  </button>
                </div>
              </div>
            </div>

            <!-- Capabilities -->
            <div class="form-row">
              <div class="form-group">
                <label>{{ $t('security.secretsManager.capabilities') }}</label>
                <div class="capability-checkboxes">
                  <label class="checkbox-option">
                    <input type="checkbox" value="ssh" v-model="secretForm.capabilities" disabled checked />
                    <Icon name="terminal" />
                    <span>{{ t('security.secretsManager.sshAlwaysEnabled') }}</span>
                  </label>
                  <label class="checkbox-option">
                    <input type="checkbox" value="vnc" v-model="secretForm.capabilities" />
                    <Icon name="desktop" />
                    <span>{{ t('security.secretsManager.vncDesktop') }}</span>
                  </label>
                </div>
              </div>
            </div>

            <!-- VNC Settings (if VNC enabled) -->
            <div class="form-row two-col" v-if="secretForm.capabilities.includes('vnc')">
              <div class="form-group">
                <label>{{ $t('security.secretsManager.vncPort') }} <span class="required">*</span></label>
                <input
                  type="number"
                  v-model.number="secretForm.vnc_port"
                  required
                  placeholder="5901"
                  class="form-input"
                  min="1"
                  max="65535"
                />
              </div>
              <div class="form-group" v-if="!showEditModal">
                <label>{{ $t('security.secretsManager.vncPassword') }}</label>
                <input
                  type="password"
                  v-model="secretForm.vnc_password"
                  :placeholder="t('security.secretsManager.vncPasswordPlaceholder')"
                  class="form-input"
                  autocomplete="new-password"
                />
              </div>
            </div>

            <!-- OS & Purpose (metadata for knowledge base) -->
            <div class="form-row two-col">
              <div class="form-group">
                <label>{{ $t('security.secretsManager.os') }}</label>
                <input
                  type="text"
                  v-model="secretForm.os"
                  :placeholder="t('security.secretsManager.osPlaceholder')"
                  class="form-input"
                />
              </div>
              <div class="form-group">
                <label>{{ $t('security.secretsManager.purpose') }}</label>
                <input
                  type="text"
                  v-model="secretForm.purpose"
                  :placeholder="$t('security.secretsManager.purposePlaceholder')"
                  class="form-input"
                />
              </div>
            </div>
          </template>

          <!-- Standard Secret Value Field (non-infrastructure_host) -->
          <div class="form-row" v-else-if="!showEditModal">
            <div class="form-group">
              <label>{{ getValueLabel(secretForm.type) }} <span class="required">*</span></label>
              <div class="secret-input-wrapper">
                <!-- Multi-line secrets (SSH keys, certificates) use textarea with CSS masking -->
                <textarea
                  v-if="isMultilineSecret(secretForm.type)"
                  v-model="secretForm.value"
                  required
                  :placeholder="getValuePlaceholder(secretForm.type)"
                  class="form-input secret-input"
                  :class="{ 'secret-masked': !showValue }"
                  :rows="getValueRows(secretForm.type)"
                ></textarea>
                <!-- Single-line secrets use password input for proper masking -->
                <input
                  v-else
                  v-model="secretForm.value"
                  :type="showValue ? 'text' : 'password'"
                  required
                  :placeholder="getValuePlaceholder(secretForm.type)"
                  class="form-input secret-input"
                  autocomplete="off"
                />
                <button
                  type="button"
                  @click="toggleValueVisibility"
                  class="toggle-visibility"
                  :title="showValue ? t('security.secretsManager.hideValue') : t('security.secretsManager.showValue')"
                >
                  <Icon :name="showValue ? 'eye-slash' : 'eye'" />
                </button>
              </div>
              <small class="input-hint">{{ getValueHint(secretForm.type) }}</small>
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>{{ $t('security.secretsManager.description') }}</label>
              <textarea
                v-model="secretForm.description"
                :placeholder="$t('security.secretsManager.descriptionPlaceholder')"
                class="form-input"
                rows="2"
              ></textarea>
            </div>
          </div>

          <div class="form-row two-col">
            <div class="form-group">
              <label>{{ $t('security.secretsManager.tags') }}</label>
              <input
                type="text"
                v-model="tagsInput"
                :placeholder="$t('security.secretsManager.tagsPlaceholder')"
                class="form-input"
                @input="updateTags"
              />
              <small class="input-hint">{{ $t('security.secretsManager.tagsSeparator') }}</small>
            </div>
            <div class="form-group">
              <label>{{ $t('security.secretsManager.expiration') }}</label>
              <input
                type="datetime-local"
                v-model="secretForm.expires_at"
                class="form-input"
              />
              <small class="input-hint">{{ t('security.secretsManager.expirationHint') }}</small>
            </div>
          </div>
        </div>
      </form>

      <template #actions>
        <button type="button" @click="closeModals" class="btn-secondary">{{ $t('security.secretsManager.cancel') }}</button>
        <button
          type="submit"
          @click="saveSecret"
          class="btn-primary"
          :disabled="saving || !isFormValid"
        >
          <Icon name="spinner" class="animate-spin" v-if="saving" />
          {{ saving ? $t('security.secretsManager.saving') : (showEditModal ? $t('security.secretsManager.updateCredential') : $t('security.secretsManager.createCredential')) }}
        </button>
      </template>
    </BaseModal>

    <!-- View Secret Modal -->
    <BaseModal
      v-model="showViewModal"
      :title="viewingSecret?.name || $t('security.secretsManager.viewDetails')"
      size="md"
    >
      <div class="view-credential">
        <div class="view-header">
          <div class="view-icon" :style="{ backgroundColor: getTypeColor(viewingSecret?.type) }">
            <Icon :name="getTypeIcon(viewingSecret?.type)" />
          </div>
          <div class="view-title">
            <h3>{{ viewingSecret?.name }}</h3>
            <span class="view-type">{{ getTypeLabel(viewingSecret?.type) }}</span>
          </div>
        </div>

        <div class="view-section">
          <label>{{ $t('security.secretsManager.value') }}</label>
          <div class="secret-display">
            <code v-if="showSecretValue">{{ viewingSecret?.value || t('security.secretsManager.loadingValue') }}</code>
            <code v-else>{{ '•'.repeat(Math.min(viewingSecret?.value?.length || 20, 40)) }}</code>
            <div class="secret-actions">
              <button @click="toggleSecretValue" class="action-btn">
                <Icon :name="showSecretValue ? 'eye-slash' : 'eye'" />
              </button>
              <button @click="copySecretValue" class="action-btn">
                <Icon name="copy" />
              </button>
            </div>
          </div>
        </div>

        <div class="view-grid">
          <div class="view-item">
            <label>{{ $t('security.secretsManager.scope') }}</label>
            <span class="badge" :class="viewingSecret?.scope">
              <Icon :name="viewingSecret?.scope === 'general' ? 'globe' : 'comments'" />
              {{ viewingSecret?.scope }}
            </span>
          </div>
          <div class="view-item">
            <label>{{ $t('security.secretsManager.createdAt') }}</label>
            <span>{{ formatDate(viewingSecret?.created_at) }}</span>
          </div>
          <div class="view-item" v-if="viewingSecret?.expires_at">
            <label>{{ $t('security.secretsManager.expiresAt') }}</label>
            <span :class="{ 'text-danger': isExpired(viewingSecret), 'text-warning': isExpiringSoon(viewingSecret) }">
              {{ formatDate(viewingSecret?.expires_at) }}
            </span>
          </div>
          <div class="view-item" v-if="viewingSecret?.updated_at">
            <label>{{ $t('security.secretsManager.lastUpdated') }}</label>
            <span>{{ formatDate(viewingSecret?.updated_at) }}</span>
          </div>
        </div>

        <div class="view-section" v-if="viewingSecret?.description">
          <label>{{ $t('security.secretsManager.description') }}</label>
          <p>{{ viewingSecret.description }}</p>
        </div>

        <div class="view-section" v-if="viewingSecret?.tags?.length">
          <label>{{ $t('security.secretsManager.tags') }}</label>
          <div class="tags-list">
            <span v-for="tag in viewingSecret.tags" :key="tag" class="tag">{{ tag }}</span>
          </div>
        </div>
      </div>

      <template #actions>
        <button @click="closeViewModal" class="btn-secondary">{{ $t('security.secretsManager.close') }}</button>
        <button @click="editSecret(viewingSecret)" class="btn-primary">
          <Icon name="edit" /> {{ $t('security.secretsManager.edit') }}
        </button>
      </template>
    </BaseModal>

    <!-- Transfer Modal -->
    <BaseModal
      v-model="showTransferModal"
      :title="$t('security.secretsManager.transferTitle')"
      size="sm"
    >
      <div class="transfer-content">
        <div class="transfer-icon">
          <Icon name="share-alt" />
        </div>
        <h4>{{ $t('security.secretsManager.transferConfirmTitle', { name: transferringSecret?.name }) }}</h4>
        <p>{{ $t('security.secretsManager.transferConfirmMessage') }}</p>
        <div class="transfer-warning">
          <Icon name="info-circle" />
          <span>{{ $t('security.secretsManager.cannotBeUndone') }}</span>
        </div>
      </div>

      <template #actions>
        <button @click="closeTransferModal" class="btn-secondary">{{ $t('security.secretsManager.cancel') }}</button>
        <button @click="confirmTransfer" class="btn-primary" :disabled="transferring">
          <Icon name="spinner" class="animate-spin" v-if="transferring" />
          {{ transferring ? $t('security.secretsManager.transferring') : $t('security.secretsManager.transferToGeneral') }}
        </button>
      </template>
    </BaseModal>

    <!-- Delete Confirmation Modal -->
    <BaseModal
      v-model="showDeleteModal"
      :title="$t('security.secretsManager.deleteConfirmTitle')"
      size="sm"
    >
      <div class="delete-content">
        <div class="delete-icon">
          <Icon name="trash-alt" />
        </div>
        <h4>{{ $t('security.secretsManager.deleteConfirmName', { name: deletingSecret?.name }) }}</h4>
        <p>{{ $t('security.secretsManager.deleteConfirmMessage') }}</p>
        <div class="delete-warning">
          <Icon name="exclamation-triangle" />
          <span>{{ $t('security.secretsManager.cannotBeUndone') }}</span>
        </div>
      </div>

      <template #actions>
        <button @click="showDeleteModal = false" class="btn-secondary">{{ $t('security.secretsManager.cancel') }}</button>
        <button @click="deleteSecret" class="btn-danger" :disabled="deleting">
          <Icon name="spinner" class="animate-spin" v-if="deleting" />
          {{ deleting ? $t('security.secretsManager.deleting') : $t('security.secretsManager.deleteCredential') }}
        </button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import type { IconName } from '@/components/ui/Icon.vue'
import Icon from '@/components/ui/Icon.vue'
import { ref, reactive, computed, onMounted, watch } from 'vue';
import { useI18n } from 'vue-i18n';
// @ts-ignore - JavaScript API client without type declarations
import { secretsApiClient } from '@/utils/SecretsApiClient';
import { useChatStore } from '@/stores/useChatStore';
import { createLogger } from '@/utils/debugUtils';
import { formatDateTime } from '@/utils/formatHelpers';
import { useDebounce } from '@/composables/useDebounce';
import { useSecretsAuditApi } from '@/composables/security/useSecretsAuditApi';
import EmptyState from '@/components/ui/EmptyState.vue';
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue';
import { BaseModal } from '@autobot/ui'
import { getCssVar } from '@/composables/useCssVars'

const { t } = useI18n();
const logger = createLogger('SecretsManager');
const { fetchInfraHosts, fetchSecretsUsage, deleteInfraHost } = useSecretsAuditApi();

// Credential type categories with icons and colors (using design tokens)
interface CredentialCategory {
  type: string
  label: string
  icon: IconName
  color: string
}

const credentialCategories = computed<CredentialCategory[]>(() => [
  { type: 'api_key', label: 'API Keys', icon: 'key', color: getCssVar('--color-primary', '#6366f1') },
  // #9724: 'ticket-alt'/'certificate' are not SVG IconNames (rendered empty)
  { type: 'token', label: 'Tokens', icon: 'tag', color: getCssVar('--chart-purple', '#8b5cf6') },
  { type: 'password', label: 'Passwords', icon: 'lock', color: getCssVar('--chart-pink', '#ec4899') },
  { type: 'ssh_key', label: 'SSH Keys', icon: 'terminal', color: getCssVar('--chart-teal', '#14b8a6') },
  { type: 'infrastructure_host', label: 'Infrastructure Hosts', icon: 'server', color: getCssVar('--chart-blue', '#3b82f6') },
  { type: 'database_url', label: 'Database', icon: 'database', color: getCssVar('--color-warning', '#f59e0b') },
  { type: 'certificate', label: 'Certificates', icon: 'shield-check', color: getCssVar('--color-success', '#10b981') },
  { type: 'other', label: 'Other', icon: 'ellipsis-h', color: getCssVar('--text-tertiary', '#6b7280') },
]);

// Quick-add templates for common services (using design tokens)
interface CredentialTemplate {
  id: string
  name: string
  description: string
  icon: IconName
  color: string
  type: string
}

// #9724: 'aws'/'github'/'slack' brand icons are not SVG IconNames (rendered
// empty) — mapped to the closest registry icons.
const credentialTemplates = computed<CredentialTemplate[]>(() => [
  { id: 'openai', name: 'OpenAI', description: 'GPT API access', icon: 'brain', color: getCssVar('--color-success', '#10a37f'), type: 'api_key' },
  { id: 'anthropic', name: 'Anthropic', description: 'Claude API access', icon: 'robot', color: getCssVar('--color-warning-hover', '#d97706'), type: 'api_key' },
  { id: 'aws', name: 'AWS', description: 'Amazon Web Services', icon: 'cloud', color: getCssVar('--chart-orange', '#ff9900'), type: 'api_key' },
  { id: 'github', name: 'GitHub', description: 'GitHub personal token', icon: 'code-branch', color: getCssVar('--bg-tertiary', '#333'), type: 'token' },
  { id: 'postgres', name: 'PostgreSQL', description: 'Database connection', icon: 'database', color: getCssVar('--color-info', '#336791'), type: 'database_url' },
  { id: 'redis', name: 'Redis', description: 'Redis connection', icon: 'layer-group', color: getCssVar('--chart-red', '#dc382d'), type: 'database_url' },
  { id: 'ssh', name: 'SSH Key', description: 'Server access', icon: 'terminal', color: getCssVar('--bg-primary', '#000'), type: 'ssh_key' },
  { id: 'slack', name: 'Slack', description: 'Slack bot token', icon: 'comments', color: getCssVar('--chart-purple', '#4a154b'), type: 'token' },
  { id: 'server', name: 'Server Host', description: 'SSH/VNC server access', icon: 'server', color: getCssVar('--chart-blue', '#3b82f6'), type: 'infrastructure_host' },
]);

// State
const secrets = ref<any[]>([]);
const stats = ref<any>(null);
const loading = ref(false);
const workflowUsage = ref<Record<string, any[]>>({});
const saving = ref(false);
const deleting = ref(false);
const transferring = ref(false);

// View state
const viewMode = ref<'grid' | 'list'>('grid');
const selectedCategory = ref('all');
const selectedScope = ref('');
const searchQuery = ref('');
const showExpiredOnly = ref(false);
const selectedSecretId = ref<string | null>(null);
const showTemplates = ref(true);

// Modal state
const showCreateModal = ref(false);
const showEditModal = ref(false);
const showViewModal = ref(false);
const showTransferModal = ref(false);
const showDeleteModal = ref(false);
const showSecretValue = ref(false);
const showValue = ref(false);

// Form state
const secretForm = reactive({
  id: '',
  name: '',
  type: '',
  scope: 'general',
  chat_id: '',
  value: '',
  description: '',
  expires_at: '',
  tags: [] as string[],
  // Issue #685: Hierarchical access fields
  visibility: 'private',
  owner_id: '',
  org_id: '',
  team_ids: [] as string[],
  shared_with: [] as string[],
  // Infrastructure host specific fields
  host: '',
  ssh_port: 22,
  vnc_port: null as number | null,
  username: 'root',
  auth_type: 'ssh_key' as 'ssh_key' | 'password',
  ssh_key: '',
  ssh_password: '',
  vnc_password: '',
  capabilities: ['ssh'] as string[],
  os: '',
  purpose: ''
});
const tagsInput = ref('');
const teamIdsInput = ref('');
const sharedWithInput = ref('');
const viewingSecret = ref<any>(null);
const transferringSecret = ref<any>(null);
const deletingSecret = ref<any>(null);

// Debounced search
const debouncedSearch = useDebounce(searchQuery, 300);

// Cache for memoized filteredSecrets computation
const filterCache = new Map<string, any[]>();

// Helper function to generate stable cache key from filter values
const getFilterCacheKey = (): string => {
  return JSON.stringify([
    selectedCategory.value,
    selectedScope.value,
    showExpiredOnly.value,
    debouncedSearch.value,
    secrets.value.length  // Include length to invalidate on additions/deletions
  ]);
};

// Computed - Memoized with cache key based on filter parameters
const filteredSecrets = computed(() => {
  const cacheKey = getFilterCacheKey();

  // Return cached result if available
  if (filterCache.has(cacheKey)) {
    return filterCache.get(cacheKey) || [];
  }

  let result = [...secrets.value];

  // Filter by category/type
  if (selectedCategory.value !== 'all') {
    result = result.filter(s => s.type === selectedCategory.value);
  }

  // Filter by scope
  if (selectedScope.value) {
    result = result.filter(s => s.scope === selectedScope.value);
  }

  // Filter expired only
  if (showExpiredOnly.value) {
    result = result.filter(s => isExpired(s));
  }

  // Search filter
  if (debouncedSearch.value) {
    const query = debouncedSearch.value.toLowerCase();
    result = result.filter(s =>
      s.name.toLowerCase().includes(query) ||
      s.description?.toLowerCase().includes(query) ||
      s.tags?.some((t: string) => t.toLowerCase().includes(query))
    );
  }

  // Store result in cache
  filterCache.set(cacheKey, result);

  // Prevent unbounded cache growth - clear when > 50 entries
  if (filterCache.size > 50) {
    filterCache.clear();
  }

  return result;
});

const currentCategoryLabel = computed(() => {
  if (showExpiredOnly.value) return t('security.secretsManager.expiredCredentials');
  if (selectedScope.value) return `${selectedScope.value.charAt(0).toUpperCase() + selectedScope.value.slice(1)} ${t('security.secretsManager.sidebarTitle')}`;
  if (selectedCategory.value === 'all') return t('security.secretsManager.allCredentials');
  const cat = credentialCategories.value.find(c => c.type === selectedCategory.value);
  return cat?.label || t('security.secretsManager.sidebarTitle');
});

const hasActiveFilters = computed(() => {
  return selectedCategory.value !== 'all' || selectedScope.value || showExpiredOnly.value || searchQuery.value;
});

const emptyStateIcon = computed(() => {
  if (hasActiveFilters.value) return 'search';
  return 'key';
});

const emptyStateMessage = computed(() => {
  if (hasActiveFilters.value) return t('security.secretsManager.noCredentialsFiltered');
  return t('security.secretsManager.noCredentialsHint');
});

const modalTitle = computed(() => {
  if (showEditModal.value) return t('security.secretsManager.editCredential');
  if (!secretForm.type) return t('security.secretsManager.newCredential');
  return t('security.secretsManager.newType', { type: getTypeLabel(secretForm.type) });
});

const isFormValid = computed(() => {
  if (!secretForm.type) return false;
  if (!secretForm.name.trim()) return false;
  if (!secretForm.scope) return false;

  // Infrastructure host has different validation
  if (secretForm.type === 'infrastructure_host') {
    if (!secretForm.host.trim()) return false;
    if (!secretForm.username.trim()) return false;
    if (secretForm.auth_type === 'ssh_key' && !showEditModal.value && !secretForm.ssh_key.trim()) return false;
    if (secretForm.auth_type === 'password' && !showEditModal.value && !secretForm.ssh_password.trim()) return false;
    if (secretForm.capabilities.includes('vnc') && !secretForm.vnc_port) return false;
    return true;
  }

  // Standard secrets require value
  if (!showEditModal.value && !secretForm.value.trim()) return false;
  return true;
});

// Methods
const loadSecrets = async () => {
  loading.value = true;
  try {
    // Fetch secrets and stats - infrastructure_host is now a regular secret type
    const [secretsResponse, statsResponse, legacyHostsResponse] = await Promise.all([
      secretsApiClient.getSecrets({}) as Promise<Record<string, any>>,
      secretsApiClient.getSecretsStats() as Promise<Record<string, any>>,
      // Also fetch legacy hosts for backwards compatibility (will be migrated eventually)
      fetchInfraHosts()
    ]);

    // Convert legacy infrastructure hosts to secret-like format for unified display
    const legacyInfraSecrets = (legacyHostsResponse.hosts || []).map((host: any) => ({
      id: host.id,
      name: host.name,
      type: 'infrastructure_host',
      scope: host.scope || 'general',
      chat_id: host.chat_id,
      description: host.description || `${host.username}@${host.host}:${host.ssh_port}`,
      tags: host.tags || [],
      created_at: host.created_at,
      updated_at: host.updated_at,
      expires_at: null,
      metadata: {
        host: host.host,
        ssh_port: host.ssh_port,
        vnc_port: host.vnc_port,
        username: host.username,
        auth_type: host.auth_type,
        capabilities: host.capabilities
      },
      _isLegacyHost: true  // Flag for legacy hosts that need different delete API
    }));

    // Merge regular secrets with legacy infrastructure hosts
    // (new infra hosts are already in secrets with type=infrastructure_host)
    secrets.value = [...(secretsResponse.secrets || []), ...legacyInfraSecrets];

    // Update stats
    const legacyInfraCount = legacyInfraSecrets.length;
    stats.value = {
      ...statsResponse,
      total_secrets: (statsResponse.total_secrets || 0) + legacyInfraCount,
      by_type: {
        ...statsResponse.by_type,
        infrastructure_host: (statsResponse.by_type?.infrastructure_host || 0) + legacyInfraCount
      }
    };

    showTemplates.value = secrets.value.length === 0;
  } catch (error) {
    logger.error('Failed to load secrets:', error);
  } finally {
    loading.value = false;
  }
};

// Load workflow usage for secrets (#1415)
const loadWorkflowUsage = async () => {
  try {
    const data = await fetchSecretsUsage();
    workflowUsage.value = data.secrets_usage || {};
  } catch (error) {
    logger.error('Failed to load workflow usage:', error);
  }
};

// Get workflow usage for a secret by matching name to keys (#1415)
const getWorkflowUsage = (secret: any): any[] => {
  const name = (secret.name || '').toUpperCase().replace(/\s+/g, '_');
  return workflowUsage.value[name] || [];
};

const selectCategory = (type: string) => {
  selectedCategory.value = type;
  selectedScope.value = '';
  showExpiredOnly.value = false;
};

const selectScope = (scope: string) => {
  if (selectedScope.value === scope) {
    selectedScope.value = '';
  } else {
    selectedScope.value = scope;
  }
  selectedCategory.value = 'all';
  showExpiredOnly.value = false;
};

const toggleExpiredFilter = () => {
  showExpiredOnly.value = !showExpiredOnly.value;
  if (showExpiredOnly.value) {
    selectedCategory.value = 'all';
    selectedScope.value = '';
  }
};

const clearFilters = () => {
  selectedCategory.value = 'all';
  selectedScope.value = '';
  showExpiredOnly.value = false;
  searchQuery.value = '';
};

const toggleView = () => {
  viewMode.value = viewMode.value === 'grid' ? 'list' : 'grid';
};

const getCategoryCount = (type: string) => {
  return secrets.value.filter(s => s.type === type).length;
};

const getTypeColor = (type: string) => {
  const cat = credentialCategories.value.find(c => c.type === type);
  return cat?.color || getCssVar('--text-tertiary', '#6b7280');
};

const getTypeIcon = (type: string) => {
  const cat = credentialCategories.value.find(c => c.type === type);
  return cat?.icon || 'key';
};

const getTypeLabel = (type: string) => {
  const cat = credentialCategories.value.find(c => c.type === type);
  return cat?.label.replace(/s$/, '') || type?.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) || '';
};

const getValueLabel = (type: string) => {
  const labels: Record<string, string> = {
    api_key: 'API Key',
    token: 'Token',
    password: 'Password',
    ssh_key: 'Private Key',
    database_url: 'Connection String',
    certificate: 'Certificate Content',
    other: 'Secret Value'
  };
  return labels[type] || 'Value';
};

const getValuePlaceholder = (type: string) => {
  const placeholders: Record<string, string> = {
    api_key: 'sk-xxxxxxxxxxxxxxxxxxxx',
    token: 'ghp_xxxxxxxxxxxxxxxxxxxx',
    password: 'Enter password',
    ssh_key: '-----BEGIN OPENSSH PRIVATE KEY-----\n...',
    database_url: 'postgresql://user:password@host:5432/database',
    certificate: '-----BEGIN CERTIFICATE-----\n...',
    other: 'Enter secret value'
  };
  return placeholders[type] || 'Enter value';
};

const isMultilineSecret = (type: string) => {
  return ['ssh_key', 'certificate'].includes(type);
};

const getValueRows = (type: string) => {
  return isMultilineSecret(type) ? 6 : 3;
};

const getValueHint = (type: string) => {
  const hints: Record<string, string> = {
    api_key: 'Your API key will be encrypted and stored securely',
    ssh_key: 'Paste your entire private key including BEGIN/END markers',
    database_url: 'Include username, password, host, port, and database name',
    certificate: 'Paste the full certificate in PEM format',
    token: 'Access tokens are sensitive - keep them private',
    password: 'Passwords are encrypted before storage'
  };
  return hints[type] || 'This value will be encrypted and stored securely';
};

const selectSecret = (secret: any) => {
  selectedSecretId.value = secret.id;
};

const selectType = (type: string) => {
  secretForm.type = type;
};

const useTemplate = (template: any) => {
  resetForm();
  secretForm.type = template.type;
  secretForm.name = template.name;
  secretForm.tags = [template.id];
  showCreateModal.value = true;
};

const openCreateModal = () => {
  resetForm();
  showCreateModal.value = true;
};

const viewSecret = async (secret: any) => {
  try {
    // Handle infrastructure hosts - show connection info instead of raw credential
    if (secret.type === 'infrastructure_host') {
      const meta = secret.metadata || {};
      viewingSecret.value = {
        ...secret,
        value: `${meta.username || 'root'}@${meta.host || 'unknown'}:${meta.ssh_port || 22}`,
        _isInfraHost: true
      };
      showSecretValue.value = false;
      showViewModal.value = true;
      return;
    }

    const response = await secretsApiClient.getSecret(secret.id, { chatId: secret.chat_id });
    viewingSecret.value = response;
    showSecretValue.value = false;
    showViewModal.value = true;
  } catch (error) {
    logger.error('Failed to load secret details:', error);
  }
};

const editSecret = (secret: any) => {
  secretForm.id = secret.id;
  secretForm.name = secret.name;
  secretForm.type = secret.type;
  secretForm.scope = secret.scope;
  secretForm.chat_id = secret.chat_id || '';
  secretForm.description = secret.description || '';
  secretForm.expires_at = secret.expires_at ? new Date(secret.expires_at).toISOString().slice(0, 16) : '';
  secretForm.tags = [...(secret.tags || [])];
  tagsInput.value = secretForm.tags.join(', ');

  // Issue #685: Populate hierarchical access fields
  secretForm.visibility = secret.visibility || 'private';
  secretForm.owner_id = secret.owner_id || '';
  secretForm.org_id = secret.org_id || '';
  secretForm.team_ids = [...(secret.team_ids || [])];
  secretForm.shared_with = [...(secret.shared_with || [])];
  teamIdsInput.value = secretForm.team_ids.join(', ');
  sharedWithInput.value = secretForm.shared_with.join(', ');

  // Populate infrastructure host specific fields from metadata
  if (secret.type === 'infrastructure_host' && secret.metadata) {
    const meta = secret.metadata;
    secretForm.host = meta.host || '';
    secretForm.ssh_port = meta.ssh_port || 22;
    secretForm.vnc_port = meta.vnc_port || null;
    secretForm.username = meta.username || 'root';
    secretForm.auth_type = meta.auth_type || 'password';
    secretForm.capabilities = meta.capabilities || ['ssh'];
    secretForm.os = meta.os || '';
    secretForm.purpose = meta.purpose || '';
  }

  showViewModal.value = false;
  showEditModal.value = true;
};

const transferSecret = (secret: any) => {
  transferringSecret.value = secret;
  showTransferModal.value = true;
};

const confirmDelete = (secret: any) => {
  deletingSecret.value = secret;
  showDeleteModal.value = true;
};

const deleteSecret = async () => {
  if (!deletingSecret.value) return;

  deleting.value = true;
  try {
    // Handle legacy infrastructure hosts differently (they use old API)
    if (deletingSecret.value._isLegacyHost) {
      await deleteInfraHost(deletingSecret.value.id);
    } else {
      // All secrets (including new infrastructure_host type) use unified secrets API
      await secretsApiClient.deleteSecret(deletingSecret.value.id, { chatId: deletingSecret.value.chat_id });
    }
    showDeleteModal.value = false;
    deletingSecret.value = null;
    await loadSecrets();
  } catch (error) {
    logger.error('Failed to delete secret:', error);
  } finally {
    deleting.value = false;
  }
};

const confirmTransfer = async () => {
  if (!transferringSecret.value) return;

  transferring.value = true;
  try {
    await secretsApiClient.transferSecrets({
      secret_ids: [transferringSecret.value.id],
      target_scope: 'general'
    }, { chatId: transferringSecret.value.chat_id });
    showTransferModal.value = false;
    transferringSecret.value = null;
    await loadSecrets();
  } catch (error) {
    logger.error('Failed to transfer secret:', error);
  } finally {
    transferring.value = false;
  }
};

// Issue #685: Validation helper for hierarchical access
const validateAccessLevelCombination = (
  visibility: string,
  fields: { org_id?: string; team_ids?: string[]; shared_with?: string[] }
): string | null => {
  if (visibility === 'organization' && !fields.org_id) {
    return 'Organization ID is required when visibility is set to "Organization"';
  }

  if (visibility === 'group' && (!fields.team_ids || fields.team_ids.length === 0)) {
    return 'At least one Team ID is required when visibility is set to "Group"';
  }

  if (visibility === 'shared' && (!fields.shared_with || fields.shared_with.length === 0)) {
    return 'At least one user must be specified when visibility is set to "Shared"';
  }

  return null;
};

const saveSecret = async () => {
  if (!isFormValid.value) return;

  // Issue #685: Frontend validation for hierarchical access
  const validationError = validateAccessLevelCombination(secretForm.visibility, {
    org_id: secretForm.org_id,
    team_ids: secretForm.team_ids,
    shared_with: secretForm.shared_with
  });

  if (validationError) {
    logger.error('Validation failed:', validationError);
    // Could add a toast notification here
    return;
  }

  saving.value = true;
  try {
    const chatStore = useChatStore();

    // Build base secret data
    const secretData: any = {
      name: secretForm.name,
      type: secretForm.type,
      scope: secretForm.scope,
      chat_id: secretForm.scope === 'chat' ? (secretForm.chat_id || chatStore.currentSessionId) : null,
      description: secretForm.description,
      expires_at: secretForm.expires_at ? new Date(secretForm.expires_at).toISOString() : null,
      tags: secretForm.tags,
      // Issue #685: Hierarchical access fields
      visibility: secretForm.visibility,
      owner_id: secretForm.owner_id || null,
      org_id: secretForm.org_id || null,
      team_ids: secretForm.team_ids.length > 0 ? secretForm.team_ids : [],
      shared_with: secretForm.shared_with.length > 0 ? secretForm.shared_with : []
    };

    // Handle infrastructure_host type - store host info in metadata, credential in value
    if (secretForm.type === 'infrastructure_host') {
      secretData.metadata = {
        host: secretForm.host,
        ssh_port: secretForm.ssh_port,
        vnc_port: secretForm.vnc_port,
        username: secretForm.username,
        auth_type: secretForm.auth_type,
        capabilities: secretForm.capabilities,
        os: secretForm.os || null,
        purpose: secretForm.purpose || null
      };
      // Store the actual credential (password or SSH key) in the encrypted value field
      if (!showEditModal.value) {
        secretData.value = secretForm.auth_type === 'ssh_key'
          ? secretForm.ssh_key
          : secretForm.ssh_password;
      }
      // Auto-generate description if empty
      if (!secretData.description) {
        secretData.description = `${secretForm.username}@${secretForm.host}:${secretForm.ssh_port}`;
      }
    }

    if (showEditModal.value) {
      await secretsApiClient.updateSecret(secretForm.id, secretData, { chatId: secretData.chat_id });
    } else {
      // For non-infrastructure_host types, use the standard value field
      if (secretForm.type !== 'infrastructure_host') {
        secretData.value = secretForm.value;
      }
      await secretsApiClient.createSecret(secretData);
    }

    closeModals();
    await loadSecrets();
  } catch (error) {
    logger.error('Failed to save secret:', error);
  } finally {
    saving.value = false;
  }
};

const closeModals = () => {
  showCreateModal.value = false;
  showEditModal.value = false;
  resetForm();
};

const closeViewModal = () => {
  showViewModal.value = false;
  viewingSecret.value = null;
  showSecretValue.value = false;
};

const closeTransferModal = () => {
  showTransferModal.value = false;
  transferringSecret.value = null;
};

const resetForm = () => {
  Object.assign(secretForm, {
    id: '',
    name: '',
    type: '',
    scope: 'general',
    chat_id: '',
    value: '',
    description: '',
    expires_at: '',
    tags: [],
    // Issue #685: Hierarchical access fields
    visibility: 'private',
    owner_id: '',
    org_id: '',
    team_ids: [],
    shared_with: [],
    // Infrastructure host specific fields
    host: '',
    ssh_port: 22,
    vnc_port: null,
    username: 'root',
    auth_type: 'ssh_key',
    ssh_key: '',
    ssh_password: '',
    vnc_password: '',
    capabilities: ['ssh'],
    os: '',
    purpose: ''
  });
  tagsInput.value = '';
  teamIdsInput.value = '';
  sharedWithInput.value = '';
  showValue.value = false;
};

const updateTags = () => {
  secretForm.tags = tagsInput.value
    .split(',')
    .map(tag => tag.trim())
    .filter(tag => tag.length > 0);
};

const updateTeamIds = () => {
  secretForm.team_ids = teamIdsInput.value
    .split(',')
    .map(id => id.trim())
    .filter(id => id.length > 0);
};

const updateSharedWith = () => {
  secretForm.shared_with = sharedWithInput.value
    .split(',')
    .map(id => id.trim())
    .filter(id => id.length > 0);
};

const toggleValueVisibility = () => {
  showValue.value = !showValue.value;
};

const toggleSecretValue = () => {
  showSecretValue.value = !showSecretValue.value;
};

const copySecretValue = async () => {
  if (viewingSecret.value?.value) {
    try {
      await navigator.clipboard.writeText(viewingSecret.value.value);
      // Could add toast notification here
    } catch (error) {
      logger.error('Failed to copy to clipboard:', error);
    }
  }
};

const formatDate = (dateString: string) => {
  if (!dateString) return 'N/A';
  return formatDateTime(dateString);
};

const formatRelativeTime = (dateString: string) => {
  if (!dateString) return '';
  const date = new Date(dateString);
  const now = new Date();
  const diff = date.getTime() - now.getTime();
  const absDiff = Math.abs(diff);

  if (absDiff < 60000) return diff < 0 ? t('security.secretsManager.timeJustNow') : t('security.secretsManager.timeInAMoment');
  if (absDiff < 3600000) {
    const mins = Math.floor(absDiff / 60000);
    return diff < 0 ? t('security.secretsManager.timeMinutesAgo', { count: mins }) : t('security.secretsManager.timeInMinutes', { count: mins });
  }
  if (absDiff < 86400000) {
    const hours = Math.floor(absDiff / 3600000);
    return diff < 0 ? t('security.secretsManager.timeHoursAgo', { count: hours }) : t('security.secretsManager.timeInHours', { count: hours });
  }
  const days = Math.floor(absDiff / 86400000);
  return diff < 0 ? t('security.secretsManager.timeDaysAgo', { count: days }) : t('security.secretsManager.timeInDays', { count: days });
};

const truncate = (text: string, length: number) => {
  if (!text || text.length <= length) return text;
  return text.substring(0, length) + '...';
};

const isExpired = (secret: any) => {
  if (!secret?.expires_at) return false;
  return new Date(secret.expires_at) < new Date();
};

const isExpiringSoon = (secret: any) => {
  if (!secret?.expires_at || isExpired(secret)) return false;
  const expiry = new Date(secret.expires_at);
  const now = new Date();
  const daysUntilExpiry = (expiry.getTime() - now.getTime()) / (1000 * 60 * 60 * 24);
  return daysUntilExpiry <= 7;
};

// Issue #685: Visibility badge helpers
const getVisibility = (secret: any): string | null => {
  return secret?.visibility || null;
};

const formatVisibility = (secret: any): string => {
  const visibility = getVisibility(secret);
  if (!visibility) return '';

  const labels: Record<string, string> = {
    'private': t('security.secretsManager.visibilityPrivate'),
    'shared': t('security.secretsManager.visibilityShared'),
    'group': t('security.secretsManager.visibilityGroup'),
    'organization': t('security.secretsManager.visibilityOrganization'),
    'system': t('security.secretsManager.visibilitySystem')
  };
  return labels[visibility] || visibility.charAt(0).toUpperCase() + visibility.slice(1);
};

// #9724: 'user-friends'/'building' are not SVG IconNames (rendered empty)
const getVisibilityIcon = (secret: Record<string, unknown>): IconName => {
  const visibility = getVisibility(secret);
  const icons: Record<string, IconName> = {
    'private': 'lock',
    'shared': 'users',
    'group': 'users',
    'organization': 'briefcase',
    'system': 'globe'
  };
  return icons[visibility || ''] || 'eye';
};

// Lifecycle
onMounted(() => {
  loadSecrets();
  loadWorkflowUsage();
});

// Watch for scope changes to reload with filter
watch(selectedScope, () => {
  // Local filtering handles this, no need to reload
});
</script>

<style scoped>
/* Issue #704: Uses CSS design tokens via getCssVar() helper */
.secrets-manager-n8n {
  display: flex;
  height: 100%;
  min-height: 0;
  background: var(--bg-primary);
}

/* Sidebar */
.secrets-sidebar {
  width: 280px;
  min-width: 280px;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-header {
  padding: var(--spacing-5);
  border-bottom: 1px solid var(--border-default);
}

.sidebar-header h3 {
  margin: var(--spacing-0);
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.sidebar-header i {
  color: var(--color-primary);
}

.sidebar-search {
  padding: var(--spacing-4) var(--spacing-5);
  border-bottom: 1px solid var(--border-default);
}

.search-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.search-wrapper i {
  position: absolute;
  left: 12px;
  color: var(--text-muted);
  font-size: var(--text-sm);
}

.search-wrapper .search-input {
  width: 100%;
  padding: var(--spacing-2-5) var(--spacing-9) var(--spacing-2-5) var(--spacing-9);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  transition: all var(--duration-200);
  background: var(--bg-input);
  color: var(--text-primary);
}

.search-wrapper .search-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}
.search-wrapper .search-input:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.clear-search {
  position: absolute;
  right: 8px;
  background: none;
  border: none;
  padding: var(--spacing-1);
  cursor: pointer;
  color: var(--text-muted);
}

.category-nav {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-3) var(--spacing-0);
}

.category-divider {
  padding: var(--spacing-3) var(--spacing-5) var(--spacing-2);
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
}

.category-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-2-5) var(--spacing-5);
  cursor: pointer;
  transition: all var(--duration-150);
  color: var(--text-secondary);
}

.category-item:hover {
  background: var(--bg-hover);
}

.category-item.active {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.category-item i {
  width: 20px;
  text-align: center;
  font-size: var(--text-sm);
}

.category-item span:first-of-type:not(.count) {
  flex: 1;
  font-size: var(--text-sm);
}

.category-item .count {
  font-size: var(--text-xs);
  background: var(--bg-tertiary);
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-xl);
  color: var(--text-tertiary);
}

.category-item.active .count {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.category-item.alert {
  color: var(--color-error);
}

.category-item.alert .count.alert {
  background: var(--color-error);
  color: var(--text-on-error);
}

.sidebar-actions {
  padding: var(--spacing-4) var(--spacing-5);
  border-top: 1px solid var(--border-default);
}

.btn-create {
  width: 100%;
  padding: var(--spacing-3);
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  transition: all var(--duration-200);
}

.btn-create:hover {
  background: var(--color-primary-hover);
}

/* Main Content */
.secrets-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.content-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-5) var(--spacing-6);
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
}

.header-left h2 {
  margin: var(--spacing-0);
  font-size: var(--text-xl);
  font-weight: 600;
  color: var(--text-primary);
}

.header-left .subtitle {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.header-actions {
  display: flex;
  gap: var(--spacing-2);
}

.btn-icon {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  border: none;
  border-radius: var(--radius-lg);
  cursor: pointer;
  color: var(--text-secondary);
  transition: all var(--duration-150);
}

.btn-icon:hover {
  background: var(--bg-hover);
}

.btn-icon:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Stats Bar */
.stats-bar {
  display: flex;
  gap: var(--spacing-6);
  padding: var(--spacing-4) var(--spacing-6);
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
}

.stat-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.stat-item i {
  color: var(--text-muted);
  font-size: var(--text-sm);
}

.stat-item .stat-value {
  font-weight: 600;
  color: var(--text-primary);
}

.stat-item .stat-label {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.stat-item.warning {
  color: var(--color-warning);
}

.stat-item.warning i,
.stat-item.warning .stat-value {
  color: var(--color-warning);
}

/* Loading */
.loading-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-4);
  color: var(--text-tertiary);
}

/* Credentials Container */
.credentials-container {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-6);
}

.credentials-container.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: var(--spacing-4);
  align-content: start;
}

.credentials-container.list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

/* Credential Card */
.credential-card {
  display: flex;
  gap: var(--spacing-4);
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  cursor: pointer;
  transition: all var(--duration-200);
}

.credential-card:hover {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-md);
}

.credential-card.selected {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.credential-card.expired {
  border-left: 3px solid var(--color-error);
}

.card-icon {
  width: 48px;
  height: 48px;
  min-width: 48px;
  border-radius: var(--radius-xl);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-on-primary);
  font-size: var(--text-lg);
}

.card-content {
  flex: 1;
  min-width: 0;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-1-5);
}

.card-header h4 {
  margin: var(--spacing-0);
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-badges {
  display: flex;
  gap: var(--spacing-1-5);
  flex-shrink: 0;
}

.badge {
  font-size: var(--text-xs);
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-default);
  font-weight: 500;
  text-transform: capitalize;
}

.badge.general {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.badge.chat {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.badge.expired {
  background: var(--color-error-bg);
  color: var(--color-error);
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
}

/* Issue #685: Visibility badge styles */
.badge.visibility {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
}

.badge.visibility-private {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.badge.visibility-shared {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.badge.visibility-group {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.badge.visibility-organization {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.badge.visibility-system {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.card-description {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-2);
  font-size: var(--text-sm);
  color: var(--text-tertiary);
  line-height: 1.4;
}

.card-meta {
  display: flex;
  gap: var(--spacing-4);
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.meta-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
}

.meta-item.text-warning {
  color: var(--color-warning);
}

.card-tags {
  display: flex;
  gap: var(--spacing-1-5);
  margin-top: var(--spacing-2);
  flex-wrap: wrap;
}

.tag {
  font-size: var(--text-xs);
  padding: var(--spacing-0-5) var(--spacing-2);
  background: var(--bg-tertiary);
  border-radius: var(--radius-default);
  color: var(--text-secondary);
}

.tag.more {
  color: var(--color-primary);
}

.card-workflow-usage {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  flex-wrap: wrap;
  margin-top: var(--spacing-1-5);
}

.usage-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
}

.usage-tag {
  font-size: var(--text-xs);
  padding: var(--spacing-0-5) var(--spacing-2);
  background: var(--color-primary-bg);
  color: var(--color-primary);
  border-radius: var(--radius-xl);
}

.card-actions {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
  opacity: 0;
  transition: opacity var(--duration-150);
}

.credential-card:hover .card-actions {
  opacity: 1;
}

.action-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  color: var(--text-secondary);
  transition: all var(--duration-150);
}

.action-btn:hover {
  background: var(--bg-hover);
  color: var(--color-primary);
}

.action-btn.delete:hover {
  background: var(--color-error-bg);
  color: var(--color-error);
}

/* Templates Section */
.templates-section {
  padding: var(--spacing-6);
}

.templates-section h3 {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-2);
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.templates-section h3 i {
  color: var(--color-primary);
}

.templates-subtitle {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-5);
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.templates-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--spacing-3);
}

.template-card {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3-5);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  cursor: pointer;
  transition: all var(--duration-200);
}

.template-card:hover {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-sm);
}

.template-icon {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-on-primary);
  font-size: var(--text-base);
}

.template-info h4 {
  margin: var(--spacing-0);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.template-info p {
  margin: var(--spacing-0-5) var(--spacing-0) var(--spacing-0);
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

/* Form Styles */
.credential-form {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-5);
}

.template-selection h4 {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-4);
  font-size: 15px;
  font-weight: 600;
  color: var(--text-secondary);
}

.type-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: var(--spacing-3);
}

.type-option {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-2-5);
  padding: var(--spacing-4);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  cursor: pointer;
  transition: all var(--duration-200);
}

.type-option:hover {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.type-option .type-icon {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-xl);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-on-primary);
  font-size: var(--text-lg);
}

.type-option span {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  text-align: center;
}

.selected-type {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3);
  background: var(--bg-tertiary);
  border-radius: var(--radius-xl);
  margin-bottom: var(--spacing-2);
}

.selected-type .type-icon {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-on-primary);
  font-size: var(--text-base);
}

.selected-type .type-info {
  display: flex;
  flex-direction: column;
}

.selected-type .type-label {
  font-weight: 600;
  color: var(--text-primary);
}

.selected-type .change-type {
  background: none;
  border: none;
  padding: var(--spacing-0);
  font-size: var(--text-xs);
  color: var(--color-primary);
  cursor: pointer;
}

.form-fields {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.form-row {
  display: flex;
  gap: var(--spacing-4);
}

.form-row.two-col > .form-group {
  flex: 1;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1-5);
  flex: 1;
}

.form-group label {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-secondary);
}

.required {
  color: var(--color-error);
}

.form-input {
  padding: var(--spacing-2-5) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  transition: all var(--duration-200);
  background: var(--bg-input);
  color: var(--text-primary);
}

.form-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.input-hint {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.secret-input-wrapper {
  position: relative;
}

.secret-input {
  padding-right: var(--touch-target-min);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
}

.secret-masked {
  -webkit-text-security: disc;
  text-security: disc;
  color: var(--text-tertiary);
}

.toggle-visibility {
  position: absolute;
  right: 8px;
  top: 8px;
  background: var(--bg-tertiary);
  border: none;
  border-radius: var(--radius-md);
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-tertiary);
}

.scope-selector {
  display: flex;
  gap: var(--spacing-3);
}

.scope-option {
  flex: 1;
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-3);
  padding: var(--spacing-3-5);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  cursor: pointer;
  transition: all var(--duration-200);
}

.scope-option:hover {
  border-color: var(--color-primary);
}

.scope-option.active {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.scope-option input[type="radio"] {
  display: none;
}

.scope-option i {
  font-size: var(--text-xl);
  color: var(--text-muted);
  margin-top: var(--spacing-0-5);
}

.scope-option.active i {
  color: var(--color-primary);
}

.scope-option > div {
  display: flex;
  flex-direction: column;
}

.scope-option span {
  font-weight: 500;
  color: var(--text-primary);
}

.scope-option small {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  margin-top: var(--spacing-0-5);
}

/* View Modal */
.view-credential {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-5);
}

.view-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  padding-bottom: var(--spacing-4);
  border-bottom: 1px solid var(--border-default);
}

.view-icon {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-xl);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-on-primary);
  font-size: var(--text-2xl);
}

.view-title h3 {
  margin: var(--spacing-0);
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
}

.view-type {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.view-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.view-section label {
  font-size: var(--text-xs);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-tertiary);
}

.view-section p {
  margin: var(--spacing-0);
  color: var(--text-primary);
}

.secret-display {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3);
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
}

.secret-display code {
  flex: 1;
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  word-break: break-all;
  color: var(--text-primary);
}

.secret-actions {
  display: flex;
  gap: var(--spacing-1);
}

.view-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-4);
}

.view-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.view-item label {
  font-size: var(--text-xs);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-tertiary);
}

.view-item span {
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
}

.text-danger {
  color: var(--color-error) !important;
}

.text-warning {
  color: var(--color-warning) !important;
}

/* Transfer & Delete Modals */
.transfer-content,
.delete-content {
  text-align: center;
  padding: var(--spacing-5) var(--spacing-0);
}

.transfer-icon,
.delete-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto 16px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
}

.transfer-icon {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.delete-icon {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.transfer-content h4,
.delete-content h4 {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-2);
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
}

.transfer-content p,
.delete-content p {
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-4);
  color: var(--text-secondary);
}

.transfer-warning,
.delete-warning {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2-5) var(--spacing-4);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
}

.transfer-warning {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.delete-warning {
  background: var(--color-error-bg);
  color: var(--color-error);
}

/* Buttons */
.btn-primary {
  padding: var(--spacing-2-5) var(--spacing-5);
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  transition: all var(--duration-200);
}

.btn-primary:hover {
  background: var(--color-primary-hover);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  padding: var(--spacing-2-5) var(--spacing-5);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: none;
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration-200);
}

.btn-secondary:hover {
  background: var(--bg-hover);
}

.btn-danger {
  padding: var(--spacing-2-5) var(--spacing-5);
  background: var(--color-error);
  color: var(--text-on-error);
  border: none;
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  transition: all var(--duration-200);
}

.btn-danger:hover {
  background: var(--color-error-hover);
}

.btn-danger:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Infrastructure Host Form Styles */
.capability-checkboxes {
  display: flex;
  gap: var(--spacing-4);
  flex-wrap: wrap;
}

.checkbox-option {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2-5) var(--spacing-4);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all var(--duration-150);
  user-select: none;
}

.checkbox-option:hover {
  background: var(--bg-hover);
  border-color: var(--color-primary);
}

.checkbox-option input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: var(--color-primary);
}

.checkbox-option input[type="checkbox"]:disabled {
  cursor: default;
}

.checkbox-option:has(input:checked) {
  background: var(--color-primary-bg);
  border-color: var(--color-primary);
}

.checkbox-option:has(input:disabled) {
  opacity: 0.7;
  cursor: default;
}

.checkbox-option i {
  font-size: var(--text-sm);
  color: var(--text-muted);
}

.checkbox-option:has(input:checked) i {
  color: var(--color-primary);
}

.checkbox-option span {
  font-size: var(--text-sm);
  color: var(--text-primary);
  font-weight: 500;
}

/* Responsive */
@media (max-width: 768px) {
  .secrets-manager-n8n {
    flex-direction: column;
  }

  .secrets-sidebar {
    width: 100%;
    min-width: 100%;
    max-height: 50vh;
  }

  .credentials-container.grid {
    grid-template-columns: 1fr;
  }

  .form-row.two-col {
    flex-direction: column;
  }

  .scope-selector {
    flex-direction: column;
  }

  .view-grid {
    grid-template-columns: 1fr;
  }
}
</style>
