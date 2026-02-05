# User Password Change Functionality - Design Document

**Issue:** #635
**Date:** 2026-02-05
**Status:** Approved Design

## Overview

Implement comprehensive password change functionality for both the main AutoBot Vue interface and SLM admin dashboard, with strict security controls including session invalidation and rate limiting.

## Requirements Summary

- **Frontends:** Both autobot-vue (profile modal) and slm-admin (user management)
- **Permissions:** Self-service (requires current password) + Admin reset (no current password required)
- **Security:** Session invalidation on password change, strict rate limiting (3 attempts / 30 min)
- **UX:** Combined password strength indicator (color bar + requirements checklist)

## Architecture Overview

### Component Structure

```
AutoBot/
├── src/
│   └── user_management/
│       ├── services/
│       │   ├── user_service.py (ENHANCE - add session invalidation)
│       │   └── session_service.py (NEW - session management)
│       └── middleware/
│           └── rate_limit.py (NEW - rate limiting)
├── backend/api/
│   └── user_management/
│       └── users.py (EXISTS - use /api/users/{user_id}/change-password)
├── shared-components/ (NEW DIRECTORY)
│   └── PasswordChangeForm.vue (NEW - shared Vue component)
├── autobot-vue/src/
│   └── components/
│       └── profile/
│           └── ProfileModal.vue (NEW - profile settings with password change)
└── slm-admin/src/
    └── views/settings/admin/
        └── UserManagementSettings.vue (UPDATE - use shared component)
```

### Key Design Decisions

1. **Shared Component:** Single `PasswordChangeForm.vue` used by both frontends for consistency
2. **Existing API:** Use existing `/api/users/{user_id}/change-password` endpoint (already has validation)
3. **Session Service:** New `SessionService` class handles JWT token invalidation via Redis
4. **Backend Rate Limiting:** Middleware tracks attempts in Redis for security

## Backend Design

### 1. Session Management

**New SessionService** (`src/user_management/services/session_service.py`):

```python
class SessionService:
    """Manages user sessions and JWT token invalidation."""

    async def invalidate_user_sessions(
        self,
        user_id: uuid.UUID,
        except_token: Optional[str] = None
    ) -> int:
        """
        Invalidate all sessions for a user except the current one.

        Implementation:
        - Store invalidated token hashes in Redis
        - Key: session:blacklist:{user_id}
        - TTL: Match JWT expiry (24 hours)
        - Exclude except_token hash to preserve current session

        Args:
            user_id: User whose sessions to invalidate
            except_token: Token to preserve (current session)

        Returns:
            Number of sessions invalidated
        """
```

**Integration with UserService:**

Update `UserService.change_password()` (line 455):

```python
async def change_password(...) -> bool:
    # ... existing password change logic ...

    # NEW: Invalidate sessions after password change
    session_service = SessionService(self.session)
    await session_service.invalidate_user_sessions(
        user_id=user_id,
        except_token=current_token  # Preserve current session
    )

    return True
```

**Implementation Notes:**
- Use Redis database "main" via `get_redis_client()`
- Store token hashes (SHA256) not full tokens
- Auth middleware checks blacklist on each request
- Return 401 Unauthorized if token blacklisted

### 2. Rate Limiting

**Middleware** (`src/user_management/middleware/rate_limit.py`):

```python
class PasswordChangeRateLimiter:
    """Rate limits password change attempts per user."""

    MAX_ATTEMPTS = 3  # Strict security
    WINDOW_SECONDS = 1800  # 30 minutes

    async def check_rate_limit(self, user_id: uuid.UUID) -> tuple[bool, int]:
        """
        Check if user has exceeded rate limit.

        Returns:
            (is_allowed, attempts_remaining)

        Raises:
            RateLimitExceeded: If limit exceeded
        """
        redis_client = get_redis_client(async_client=True, database="main")
        key = f"password_change_attempts:{user_id}"

        attempts = await redis_client.get(key)
        current = int(attempts) if attempts else 0

        if current >= self.MAX_ATTEMPTS:
            ttl = await redis_client.ttl(key)
            raise RateLimitExceeded(
                f"Too many attempts. Try again in {ttl // 60} minutes."
            )

        return True, self.MAX_ATTEMPTS - current

    async def record_attempt(self, user_id: uuid.UUID, success: bool):
        """Record password change attempt."""
        if success:
            await redis_client.delete(key)  # Clear on success
        else:
            await redis_client.incr(key)
            await redis_client.expire(key, self.WINDOW_SECONDS)
```

**Integration:** Apply as dependency to `/api/users/{user_id}/change-password` endpoint.

## Frontend Design

### Shared Component

**PasswordChangeForm.vue** (`shared-components/PasswordChangeForm.vue`):

```vue
<template>
  <div class="password-change-form">
    <!-- Strength Indicator: Color Bar -->
    <div class="strength-bar" :class="strengthClass">
      <div class="strength-fill" :style="{ width: strengthPercent }"></div>
      <span class="strength-label">{{ strengthLabel }}</span>
    </div>

    <!-- Strength Indicator: Requirements Checklist -->
    <div class="requirements-checklist">
      <div :class="{ met: hasMinLength }">
        <span class="icon">{{ hasMinLength ? '✓' : '○' }}</span>
        At least 8 characters
      </div>
      <div :class="{ met: hasUppercase }">
        <span class="icon">{{ hasUppercase ? '✓' : '○' }}</span>
        One uppercase letter
      </div>
      <div :class="{ met: hasLowercase }">
        <span class="icon">{{ hasLowercase ? '✓' : '○' }}</span>
        One lowercase letter
      </div>
      <div :class="{ met: hasNumber }">
        <span class="icon">{{ hasNumber ? '✓' : '○' }}</span>
        One number
      </div>
    </div>

    <!-- Form Fields -->
    <input
      v-if="requireCurrentPassword"
      v-model="currentPassword"
      type="password"
      placeholder="Current Password"
      @input="clearError"
    />
    <input
      v-model="newPassword"
      type="password"
      placeholder="New Password"
      @input="validateStrength"
    />
    <input
      v-model="confirmPassword"
      type="password"
      placeholder="Confirm Password"
      @input="validateMatch"
    />

    <!-- Rate Limit Warning -->
    <div v-if="attemptsRemaining !== null && attemptsRemaining <= 1" class="warning">
      ⚠️ {{ attemptsRemaining }} attempt remaining before lockout
    </div>

    <!-- Error Messages -->
    <div v-if="error" class="error">{{ error }}</div>

    <!-- Submit Button -->
    <button
      @click="handleSubmit"
      :disabled="!isValid || loading"
    >
      {{ loading ? 'Changing...' : 'Change Password' }}
    </button>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  userId: { type: String, required: true },
  requireCurrentPassword: { type: Boolean, default: true }
})

const emit = defineEmits(['success', 'error'])

// Form state
const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const error = ref(null)
const attemptsRemaining = ref(null)

// Password strength validation
const hasMinLength = computed(() => newPassword.value.length >= 8)
const hasUppercase = computed(() => /[A-Z]/.test(newPassword.value))
const hasLowercase = computed(() => /[a-z]/.test(newPassword.value))
const hasNumber = computed(() => /\d/.test(newPassword.value))

const strengthPercent = computed(() => {
  let score = 0
  if (hasMinLength.value) score += 25
  if (hasUppercase.value) score += 25
  if (hasLowercase.value) score += 25
  if (hasNumber.value) score += 25
  return `${score}%`
})

const strengthClass = computed(() => {
  const score = parseInt(strengthPercent.value)
  if (score === 100) return 'strong'
  if (score >= 50) return 'medium'
  return 'weak'
})

const strengthLabel = computed(() => {
  const score = parseInt(strengthPercent.value)
  if (score === 100) return 'Strong'
  if (score >= 50) return 'Medium'
  return 'Weak'
})

const isValid = computed(() => {
  return hasMinLength.value &&
         hasUppercase.value &&
         hasLowercase.value &&
         hasNumber.value &&
         newPassword.value === confirmPassword.value &&
         (!props.requireCurrentPassword || currentPassword.value)
})

async function handleSubmit() {
  loading.value = true
  error.value = null

  try {
    const response = await fetch(`/api/users/${props.userId}/change-password`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${getAuthToken()}`
      },
      body: JSON.stringify({
        current_password: props.requireCurrentPassword ? currentPassword.value : null,
        new_password: newPassword.value
      })
    })

    const data = await response.json()

    if (!response.ok) {
      if (response.status === 429) {
        // Rate limited
        error.value = data.detail
      } else if (response.status === 401) {
        // Wrong current password
        error.value = 'Current password is incorrect'
        attemptsRemaining.value = data.attempts_remaining || null
      } else {
        error.value = data.detail || 'Failed to change password'
      }
      emit('error', error.value)
      return
    }

    // Success
    emit('success', data.message)
    resetForm()

  } catch (e) {
    error.value = 'Unable to change password. Please try again.'
    emit('error', error.value)
  } finally {
    loading.value = false
  }
}

function resetForm() {
  currentPassword.value = ''
  newPassword.value = ''
  confirmPassword.value = ''
  attemptsRemaining.value = null
}
</script>

<style scoped>
.strength-bar {
  height: 8px;
  background: #e0e0e0;
  border-radius: 4px;
  overflow: hidden;
  position: relative;
}

.strength-fill {
  height: 100%;
  transition: width 0.3s, background-color 0.3s;
}

.strength-bar.weak .strength-fill { background: #ef4444; }
.strength-bar.medium .strength-fill { background: #f59e0b; }
.strength-bar.strong .strength-fill { background: #10b981; }

.requirements-checklist div {
  color: #6b7280;
  transition: color 0.2s;
}

.requirements-checklist div.met {
  color: #10b981;
  font-weight: 500;
}

.warning {
  background: #fef3c7;
  border: 1px solid #f59e0b;
  padding: 8px;
  border-radius: 4px;
  color: #92400e;
}

.error {
  background: #fee2e2;
  border: 1px solid #ef4444;
  padding: 8px;
  border-radius: 4px;
  color: #991b1b;
}
</style>
```

### AutoBot Vue Integration

**ProfileModal.vue** (`autobot-vue/src/components/profile/ProfileModal.vue`):

```vue
<template>
  <div class="modal" v-if="isOpen">
    <div class="modal-content">
      <h2>Profile Settings</h2>

      <!-- User Info Section -->
      <div class="profile-section">
        <h3>Account Information</h3>
        <div class="info-row">
          <label>Username:</label>
          <span>{{ currentUser.username }}</span>
        </div>
        <div class="info-row">
          <label>Email:</label>
          <span>{{ currentUser.email }}</span>
        </div>
      </div>

      <!-- Password Change Section -->
      <div class="profile-section">
        <h3>Security</h3>
        <PasswordChangeForm
          :user-id="currentUser.id"
          :require-current-password="true"
          @success="handlePasswordChanged"
          @error="handleError"
        />
      </div>

      <!-- Success Toast -->
      <div v-if="successMessage" class="toast success">
        {{ successMessage }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import PasswordChangeForm from '@/../shared-components/PasswordChangeForm.vue'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const currentUser = computed(() => authStore.user)
const successMessage = ref(null)

const handlePasswordChanged = (message) => {
  successMessage.value = 'Password changed successfully. Other sessions logged out.'
  setTimeout(() => { successMessage.value = null }, 5000)
}

const handleError = (error) => {
  console.error('Password change error:', error)
}
</script>
```

**Trigger:** Add "Profile" button in main navigation that opens this modal.

### SLM Admin Update

**UserManagementSettings.vue** (`slm-admin/src/views/settings/admin/UserManagementSettings.vue`):

**Changes Required:**

1. **Remove old password change code** (lines 160-197)
2. **Import shared component:**

```vue
<script setup>
import PasswordChangeForm from '@/../shared-components/PasswordChangeForm.vue'

const isAdminReset = computed(() => {
  // Admin resetting another user's password doesn't require current password
  return isAdmin.value && selectedUser.id !== currentUser.id
})
</script>

<template>
  <!-- In password change modal -->
  <PasswordChangeForm
    :user-id="selectedUser.id"
    :require-current-password="!isAdminReset"
    @success="handlePasswordChanged"
    @error="handleError"
  />
</template>
```

3. **Add "Reset Password" action** in user table actions column

## Data Flow

### Complete Password Change Flow

```
User (Frontend)
  │
  ├─► 1. Enters passwords in PasswordChangeForm
  │
  ├─► 2. Component validates strength requirements (real-time)
  │
  ├─► 3. POST /api/users/{user_id}/change-password
  │      { current_password, new_password }
  │
  ▼
Rate Limit Middleware
  │
  ├─► 4. Check Redis: password_change_attempts:{user_id}
  │
  ├─► 5. Allow if < 3 attempts in 30 minutes
  │      Otherwise: Return 429 with retry_after
  │
  ▼
Users API Endpoint (backend/api/user_management/users.py)
  │
  ├─► 6. Call UserService.change_password()
  │
  ▼
UserService
  │
  ├─► 7. Verify current password (if required)
  │
  ├─► 8. Hash new password (bcrypt, 12 rounds)
  │
  ├─► 9. Update user.password_hash in database
  │
  ├─► 10. Call SessionService.invalidate_user_sessions()
  │
  ▼
SessionService
  │
  ├─► 11. Generate hashes for all user's JWT tokens
  │
  ├─► 12. Add hashes to Redis blacklist
  │       Key: session:blacklist:{user_id}
  │       TTL: 24 hours (JWT expiry)
  │
  ├─► 13. Preserve current session token hash (exclude from blacklist)
  │
  ▼
Response
  │
  ├─► 14. Clear rate limit counter on success
  │
  ├─► 15. Return { success: true, message: "Password changed successfully" }
  │
  ▼
Frontend
  │
  └─► 16. Show success message
       "Password changed. Other sessions logged out."
```

### Subsequent Authenticated Requests

```
User makes API request
  │
  ▼
Auth Middleware
  │
  ├─► Extract JWT token from Authorization header
  │
  ├─► Generate token hash (SHA256)
  │
  ├─► Check Redis: session:blacklist:{user_id}
  │
  ├─► If hash found in blacklist:
  │     └─► Return 401 Unauthorized
  │         { detail: "Session invalidated. Please log in again." }
  │
  └─► If not blacklisted: Continue to endpoint
```

## Error Handling

### Error Scenarios

**1. Password Validation Errors (Frontend - Real-time)**

```javascript
// Displayed as user types
const validationErrors = computed(() => {
  const errors = []
  if (newPassword.value && !hasMinLength.value)
    errors.push('Password must be at least 8 characters')
  if (newPassword.value && !hasUppercase.value)
    errors.push('Must contain uppercase letter')
  if (newPassword.value && !hasLowercase.value)
    errors.push('Must contain lowercase letter')
  if (newPassword.value && !hasNumber.value)
    errors.push('Must contain at least one number')
  if (confirmPassword.value && newPassword.value !== confirmPassword.value)
    errors.push('Passwords do not match')
  return errors
})
```

**2. Rate Limit Exceeded**

Backend response:
```json
{
  "status": 429,
  "detail": "Too many password change attempts. Try again in 27 minutes.",
  "retry_after": 1620
}
```

Frontend display:
```
⛔ Too many password change attempts. Try again in 27 minutes.
```

**3. Invalid Current Password**

Backend response:
```json
{
  "status": 401,
  "detail": "Current password is incorrect",
  "attempts_remaining": 2
}
```

Frontend display:
```
❌ Current password is incorrect
⚠️ 2 attempts remaining before lockout
```

**4. Session Invalidation Failure**

```python
# Backend logs error but doesn't fail password change
try:
    await session_service.invalidate_user_sessions(user_id, current_token)
except Exception as e:
    logger.error("Session invalidation failed for user %s: %s", user_id, e)
    # Continue - password was changed successfully
```

**5. Network/Server Errors**

```javascript
// Frontend generic error handling
catch (error) {
  showError('Unable to change password. Please try again later.')
}
```

## Testing Strategy

### Backend Tests

**File:** `tests/user_management/test_password_change.py`

```python
async def test_self_service_password_change():
    """User changes own password with current password verification."""
    # Create user with password
    # Authenticate and get token
    # Change password with correct current password
    # Assert: password_hash updated
    # Assert: old sessions invalidated

async def test_admin_password_reset():
    """Admin resets user password without current password."""
    # Create admin user and regular user
    # Admin calls change_password without current_password
    # Assert: password changed without current password check
    # Assert: user sessions invalidated

async def test_rate_limiting():
    """Rate limiter blocks after 3 failed attempts."""
    # Attempt password change 3 times with wrong current password
    # Assert: attempts 1-3 return 401
    # Assert: attempt 4 returns 429 Too Many Requests
    # Assert: retry_after in response

async def test_rate_limit_resets_on_success():
    """Successful password change clears rate limit counter."""
    # Fail 2 attempts
    # Succeed on 3rd attempt
    # Assert: counter cleared, can attempt again immediately

async def test_session_invalidation():
    """Old sessions rejected after password change."""
    # Create user, get 2 tokens (session A, session B)
    # Change password using session A
    # Assert: session A still works
    # Assert: session B gets 401 on next request

async def test_session_invalidation_preserves_current():
    """Current session preserved during password change."""
    # Change password
    # Make authenticated request with same token
    # Assert: request succeeds

async def test_password_validation():
    """Weak passwords rejected by backend."""
    passwords = [
        ("weak", "Password must be at least 8 characters"),
        ("NoNumber", "Password must contain at least one digit"),
        ("no-upper-123", "Password must contain at least one uppercase letter"),
        ("NO-LOWER-123", "Password must contain at least one lowercase letter"),
    ]
    for password, expected_error in passwords:
        # Assert: backend returns 422 with expected error
```

### Frontend Tests

**File:** `tests/PasswordChangeForm.spec.js`

```javascript
import { mount } from '@vue/test-utils'
import PasswordChangeForm from '@/shared-components/PasswordChangeForm.vue'

test('shows strength indicator as user types', async () => {
  const wrapper = mount(PasswordChangeForm, {
    props: { userId: '123', requireCurrentPassword: true }
  })

  await wrapper.find('input[placeholder="New Password"]').setValue('Test1234')

  expect(wrapper.find('.strength-bar').classes()).toContain('strong')
  expect(wrapper.find('.strength-label').text()).toBe('Strong')
  expect(wrapper.find('.strength-fill').attributes('style')).toContain('width: 100%')
})

test('shows requirement checklist with real-time updates', async () => {
  const wrapper = mount(PasswordChangeForm)

  // Type partial password
  await wrapper.find('input[placeholder="New Password"]').setValue('test')
  expect(wrapper.findAll('.requirements-checklist .met')).toHaveLength(1) // Only lowercase

  // Complete strong password
  await wrapper.find('input[placeholder="New Password"]').setValue('Test1234')
  expect(wrapper.findAll('.requirements-checklist .met')).toHaveLength(4) // All requirements
})

test('disables submit until all requirements met', async () => {
  const wrapper = mount(PasswordChangeForm)

  // Weak password
  await wrapper.find('input[placeholder="New Password"]').setValue('weak')
  expect(wrapper.find('button').attributes('disabled')).toBeDefined()

  // Strong password
  await wrapper.find('input[placeholder="New Password"]').setValue('Test1234')
  await wrapper.find('input[placeholder="Confirm Password"]').setValue('Test1234')
  expect(wrapper.find('button').attributes('disabled')).toBeUndefined()
})

test('shows rate limit warning', async () => {
  const wrapper = mount(PasswordChangeForm)

  // Mock API response with attempts_remaining
  global.fetch = vi.fn(() =>
    Promise.resolve({
      ok: false,
      status: 401,
      json: () => Promise.resolve({
        detail: 'Wrong password',
        attempts_remaining: 1
      })
    })
  )

  await wrapper.find('button').trigger('click')
  await wrapper.vm.$nextTick()

  expect(wrapper.find('.warning').text()).toContain('1 attempt remaining')
})

test('shows error on password mismatch', async () => {
  const wrapper = mount(PasswordChangeForm)

  await wrapper.find('input[placeholder="New Password"]').setValue('Test1234')
  await wrapper.find('input[placeholder="Confirm Password"]').setValue('Different123')

  // Submit button should be disabled
  expect(wrapper.find('button').attributes('disabled')).toBeDefined()
})
```

### Manual Testing Checklist

**AutoBot Vue (Profile Modal):**
- [ ] Profile modal opens from navigation menu
- [ ] Current password field displayed
- [ ] Strength indicator updates as user types
- [ ] All 4 requirements show checkmarks when met
- [ ] Submit disabled until all requirements met
- [ ] Correct current password allows password change
- [ ] Wrong current password shows error and attempts remaining
- [ ] Success message displayed after password change
- [ ] Can still use current session after change
- [ ] Rate limit triggers after 3 failed attempts

**SLM Admin (User Management):**
- [ ] "Reset Password" button appears in user table actions
- [ ] Admin resetting own password requires current password
- [ ] Admin resetting other user's password does NOT require current password
- [ ] Same strength indicator and validation
- [ ] Success message confirms password reset
- [ ] Target user's sessions are invalidated

**Session Invalidation:**
- [ ] Open AutoBot in two browsers with same user
- [ ] Change password in browser A
- [ ] Browser A session continues working
- [ ] Browser B session gets 401 on next request
- [ ] Browser B forced to re-login

**Rate Limiting:**
- [ ] After 3 failed attempts, 4th attempt blocked
- [ ] Error message shows time remaining (minutes)
- [ ] Counter resets after successful password change
- [ ] Counter expires after 30 minutes

## Security Considerations

1. **Password Hashing:** bcrypt with 12 rounds (existing implementation)
2. **Session Management:** Token hashes stored in Redis, not full tokens
3. **Rate Limiting:** Backend enforcement prevents brute force
4. **Current Password Verification:** Required for self-service changes
5. **Admin Bypass:** Admins can reset without current password (audit logged)
6. **Session Invalidation:** Automatic logout of other devices on password change
7. **HTTPS Only:** All password change requests must use HTTPS in production

## Implementation Checklist

### Phase 1: Backend Foundation
- [ ] Create `SessionService` class
- [ ] Implement token blacklist in Redis
- [ ] Add session invalidation to `UserService.change_password()`
- [ ] Create `PasswordChangeRateLimiter` middleware
- [ ] Apply rate limiter to password change endpoint
- [ ] Update auth middleware to check token blacklist
- [ ] Write backend tests

### Phase 2: Shared Component
- [ ] Create `shared-components/` directory
- [ ] Build `PasswordChangeForm.vue` component
- [ ] Implement password strength indicator (bar + checklist)
- [ ] Add form validation
- [ ] Implement API integration
- [ ] Write frontend tests

### Phase 3: AutoBot Vue Integration
- [ ] Create `ProfileModal.vue` component
- [ ] Add profile button to navigation
- [ ] Integrate `PasswordChangeForm` component
- [ ] Add success/error toast notifications
- [ ] Manual testing

### Phase 4: SLM Admin Update
- [ ] Remove old password change code
- [ ] Import and integrate `PasswordChangeForm`
- [ ] Add admin reset logic (requireCurrentPassword prop)
- [ ] Add "Reset Password" button to user table
- [ ] Manual testing

### Phase 5: Documentation & Deployment
- [ ] Update API documentation
- [ ] Add user guide for password change
- [ ] Update deployment notes for Redis session blacklist
- [ ] Code review
- [ ] Merge to main

## API Reference

### Endpoint: `POST /api/users/{user_id}/change-password`

**Request:**
```json
{
  "current_password": "OldPass123",  // Optional for admin resets
  "new_password": "NewPass456"
}
```

**Response (Success):**
```json
{
  "success": true,
  "message": "Password changed successfully"
}
```

**Response (Rate Limited):**
```json
{
  "status": 429,
  "detail": "Too many password change attempts. Try again in 27 minutes.",
  "retry_after": 1620
}
```

**Response (Invalid Current Password):**
```json
{
  "status": 401,
  "detail": "Current password is incorrect",
  "attempts_remaining": 2
}
```

## Redis Keys

### Session Blacklist
- **Key:** `session:blacklist:{user_id}`
- **Type:** Set
- **Value:** SHA256 hashes of invalidated JWT tokens
- **TTL:** 24 hours (matches JWT expiration)

### Rate Limiting
- **Key:** `password_change_attempts:{user_id}`
- **Type:** Integer counter
- **Value:** Number of failed attempts
- **TTL:** 1800 seconds (30 minutes)

## Acceptance Criteria Verification

From Issue #635:

- [x] User can change their password via the UI
  - ✅ Both autobot-vue profile modal and slm-admin user management

- [x] Current password is required and validated
  - ✅ Required for self-service, not required for admin resets

- [x] New password must meet complexity requirements
  - ✅ Real-time validation: 8 chars, uppercase, lowercase, digit

- [x] Error messages are displayed appropriately
  - ✅ Validation errors, rate limit warnings, wrong password errors

- [x] Success message confirms password was changed
  - ✅ "Password changed successfully. Other sessions logged out."

## Related Issues

- **Parent:** #627 - Technical Debt Cleanup
- **Dependencies:** None (backend infrastructure already exists)

---

**Approved by:** [Pending]
**Ready for Implementation:** Yes
