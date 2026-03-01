<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition duration-300 ease-out"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition duration-200 ease-in"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="visible"
        class="fixed inset-0 z-50 overflow-y-auto"
        @click.self="handleOverlayClick"
        @keydown.escape="handleClose"
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-node-modal-title"
      >
        <div class="flex min-h-full items-end justify-center p-4 text-center sm:items-center sm:p-0">
          <!-- Background overlay -->
          <div class="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity" aria-hidden="true"></div>

          <!-- Modal panel -->
          <div
            @click.stop
            class="relative transform overflow-hidden rounded-lg bg-white text-left shadow-xl transition-all sm:my-8 sm:w-full sm:max-w-2xl"
          >
            <!-- Header -->
            <div class="flex items-center justify-between border-b border-gray-200 px-6 py-4">
              <h3 id="add-node-modal-title" class="text-lg font-semibold text-gray-900">{{ modalTitle }}</h3>
              <button
                @click="handleClose"
                :disabled="isSubmitting"
                class="rounded-md text-gray-400 hover:text-gray-600 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50"
                aria-label="Close dialog"
              >
                <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <!-- Replace Mode Warning -->
            <div v-if="isReplaceMode" class="mx-6 mt-4 p-3 bg-yellow-100 border border-yellow-300 rounded-lg" role="alert">
              <div class="flex items-start gap-3">
                <svg class="h-5 w-5 text-yellow-600 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <div>
                  <p class="text-sm font-medium text-yellow-800">You are replacing an existing node</p>
                  <p class="text-sm text-yellow-700 mt-1">
                    Node <span class="font-medium">{{ existingNode?.hostname }}</span> will be removed and replaced with the new node configuration.
                    This action cannot be undone.
                  </p>
                </div>
              </div>
            </div>

            <!-- Form Content -->
            <div class="px-6 py-4 max-h-[70vh] overflow-y-auto">
              <form @submit.prevent="handleSubmit" class="space-y-6">

                <!-- Connection Information Section -->
                <fieldset class="space-y-4">
                  <legend class="flex items-center gap-2 text-sm font-semibold text-gray-700 border-b border-gray-100 pb-2">
                    <svg class="h-4 w-4 text-primary-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
                    </svg>
                    Connection Information
                  </legend>

                  <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <!-- Hostname -->
                    <div class="sm:col-span-1">
                      <label for="hostname" class="block text-sm font-medium text-gray-700 mb-1">
                        Hostname <span class="text-danger-500" aria-hidden="true">*</span>
                        <span class="sr-only">(required)</span>
                      </label>
                      <input
                        v-model="formData.hostname"
                        type="text"
                        id="hostname"
                        :class="['input', { 'border-danger-500 focus:ring-danger-500 focus:border-danger-500': errors.hostname }]"
                        placeholder="e.g., npu-worker-02"
                        aria-required="true"
                        :aria-invalid="!!errors.hostname"
                        :aria-describedby="errors.hostname ? 'hostname-error' : undefined"
                        @blur="validateField('hostname')"
                      />
                      <p v-if="errors.hostname" id="hostname-error" class="mt-1 text-xs text-danger-500" role="alert">{{ errors.hostname }}</p>
                    </div>

                    <!-- IP Address -->
                    <div class="sm:col-span-1">
                      <label for="ip_address" class="block text-sm font-medium text-gray-700 mb-1">
                        IP Address <span class="text-danger-500" aria-hidden="true">*</span>
                        <span class="sr-only">(required)</span>
                      </label>
                      <input
                        v-model="formData.ip_address"
                        type="text"
                        id="ip_address"
                        :class="['input', { 'border-danger-500 focus:ring-danger-500 focus:border-danger-500': errors.ip_address }]"
                        placeholder="e.g., 172.16.168.26"
                        aria-required="true"
                        :aria-invalid="!!errors.ip_address"
                        :aria-describedby="errors.ip_address ? 'ip-error' : undefined"
                        @blur="validateField('ip_address')"
                      />
                      <p v-if="errors.ip_address" id="ip-error" class="mt-1 text-xs text-danger-500" role="alert">{{ errors.ip_address }}</p>
                    </div>

                    <!-- SSH Port -->
                    <div class="sm:col-span-1">
                      <label for="ssh_port" class="block text-sm font-medium text-gray-700 mb-1">
                        SSH Port
                      </label>
                      <input
                        v-model.number="formData.ssh_port"
                        type="number"
                        id="ssh_port"
                        min="1"
                        max="65535"
                        class="input"
                        placeholder="22"
                      />
                    </div>
                  </div>
                </fieldset>

                <!-- Authentication Method Section -->
                <fieldset class="space-y-4">
                  <legend class="flex items-center gap-2 text-sm font-semibold text-gray-700 border-b border-gray-100 pb-2">
                    <svg class="h-4 w-4 text-primary-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                    </svg>
                    Authentication Method
                  </legend>

                  <!-- Auth Method Selection -->
                  <div class="flex gap-4" role="radiogroup" aria-label="Authentication method">
                    <label
                      :class="[
                        'flex-1 flex items-center gap-3 p-4 border-2 rounded-lg cursor-pointer transition-all',
                        formData.auth_method === 'password'
                          ? 'border-primary-500 bg-primary-50'
                          : 'border-gray-200 hover:border-gray-300 bg-white'
                      ]"
                    >
                      <input
                        type="radio"
                        v-model="formData.auth_method"
                        value="password"
                        class="sr-only"
                      />
                      <div class="flex items-center justify-center w-10 h-10 bg-primary-100 rounded-lg" aria-hidden="true">
                        <svg class="h-5 w-5 text-primary-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                        </svg>
                      </div>
                      <div>
                        <p class="font-medium text-gray-900">Password</p>
                        <p class="text-xs text-gray-500">Sudo user with password</p>
                      </div>
                    </label>

                    <label
                      :class="[
                        'flex-1 flex items-center gap-3 p-4 border-2 rounded-lg cursor-pointer transition-all',
                        formData.auth_method === 'pki'
                          ? 'border-primary-500 bg-primary-50'
                          : 'border-gray-200 hover:border-gray-300 bg-white'
                      ]"
                    >
                      <input
                        type="radio"
                        v-model="formData.auth_method"
                        value="pki"
                        class="sr-only"
                      />
                      <div class="flex items-center justify-center w-10 h-10 bg-primary-100 rounded-lg" aria-hidden="true">
                        <svg class="h-5 w-5 text-primary-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                        </svg>
                      </div>
                      <div>
                        <p class="font-medium text-gray-900">PKI (SSH Key)</p>
                        <p class="text-xs text-gray-500">Recommended for production</p>
                      </div>
                    </label>
                  </div>

                  <!-- Password Auth Fields -->
                  <div v-if="formData.auth_method === 'password'" class="p-4 bg-gray-50 rounded-lg space-y-4">
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <!-- SSH User -->
                      <div>
                        <label for="ssh_user" class="block text-sm font-medium text-gray-700 mb-1">
                          Username <span class="text-danger-500" aria-hidden="true">*</span>
                          <span class="sr-only">(required)</span>
                        </label>
                        <input
                          v-model="formData.ssh_user"
                          type="text"
                          id="ssh_user"
                          class="input"
                          placeholder="autobot"
                          aria-required="true"
                        />
                      </div>

                      <!-- Password -->
                      <div>
                        <label for="ssh_password" class="block text-sm font-medium text-gray-700 mb-1">
                          Password
                          <span v-if="!isEditMode || needsCredentialsForEdit" class="text-danger-500" aria-hidden="true">*</span>
                          <span v-if="!isEditMode || needsCredentialsForEdit" class="sr-only">(required)</span>
                          <span v-else class="text-gray-400 text-xs ml-1">(optional)</span>
                        </label>
                        <div class="relative">
                          <input
                            v-model="formData.ssh_password"
                            :type="showPassword ? 'text' : 'password'"
                            id="ssh_password"
                            :class="['input pr-10', { 'border-danger-500 focus:ring-danger-500 focus:border-danger-500': errors.ssh_password }]"
                            :placeholder="isEditMode && !needsCredentialsForEdit ? 'Leave empty for basic edit' : 'Enter password'"
                            :aria-required="!isEditMode || needsCredentialsForEdit ? 'true' : undefined"
                            :aria-invalid="!!errors.ssh_password"
                            :aria-describedby="errors.ssh_password ? 'password-error' : undefined"
                            @blur="validateField('ssh_password')"
                          />
                          <button
                            type="button"
                            @click="showPassword = !showPassword"
                            class="absolute inset-y-0 right-0 flex items-center pr-3 text-gray-400 hover:text-gray-600"
                            :aria-label="showPassword ? 'Hide password' : 'Show password'"
                            :aria-pressed="showPassword"
                          >
                            <svg v-if="!showPassword" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                            </svg>
                            <svg v-else class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                            </svg>
                          </button>
                        </div>
                        <p v-if="errors.ssh_password" id="password-error" class="mt-1 text-xs text-danger-500" role="alert">{{ errors.ssh_password }}</p>
                      </div>
                    </div>

                    <!-- Has Sudo -->
                    <label class="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        v-model="formData.has_sudo"
                        class="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                      />
                      <span class="text-sm text-gray-700">User has sudo privileges</span>
                    </label>
                  </div>

                  <!-- PKI Auth Fields -->
                  <div v-if="formData.auth_method === 'pki'" class="p-4 bg-gray-50 rounded-lg space-y-4">
                    <!-- SSH User -->
                    <div>
                      <label for="ssh_user_pki" class="block text-sm font-medium text-gray-700 mb-1">
                        Username <span class="text-danger-500" aria-hidden="true">*</span>
                        <span class="sr-only">(required)</span>
                      </label>
                      <input
                        v-model="formData.ssh_user"
                        type="text"
                        id="ssh_user_pki"
                        class="input"
                        placeholder="autobot"
                        aria-required="true"
                      />
                    </div>

                    <!-- Key Source Selection -->
                    <div>
                      <label class="block text-sm font-medium text-gray-700 mb-2">SSH Key Source</label>
                      <div class="space-y-2" role="radiogroup" aria-label="SSH key source">
                        <label
                          v-for="option in keySourceOptions"
                          :key="option.value"
                          :class="[
                            'flex items-center gap-3 p-3 border rounded-lg cursor-pointer transition-all',
                            keySource === option.value
                              ? 'border-primary-500 bg-primary-50'
                              : 'border-gray-200 hover:border-gray-300'
                          ]"
                        >
                          <input
                            type="radio"
                            v-model="keySource"
                            :value="option.value"
                            class="w-4 h-4 text-primary-600 border-gray-300 focus:ring-primary-500"
                          />
                          <span class="text-sm text-gray-700">{{ option.label }}</span>
                        </label>
                      </div>
                    </div>

                    <!-- Key Path (for browse) -->
                    <div v-if="keySource === 'browse'">
                      <label for="ssh_key_path" class="block text-sm font-medium text-gray-700 mb-1">
                        Key Path
                      </label>
                      <input
                        v-model="formData.ssh_key_path"
                        type="text"
                        id="ssh_key_path"
                        class="input"
                        placeholder="/path/to/private_key"
                      />
                    </div>

                    <!-- Key Content (for paste) -->
                    <div v-if="keySource === 'paste'">
                      <label for="ssh_key" class="block text-sm font-medium text-gray-700 mb-1">
                        SSH Private Key
                      </label>
                      <textarea
                        v-model="formData.ssh_key"
                        id="ssh_key"
                        rows="5"
                        :class="['input font-mono text-xs', { 'border-danger-500 focus:ring-danger-500 focus:border-danger-500': errors.ssh_key }]"
                        placeholder="-----BEGIN OPENSSH PRIVATE KEY-----&#10;...&#10;-----END OPENSSH PRIVATE KEY-----"
                        :aria-invalid="!!errors.ssh_key"
                        :aria-describedby="errors.ssh_key ? 'ssh-key-error' : undefined"
                        @blur="validateField('ssh_key')"
                      ></textarea>
                      <p v-if="errors.ssh_key" id="ssh-key-error" class="mt-1 text-xs text-danger-500" role="alert">{{ errors.ssh_key }}</p>
                    </div>
                  </div>
                </fieldset>

                <!-- Role Assignment Section -->
                <fieldset class="space-y-4">
                  <legend class="flex items-center gap-2 text-sm font-semibold text-gray-700 border-b border-gray-100 pb-2">
                    <svg class="h-4 w-4 text-primary-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                    </svg>
                    Role Assignment
                  </legend>

                  <div class="grid grid-cols-1 sm:grid-cols-2 gap-3" role="group" aria-label="Available roles">
                    <label
                      v-for="role in availableRoles"
                      :key="role.id"
                      :class="[
                        'flex items-start gap-3 p-3 border rounded-lg cursor-pointer transition-all',
                        formData.roles.includes(role.id)
                          ? 'border-primary-500 bg-primary-50'
                          : 'border-gray-200 hover:border-gray-300'
                      ]"
                    >
                      <input
                        type="checkbox"
                        :value="role.id"
                        v-model="formData.roles"
                        class="mt-0.5 w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                        :aria-label="`${role.name}: ${role.description}`"
                      />
                      <div>
                        <p class="font-medium text-gray-900 text-sm">{{ role.name }}</p>
                        <p class="text-xs text-gray-500">{{ role.description }}</p>
                      </div>
                    </label>
                  </div>
                  <p v-if="errors.roles" class="text-xs text-danger-500" role="alert">{{ errors.roles }}</p>

                  <!-- Selected Roles Details -->
                  <div v-if="selectedRolesDetails.length > 0" class="p-3 bg-gray-50 rounded-lg" role="status">
                    <p class="text-xs font-medium text-gray-600 mb-2">Selected roles will configure:</p>
                    <div class="space-y-1">
                      <div v-for="role in selectedRolesDetails" :key="role.id" class="flex items-center gap-2 text-xs">
                        <span class="w-2 h-2 bg-primary-500 rounded-full" aria-hidden="true"></span>
                        <span class="text-gray-700">{{ role.name }}: {{ role.services?.join(', ') || 'No services' }}</span>
                        <span v-if="role.default_port" class="text-gray-500">(Port {{ role.default_port }})</span>
                      </div>
                    </div>
                  </div>
                </fieldset>

                <!-- Enrollment Options Section -->
                <fieldset class="space-y-4">
                  <legend class="flex items-center gap-2 text-sm font-semibold text-gray-700 border-b border-gray-100 pb-2">
                    <svg class="h-4 w-4 text-primary-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                    {{ isEditMode ? 'Update Options' : 'Enrollment Options' }}
                  </legend>

                  <!-- Add/Replace Mode Options -->
                  <div v-if="!isEditMode" class="space-y-3">
                    <!-- Import Existing Node Option -->
                    <label class="flex items-start gap-3 cursor-pointer">
                      <input
                        type="checkbox"
                        v-model="formData.import_existing"
                        class="mt-0.5 w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                      />
                      <div>
                        <span class="text-sm text-gray-700 font-medium">Import existing node (no deployment)</span>
                        <p class="text-xs text-gray-500 mt-0.5">
                          Register an already-configured node without running Ansible. Use this for nodes that already have services running. The node will be marked as healthy immediately.
                        </p>
                      </div>
                    </label>

                    <div v-if="!formData.import_existing" class="pl-4 border-l-2 border-gray-200 space-y-3">
                      <label class="flex items-start gap-3 cursor-pointer">
                        <input
                          type="checkbox"
                          v-model="formData.auto_enroll"
                          class="mt-0.5 w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                        />
                        <div>
                          <span class="text-sm text-gray-700">Start enrollment immediately after adding</span>
                          <p class="text-xs text-gray-500 mt-0.5">
                            The node will be automatically enrolled with Ansible after being added, including installing dependencies and configuring services.
                          </p>
                        </div>
                      </label>

                      <label v-if="formData.auth_method === 'password'" class="flex items-start gap-3 cursor-pointer">
                        <input
                          type="checkbox"
                          v-model="formData.deploy_pki"
                          class="mt-0.5 w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                        />
                        <div>
                          <span class="text-sm text-gray-700">Deploy PKI certificates during enrollment</span>
                          <p class="text-xs text-gray-500 mt-0.5">
                            SSH keys will be deployed to the node for passwordless authentication in future connections.
                          </p>
                        </div>
                      </label>
                    </div>
                  </div>

                  <!-- Edit Mode Options -->
                  <div v-if="isEditMode" class="space-y-3">
                    <!-- Info: PKI auth - no password ever needed -->
                    <div v-if="formData.auth_method === 'pki'" class="flex items-start gap-3 p-3 bg-blue-50 border border-blue-200 rounded-lg" role="status">
                      <svg class="h-5 w-5 text-blue-600 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                      </svg>
                      <p class="text-sm text-blue-700">
                        Using SSH key authentication. No password required.
                      </p>
                    </div>
                    <!-- Info: Password auth - credentials optional for basic edits -->
                    <div v-else-if="!needsCredentialsForEdit" class="flex items-start gap-3 p-3 bg-green-50 border border-green-200 rounded-lg" role="status">
                      <svg class="h-5 w-5 text-green-600 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      <p class="text-sm text-green-700">
                        Password not required for basic edits. Enable options below if you need SSH access.
                      </p>
                    </div>
                    <!-- Info: Password auth with SSH ops - password required -->
                    <div v-else class="flex items-start gap-3 p-3 bg-amber-50 border border-amber-200 rounded-lg" role="alert">
                      <svg class="h-5 w-5 text-amber-600 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                      </svg>
                      <p class="text-sm text-amber-700">
                        Password required for selected SSH operations.
                      </p>
                    </div>

                    <label class="flex items-start gap-3 cursor-pointer">
                      <input
                        type="checkbox"
                        v-model="formData.deploy_pki"
                        class="mt-0.5 w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                      />
                      <div>
                        <span class="text-sm text-gray-700">Deploy PKI certificates after update</span>
                        <p class="text-xs text-gray-500 mt-0.5">
                          If a password is provided, it will be used to connect and deploy PKI certificates.
                        </p>
                      </div>
                    </label>

                    <label class="flex items-start gap-3 cursor-pointer">
                      <input
                        type="checkbox"
                        v-model="formData.run_enrollment"
                        class="mt-0.5 w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                      />
                      <div>
                        <span class="text-sm text-gray-700">Re-run enrollment tasks</span>
                        <p class="text-xs text-gray-500 mt-0.5">
                          Run Ansible enrollment to update dependencies and services on the node.
                        </p>
                      </div>
                    </label>
                  </div>

                  <!-- PKI Migration Notice -->
                  <div v-if="isEditMode && formData.auth_method === 'password' && formData.ssh_password" class="flex items-start gap-3 p-3 bg-blue-50 border border-blue-200 rounded-lg" role="status">
                    <svg class="h-5 w-5 text-blue-600 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <p class="text-sm text-blue-700">
                      Password will be used to establish connection and deploy PKI certificates.
                    </p>
                  </div>
                </fieldset>

                <!-- Replace Confirmation (for replace mode) -->
                <div v-if="isReplaceMode" class="space-y-3">
                  <label class="flex items-start gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      v-model="replaceConfirmed"
                      class="mt-0.5 w-4 h-4 text-danger-500 border-gray-300 rounded focus:ring-danger-500"
                    />
                    <div>
                      <span class="text-sm text-gray-700 font-medium">
                        I understand that this will permanently remove the existing node
                      </span>
                      <p class="text-xs text-gray-500 mt-0.5">
                        All configuration and history for <span class="font-medium">{{ existingNode?.hostname }}</span> will be deleted.
                      </p>
                    </div>
                  </label>
                </div>

                <!-- Connection Test Result -->
                <div v-if="testResult" :class="[
                  'flex items-start gap-3 p-3 rounded-lg border',
                  testResult.success
                    ? 'bg-green-50 border-green-200'
                    : 'bg-red-50 border-red-200'
                ]" :role="testResult.success ? 'status' : 'alert'">
                  <svg
                    :class="[
                      'h-5 w-5 mt-0.5 flex-shrink-0',
                      testResult.success ? 'text-green-600' : 'text-red-600'
                    ]"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    aria-hidden="true"
                  >
                    <path
                      v-if="testResult.success"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      stroke-width="2"
                      d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                    />
                    <path
                      v-else
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      stroke-width="2"
                      d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
                    />
                  </svg>
                  <div>
                    <p :class="['font-medium text-sm', testResult.success ? 'text-green-800' : 'text-red-800']">
                      {{ testResult.success ? 'Connection Successful' : 'Connection Failed' }}
                    </p>
                    <p :class="['text-sm', testResult.success ? 'text-green-700' : 'text-red-700']">
                      {{ testResult.message }}
                    </p>
                  </div>
                </div>

                <!-- Error Message -->
                <div
                  v-if="error"
                  class="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm"
                  role="alert"
                >
                  {{ error }}
                </div>

                <!-- Success Message -->
                <div
                  v-if="success"
                  class="p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm"
                  role="status"
                >
                  {{ success }}
                </div>
              </form>
            </div>

            <!-- Actions Footer -->
            <div class="flex items-center justify-between gap-3 px-6 py-4 border-t border-gray-200 bg-gray-50">
              <button
                type="button"
                @click="handleClose"
                :disabled="isSubmitting"
                class="btn btn-secondary"
              >
                Cancel
              </button>

              <div class="flex items-center gap-3">
                <button
                  type="button"
                  @click="testConnection"
                  :disabled="!canTest || isTesting"
                  class="btn btn-secondary flex items-center gap-2"
                >
                  <svg v-if="isTesting" class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <svg v-else class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  {{ isTesting ? 'Testing...' : 'Test Connection' }}
                </button>

                <button
                  type="button"
                  @click="handleSubmit"
                  :disabled="!canSubmit || isSubmitting"
                  :class="[
                    'btn flex items-center gap-2',
                    isReplaceMode ? 'btn-danger' : 'btn-primary'
                  ]"
                >
                  <svg v-if="isSubmitting" class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <svg v-else-if="isEditMode" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
                  </svg>
                  <svg v-else class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                  </svg>
                  {{ submitButtonText }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * AddNodeModal - Modal for adding, editing, or replacing fleet nodes.
 *
 * Issue #754: Added role="dialog", aria-modal, aria-labelledby,
 * @keydown.escape, aria-hidden on decorative elements,
 * aria-label/aria-pressed on password toggle, aria-required/aria-invalid
 * on required fields, aria-describedby linking errors to inputs,
 * role="alert" on error messages, role="status" on info/success,
 * role="radiogroup" on auth method and key source, fieldset/legend
 * on form sections, role="group" on role checkboxes,
 * sr-only text for required indicators.
 */

import { ref, computed, watch, onMounted } from 'vue'
import { useSlmApi } from '@/composables/useSlmApi'
import type { NodeRole, RoleInfo } from '@/types/slm'

// Types
interface NodeRoleOption {
  id: NodeRole
  name: string
  description: string
  category: string
  services?: string[]
  default_port?: number
}

interface ExistingNode {
  node_id: string
  hostname: string
  ip_address: string
  ssh_user?: string
  ssh_port?: number
  auth_method?: 'password' | 'pki'
  roles: NodeRole[]
}

interface FormData {
  hostname: string
  ip_address: string
  ssh_port: number
  auth_method: 'password' | 'pki'
  ssh_user: string
  ssh_password: string
  has_sudo: boolean
  ssh_key: string
  ssh_key_path: string
  roles: NodeRole[]
  import_existing: boolean
  auto_enroll: boolean
  deploy_pki: boolean
  run_enrollment: boolean
}

interface TestResult {
  success: boolean
  message: string
}

type ModalMode = 'add' | 'edit' | 'replace'

// Props
const props = withDefaults(defineProps<{
  visible: boolean
  mode?: ModalMode
  existingNode?: ExistingNode | null
}>(), {
  mode: 'add',
  existingNode: null,
})

// Emits
const emit = defineEmits<{
  close: []
  added: [node: unknown]
  updated: [node: unknown]
  replaced: [data: { oldNodeId: string; newNode: unknown }]
}>()

// API
const api = useSlmApi()

// Available roles fetched from backend
const availableRoles = ref<NodeRoleOption[]>([])
const isLoadingRoles = ref(false)

// Fetch roles from backend
async function fetchRoles() {
  isLoadingRoles.value = true
  try {
    const roles = await api.getRoles()
    availableRoles.value = roles.map((role: RoleInfo) => ({
      id: role.name,
      name: formatRoleName(role.name),
      description: role.description,
      category: role.category,
      default_port: typeof role.variables?.port === 'number' ? role.variables.port : undefined,
    }))
  } catch (e) {
    // Fallback to node-roles constants if API fails
    const { NODE_ROLE_METADATA } = await import('@/constants/node-roles')
    availableRoles.value = Object.values(NODE_ROLE_METADATA).map((meta) => ({
      id: meta.name,
      name: meta.displayName,
      description: meta.description,
      category: meta.category,
    }))
  } finally {
    isLoadingRoles.value = false
  }
}

// Format role name for display
function formatRoleName(name: string): string {
  return name
    .split('-')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

// Fetch roles on mount
onMounted(() => {
  fetchRoles()
})

// Key source options
const keySourceOptions = [
  { value: 'default', label: 'Use default key (~/.ssh/autobot_key)' },
  { value: 'browse', label: 'Browse for key file' },
  { value: 'paste', label: 'Paste key content' },
] as const

// State
const isSubmitting = ref(false)
const isTesting = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)
const testResult = ref<TestResult | null>(null)
const showPassword = ref(false)
const keySource = ref<'default' | 'browse' | 'paste'>('default')
const replaceConfirmed = ref(false)
const errors = ref<Record<string, string>>({})

const formData = ref<FormData>({
  hostname: '',
  ip_address: '',
  ssh_user: 'autobot',
  ssh_port: 22,
  auth_method: 'password',
  ssh_password: '',
  has_sudo: true,
  ssh_key: '',
  ssh_key_path: '',
  roles: [],
  import_existing: false,
  auto_enroll: false,
  deploy_pki: true,
  run_enrollment: false,
})

// Computed
const isEditMode = computed(() => props.mode === 'edit')
const isReplaceMode = computed(() => props.mode === 'replace')

const modalTitle = computed(() => {
  if (isEditMode.value) return 'Edit Node'
  if (isReplaceMode.value) return `Replace Node: ${props.existingNode?.hostname || ''}`
  return 'Add New Node'
})

const submitButtonText = computed(() => {
  if (isSubmitting.value) {
    if (isEditMode.value) return 'Saving...'
    if (isReplaceMode.value) return 'Replacing...'
    return 'Adding...'
  }
  if (isEditMode.value) return 'Save Changes'
  if (isReplaceMode.value) return 'Replace Node'
  return 'Add Node'
})

const selectedRolesDetails = computed(() => {
  return availableRoles.value.filter(role => formData.value.roles.includes(role.id))
})

const canTest = computed(() => {
  return (
    formData.value.hostname.trim() !== '' &&
    formData.value.ip_address.trim() !== '' &&
    formData.value.ssh_user.trim() !== '' &&
    (formData.value.auth_method === 'pki' ||
      (formData.value.auth_method === 'password' && formData.value.ssh_password.trim() !== ''))
  )
})

// In edit mode, password only needed if SSH operations requested AND using password auth
// PKI auth uses SSH key - no password ever needed
const needsCredentialsForEdit = computed(() => {
  const sshOpsRequested = formData.value.deploy_pki || formData.value.run_enrollment
  const usingPasswordAuth = formData.value.auth_method === 'password'
  return sshOpsRequested && usingPasswordAuth
})

// Basic field validation without credentials check
const hasBasicFields = computed(() => {
  return (
    formData.value.hostname.trim() !== '' &&
    formData.value.ip_address.trim() !== '' &&
    formData.value.ssh_user.trim() !== '' &&
    formData.value.roles.length > 0 &&
    Object.keys(errors.value).length === 0
  )
})

const canSubmit = computed(() => {
  // Replace mode always needs full credentials
  if (isReplaceMode.value) {
    return canTest.value && hasBasicFields.value && replaceConfirmed.value
  }

  // Edit mode: credentials only required if SSH operations are requested
  if (isEditMode.value) {
    if (needsCredentialsForEdit.value) {
      // Need credentials for PKI deployment or re-enrollment
      return canTest.value && hasBasicFields.value
    }
    // Simple edit without SSH operations - no credentials needed
    return hasBasicFields.value
  }

  // Add mode always needs full credentials
  return canTest.value && hasBasicFields.value
})

// Watchers
watch(() => props.visible, (visible) => {
  if (visible) {
    if (props.mode === 'edit' && props.existingNode) {
      populateEditData()
    } else if (props.mode === 'replace' && props.existingNode) {
      populateReplaceData()
    } else {
      resetForm()
    }
  }
})

watch(() => props.existingNode, (node) => {
  if (props.visible && node) {
    if (props.mode === 'edit') {
      populateEditData()
    } else if (props.mode === 'replace') {
      populateReplaceData()
    }
  }
})

// Methods
function populateEditData() {
  if (!props.existingNode) return

  formData.value = {
    hostname: props.existingNode.hostname,
    ip_address: props.existingNode.ip_address,
    ssh_port: props.existingNode.ssh_port || 22,
    auth_method: props.existingNode.auth_method || 'password',
    ssh_user: props.existingNode.ssh_user || 'autobot',
    ssh_password: '',
    has_sudo: true,
    ssh_key: '',
    ssh_key_path: '',
    roles: [...props.existingNode.roles],
    import_existing: false,
    auto_enroll: false,
    deploy_pki: false,  // User must opt-in to SSH operations when editing
    run_enrollment: false,
  }

  errors.value = {}
  testResult.value = null
}

function populateReplaceData() {
  if (!props.existingNode) return

  formData.value = {
    hostname: '',
    ip_address: '',
    ssh_port: 22,
    auth_method: 'password',
    ssh_user: 'autobot',
    ssh_password: '',
    has_sudo: true,
    ssh_key: '',
    ssh_key_path: '',
    roles: [...props.existingNode.roles],
    import_existing: false,
    auto_enroll: false,
    deploy_pki: true,
    run_enrollment: false,
  }

  replaceConfirmed.value = false
  errors.value = {}
  testResult.value = null
}

function resetForm() {
  formData.value = {
    hostname: '',
    ip_address: '',
    ssh_user: 'autobot',
    ssh_port: 22,
    auth_method: 'password',
    ssh_password: '',
    has_sudo: true,
    ssh_key: '',
    ssh_key_path: '',
    roles: [],
    import_existing: false,
    auto_enroll: false,
    deploy_pki: true,
    run_enrollment: false,
  }
  error.value = null
  success.value = null
  testResult.value = null
  errors.value = {}
  showPassword.value = false
  keySource.value = 'default'
  replaceConfirmed.value = false
}

function validateField(field: string) {
  const value = formData.value[field as keyof FormData]

  switch (field) {
    case 'hostname':
      if (!value || (typeof value === 'string' && value.trim() === '')) {
        errors.value.hostname = 'Hostname is required'
      } else if (typeof value === 'string' && !/^[a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9]$|^[a-zA-Z0-9]$/.test(value)) {
        errors.value.hostname = 'Invalid hostname format'
      } else {
        delete errors.value.hostname
      }
      break

    case 'ip_address':
      if (!value || (typeof value === 'string' && value.trim() === '')) {
        errors.value.ip_address = 'IP address is required'
      } else if (typeof value === 'string' && !/^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/.test(value)) {
        errors.value.ip_address = 'Invalid IPv4 address'
      } else {
        delete errors.value.ip_address
      }
      break

    case 'ssh_password': {
      // In edit mode, password only required if SSH operations are requested
      const passwordRequired = isEditMode.value
        ? formData.value.auth_method === 'password' && needsCredentialsForEdit.value
        : formData.value.auth_method === 'password'

      if (passwordRequired && (!value || (typeof value === 'string' && value.trim() === ''))) {
        errors.value.ssh_password = 'Password is required for SSH operations'
      } else {
        delete errors.value.ssh_password
      }
      break
    }

    case 'ssh_key':
      if (formData.value.auth_method === 'pki' && keySource.value === 'paste' && (!value || (typeof value === 'string' && value.trim() === ''))) {
        errors.value.ssh_key = 'SSH key is required'
      } else {
        delete errors.value.ssh_key
      }
      break

    case 'roles':
      if (formData.value.roles.length === 0) {
        errors.value.roles = 'At least one role is required'
      } else {
        delete errors.value.roles
      }
      break
  }
}

function validateAll(): boolean {
  validateField('hostname')
  validateField('ip_address')
  validateField('roles')

  if (formData.value.auth_method === 'password') {
    validateField('ssh_password')
  } else if (keySource.value === 'paste') {
    validateField('ssh_key')
  }

  return Object.keys(errors.value).length === 0
}

function getSshKey(): string | undefined {
  if (formData.value.auth_method !== 'pki') return undefined

  switch (keySource.value) {
    case 'default':
      return undefined
    case 'browse':
      return formData.value.ssh_key_path || undefined
    case 'paste':
      return formData.value.ssh_key || undefined
    default:
      return undefined
  }
}

async function testConnection() {
  if (!canTest.value) return

  isTesting.value = true
  testResult.value = null

  try {
    const result = await api.testConnection({
      ip_address: formData.value.ip_address,
      ssh_port: formData.value.ssh_port,
      ssh_user: formData.value.ssh_user,
      auth_method: formData.value.auth_method,
      password: formData.value.auth_method === 'password' ? formData.value.ssh_password : undefined,
      ssh_key: getSshKey(),
    })

    testResult.value = {
      success: result.success,
      message: result.success
        ? `Successfully connected to ${formData.value.ip_address}. OS: ${result.os || 'Unknown'}`
        : result.error || 'Connection failed',
    }
  } catch (e) {
    testResult.value = {
      success: false,
      message: e instanceof Error ? e.message : 'Failed to test connection',
    }
  } finally {
    isTesting.value = false
  }
}

async function handleSubmit() {
  if (!validateAll()) return

  isSubmitting.value = true
  error.value = null

  try {
    // If importing existing, skip enrollment entirely
    const skipEnrollment = formData.value.import_existing

    const nodeData = {
      hostname: formData.value.hostname.trim(),
      ip_address: formData.value.ip_address.trim(),
      ssh_user: formData.value.ssh_user.trim(),
      ssh_port: formData.value.ssh_port,
      auth_method: formData.value.auth_method,
      ssh_password: formData.value.auth_method === 'password' ? formData.value.ssh_password : undefined,
      ssh_key: getSshKey(),
      roles: formData.value.roles,
      auto_enroll: skipEnrollment ? false : formData.value.auto_enroll,
      deploy_pki: skipEnrollment ? false : formData.value.deploy_pki,
      import_existing: formData.value.import_existing,
    }

    if (isEditMode.value && props.existingNode) {
      const node = await api.updateNode(props.existingNode.node_id, {
        ...nodeData,
        run_enrollment: formData.value.run_enrollment,
      })
      success.value = `Node ${formData.value.hostname} updated successfully`
      emit('updated', node)
    } else if (isReplaceMode.value && props.existingNode) {
      const newNode = await api.replaceNode(props.existingNode.node_id, nodeData)
      success.value = `Node replaced successfully`
      emit('replaced', { oldNodeId: props.existingNode.node_id, newNode })
    } else {
      const node = await api.registerNode(nodeData)
      success.value = `Node ${formData.value.hostname} registered successfully`
      emit('added', node)
    }

    setTimeout(() => {
      emit('close')
    }, 1500)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Operation failed'
  } finally {
    isSubmitting.value = false
  }
}

function handleOverlayClick() {
  if (!isSubmitting.value) {
    handleClose()
  }
}

function handleClose() {
  emit('close')
}
</script>

<style scoped>
/* Screen reader only utility (Issue #754) */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}
</style>
