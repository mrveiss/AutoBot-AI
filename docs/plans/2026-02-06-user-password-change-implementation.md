# User Password Change Functionality - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement secure password change functionality for both autobot-vue and slm-admin with session invalidation and rate limiting.

**Architecture:** Backend session service manages JWT token blacklisting via Redis. Rate limiting middleware prevents brute force. Shared Vue component provides consistent UX across both frontends. Admin users can reset passwords without current password.

**Tech Stack:** Python FastAPI, Redis, Vue 3, TypeScript, bcrypt, JWT

**Related Issue:** #635

---

## Phase 1: Backend - Session Service (TDD)

### Task 1.1: SessionService - Token Hashing Test

**Files:**
- Create: `tests/user_management/services/test_session_service.py`
- Reference: `src/user_management/services/user_service.py` (existing service pattern)

**Step 1: Write the failing test**

```python
# tests/user_management/services/test_session_service.py
import pytest
import uuid
from src.user_management.services.session_service import SessionService

@pytest.mark.asyncio
async def test_hash_token_creates_sha256():
    """Token hashing produces consistent SHA256 hashes."""
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"

    hash1 = SessionService.hash_token(token)
    hash2 = SessionService.hash_token(token)

    assert hash1 == hash2  # Deterministic
    assert len(hash1) == 64  # SHA256 hex length
    assert hash1.isalnum()  # Hex string
```

**Step 2: Run test to verify it fails**

```bash
cd /home/kali/Desktop/AutoBot/.worktrees/feature/user-password-change
pytest tests/user_management/services/test_session_service.py::test_hash_token_creates_sha256 -v
```

Expected: `ModuleNotFoundError: No module named 'src.user_management.services.session_service'`

**Step 3: Write minimal implementation**

Create: `src/user_management/services/session_service.py`

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Session Service

Manages user sessions and JWT token invalidation via Redis blacklist.
Issue #635.
"""

import hashlib
import logging
import uuid
from typing import Optional

logger = logging.getLogger(__name__)


class SessionService:
    """Manages user sessions and JWT token invalidation."""

    @staticmethod
    def hash_token(token: str) -> str:
        """
        Hash JWT token using SHA256.

        Args:
            token: JWT token string

        Returns:
            Hex string of SHA256 hash
        """
        return hashlib.sha256(token.encode('utf-8')).hexdigest()
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/user_management/services/test_session_service.py::test_hash_token_creates_sha256 -v
```

Expected: `PASSED`

**Step 5: Commit**

```bash
git add tests/user_management/services/test_session_service.py src/user_management/services/session_service.py
git commit -m "test(session): add token hashing with SHA256 (#635)"
```

---

### Task 1.2: SessionService - Redis Blacklist Storage Test

**Files:**
- Modify: `tests/user_management/services/test_session_service.py`
- Modify: `src/user_management/services/session_service.py`

**Step 1: Write the failing test**

```python
# Add to test_session_service.py
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    mock = AsyncMock()
    mock.sadd = AsyncMock(return_value=1)
    mock.expire = AsyncMock(return_value=True)
    mock.sismember = AsyncMock(return_value=False)
    return mock

@pytest.mark.asyncio
async def test_add_token_to_blacklist(mock_redis):
    """Adding token to blacklist stores hash in Redis set."""
    user_id = uuid.uuid4()
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"

    with patch('src.user_management.services.session_service.get_redis_client', return_value=mock_redis):
        service = SessionService()
        await service.add_token_to_blacklist(user_id, token, ttl=86400)

    # Verify Redis operations
    expected_key = f"session:blacklist:{user_id}"
    expected_hash = SessionService.hash_token(token)

    mock_redis.sadd.assert_called_once_with(expected_key, expected_hash)
    mock_redis.expire.assert_called_once_with(expected_key, 86400)
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/user_management/services/test_session_service.py::test_add_token_to_blacklist -v
```

Expected: `AttributeError: 'SessionService' object has no attribute 'add_token_to_blacklist'`

**Step 3: Write minimal implementation**

```python
# Add to src/user_management/services/session_service.py
from src.utils.redis_client import get_redis_client

class SessionService:
    """Manages user sessions and JWT token invalidation."""

    # ... existing hash_token method ...

    async def add_token_to_blacklist(
        self,
        user_id: uuid.UUID,
        token: str,
        ttl: int = 86400
    ) -> None:
        """
        Add token to blacklist.

        Args:
            user_id: User whose token to blacklist
            token: JWT token to invalidate
            ttl: Time to live in seconds (default 24 hours)
        """
        redis_client = get_redis_client(async_client=True, database="main")
        key = f"session:blacklist:{user_id}"
        token_hash = self.hash_token(token)

        await redis_client.sadd(key, token_hash)
        await redis_client.expire(key, ttl)

        logger.info("Added token to blacklist for user %s", user_id)
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/user_management/services/test_session_service.py::test_add_token_to_blacklist -v
```

Expected: `PASSED`

**Step 5: Commit**

```bash
git add tests/user_management/services/test_session_service.py src/user_management/services/session_service.py
git commit -m "feat(session): add token to Redis blacklist (#635)"
```

---

### Task 1.3: SessionService - Check Blacklist Test

**Files:**
- Modify: `tests/user_management/services/test_session_service.py`
- Modify: `src/user_management/services/session_service.py`

**Step 1: Write the failing test**

```python
# Add to test_session_service.py
@pytest.mark.asyncio
async def test_is_token_blacklisted(mock_redis):
    """Check if token is in blacklist."""
    user_id = uuid.uuid4()
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"

    # Mock blacklisted token
    mock_redis.sismember = AsyncMock(return_value=True)

    with patch('src.user_management.services.session_service.get_redis_client', return_value=mock_redis):
        service = SessionService()
        is_blacklisted = await service.is_token_blacklisted(user_id, token)

    assert is_blacklisted is True

    expected_key = f"session:blacklist:{user_id}"
    expected_hash = SessionService.hash_token(token)
    mock_redis.sismember.assert_called_once_with(expected_key, expected_hash)
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/user_management/services/test_session_service.py::test_is_token_blacklisted -v
```

Expected: `AttributeError: 'SessionService' object has no attribute 'is_token_blacklisted'`

**Step 3: Write minimal implementation**

```python
# Add to src/user_management/services/session_service.py
async def is_token_blacklisted(
    self,
    user_id: uuid.UUID,
    token: str
) -> bool:
    """
    Check if token is blacklisted.

    Args:
        user_id: User ID
        token: JWT token to check

    Returns:
        True if token is blacklisted
    """
    redis_client = get_redis_client(async_client=True, database="main")
    key = f"session:blacklist:{user_id}"
    token_hash = self.hash_token(token)

    return await redis_client.sismember(key, token_hash)
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/user_management/services/test_session_service.py::test_is_token_blacklisted -v
```

Expected: `PASSED`

**Step 5: Commit**

```bash
git add tests/user_management/services/test_session_service.py src/user_management/services/session_service.py
git commit -m "feat(session): check if token is blacklisted (#635)"
```

---

### Task 1.4: SessionService - Invalidate User Sessions Test

**Files:**
- Modify: `tests/user_management/services/test_session_service.py`
- Modify: `src/user_management/services/session_service.py`

**Step 1: Write the failing test**

```python
# Add to test_session_service.py
@pytest.mark.asyncio
async def test_invalidate_user_sessions_except_current(mock_redis):
    """Invalidate all user sessions except the current token."""
    user_id = uuid.uuid4()
    current_token = "current.token.here"

    # Mock existing tokens in Redis
    existing_tokens = ["old.token.1", "old.token.2", current_token]
    mock_redis.smembers = AsyncMock(return_value={
        SessionService.hash_token(t) for t in existing_tokens
    })
    mock_redis.sadd = AsyncMock()
    mock_redis.expire = AsyncMock()

    with patch('src.user_management.services.session_service.get_redis_client', return_value=mock_redis):
        service = SessionService()
        count = await service.invalidate_user_sessions(user_id, except_token=current_token)

    # Should invalidate 2 tokens (excluding current)
    assert count == 2

    # Verify current token hash NOT added to blacklist
    current_hash = SessionService.hash_token(current_token)
    calls = mock_redis.sadd.call_args_list
    for call in calls:
        assert current_hash not in call[0][1]  # Not in added tokens
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/user_management/services/test_session_service.py::test_invalidate_user_sessions_except_current -v
```

Expected: `AttributeError: 'SessionService' object has no attribute 'invalidate_user_sessions'`

**Step 3: Write minimal implementation**

```python
# Add to src/user_management/services/session_service.py
async def invalidate_user_sessions(
    self,
    user_id: uuid.UUID,
    except_token: Optional[str] = None
) -> int:
    """
    Invalidate all sessions for a user except the current one.

    Implementation:
    - Adds token hashes to Redis blacklist set
    - Key: session:blacklist:{user_id}
    - TTL: 24 hours (matches JWT expiry)
    - Excludes except_token hash to preserve current session

    Args:
        user_id: User whose sessions to invalidate
        except_token: Token to preserve (current session)

    Returns:
        Number of sessions invalidated
    """
    redis_client = get_redis_client(async_client=True, database="main")
    key = f"session:blacklist:{user_id}"

    # Get existing token hashes (if any)
    existing_hashes = await redis_client.smembers(key) or set()

    # Compute except_token hash if provided
    except_hash = self.hash_token(except_token) if except_token else None

    # Add all existing tokens to blacklist except current
    count = 0
    for token_hash in existing_hashes:
        if token_hash != except_hash:
            await redis_client.sadd(key, token_hash)
            count += 1

    # Set expiry
    await redis_client.expire(key, 86400)  # 24 hours

    logger.info("Invalidated %d sessions for user %s", count, user_id)
    return count
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/user_management/services/test_session_service.py::test_invalidate_user_sessions_except_current -v
```

Expected: `PASSED`

**Step 5: Commit**

```bash
git add tests/user_management/services/test_session_service.py src/user_management/services/session_service.py
git commit -m "feat(session): invalidate user sessions except current (#635)"
```

---

## Phase 2: Backend - Rate Limiting Middleware (TDD)

### Task 2.1: Rate Limiter - Check Limit Test

**Files:**
- Create: `tests/user_management/middleware/test_rate_limit.py`
- Create: `src/user_management/middleware/__init__.py` (empty)
- Create: `src/user_management/middleware/rate_limit.py`

**Step 1: Write the failing test**

```python
# tests/user_management/middleware/test_rate_limit.py
import pytest
import uuid
from unittest.mock import AsyncMock, patch

@pytest.fixture
def mock_redis():
    """Mock Redis client for rate limiting."""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.incr = AsyncMock(return_value=1)
    mock.expire = AsyncMock(return_value=True)
    mock.ttl = AsyncMock(return_value=1800)
    mock.delete = AsyncMock(return_value=1)
    return mock

@pytest.mark.asyncio
async def test_check_rate_limit_allows_under_threshold(mock_redis):
    """Rate limiter allows requests under threshold."""
    from src.user_management.middleware.rate_limit import PasswordChangeRateLimiter

    user_id = uuid.uuid4()
    mock_redis.get = AsyncMock(return_value="2")  # 2 attempts

    with patch('src.user_management.middleware.rate_limit.get_redis_client', return_value=mock_redis):
        limiter = PasswordChangeRateLimiter()
        is_allowed, remaining = await limiter.check_rate_limit(user_id)

    assert is_allowed is True
    assert remaining == 1  # 3 max - 2 current = 1 remaining
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/user_management/middleware/test_rate_limit.py::test_check_rate_limit_allows_under_threshold -v
```

Expected: `ModuleNotFoundError: No module named 'src.user_management.middleware.rate_limit'`

**Step 3: Write minimal implementation**

Create: `src/user_management/middleware/__init__.py` (empty file)

Create: `src/user_management/middleware/rate_limit.py`

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Rate Limiting Middleware

Prevents brute force password change attempts.
Issue #635.
"""

import logging
import uuid

from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""
    pass


class PasswordChangeRateLimiter:
    """Rate limits password change attempts per user."""

    MAX_ATTEMPTS = 3  # Strict security
    WINDOW_SECONDS = 1800  # 30 minutes

    async def check_rate_limit(self, user_id: uuid.UUID) -> tuple[bool, int]:
        """
        Check if user has exceeded rate limit.

        Args:
            user_id: User ID to check

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
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/user_management/middleware/test_rate_limit.py::test_check_rate_limit_allows_under_threshold -v
```

Expected: `PASSED`

**Step 5: Commit**

```bash
git add tests/user_management/middleware/test_rate_limit.py src/user_management/middleware/__init__.py src/user_management/middleware/rate_limit.py
git commit -m "test(rate-limit): check rate limit threshold (#635)"
```

---

### Task 2.2: Rate Limiter - Block Exceeded Limit Test

**Files:**
- Modify: `tests/user_management/middleware/test_rate_limit.py`

**Step 1: Write the failing test**

```python
# Add to test_rate_limit.py
@pytest.mark.asyncio
async def test_check_rate_limit_blocks_exceeded(mock_redis):
    """Rate limiter blocks when threshold exceeded."""
    from src.user_management.middleware.rate_limit import (
        PasswordChangeRateLimiter,
        RateLimitExceeded
    )

    user_id = uuid.uuid4()
    mock_redis.get = AsyncMock(return_value="3")  # At max
    mock_redis.ttl = AsyncMock(return_value=1620)  # 27 minutes

    with patch('src.user_management.middleware.rate_limit.get_redis_client', return_value=mock_redis):
        limiter = PasswordChangeRateLimiter()

        with pytest.raises(RateLimitExceeded) as exc_info:
            await limiter.check_rate_limit(user_id)

        assert "27 minutes" in str(exc_info.value)
```

**Step 2: Run test to verify it passes**

```bash
pytest tests/user_management/middleware/test_rate_limit.py::test_check_rate_limit_blocks_exceeded -v
```

Expected: `PASSED` (implementation already supports this)

**Step 3: Commit**

```bash
git add tests/user_management/middleware/test_rate_limit.py
git commit -m "test(rate-limit): verify blocking when exceeded (#635)"
```

---

### Task 2.3: Rate Limiter - Record Attempt Test

**Files:**
- Modify: `tests/user_management/middleware/test_rate_limit.py`
- Modify: `src/user_management/middleware/rate_limit.py`

**Step 1: Write the failing test**

```python
# Add to test_rate_limit.py
@pytest.mark.asyncio
async def test_record_attempt_increments_on_failure(mock_redis):
    """Recording failed attempt increments counter."""
    from src.user_management.middleware.rate_limit import PasswordChangeRateLimiter

    user_id = uuid.uuid4()
    mock_redis.incr = AsyncMock(return_value=2)
    mock_redis.expire = AsyncMock()

    with patch('src.user_management.middleware.rate_limit.get_redis_client', return_value=mock_redis):
        limiter = PasswordChangeRateLimiter()
        await limiter.record_attempt(user_id, success=False)

    key = f"password_change_attempts:{user_id}"
    mock_redis.incr.assert_called_once_with(key)
    mock_redis.expire.assert_called_once_with(key, 1800)

@pytest.mark.asyncio
async def test_record_attempt_clears_on_success(mock_redis):
    """Recording successful attempt clears counter."""
    from src.user_management.middleware.rate_limit import PasswordChangeRateLimiter

    user_id = uuid.uuid4()
    mock_redis.delete = AsyncMock(return_value=1)

    with patch('src.user_management.middleware.rate_limit.get_redis_client', return_value=mock_redis):
        limiter = PasswordChangeRateLimiter()
        await limiter.record_attempt(user_id, success=True)

    key = f"password_change_attempts:{user_id}"
    mock_redis.delete.assert_called_once_with(key)
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/user_management/middleware/test_rate_limit.py::test_record_attempt_increments_on_failure -v
pytest tests/user_management/middleware/test_rate_limit.py::test_record_attempt_clears_on_success -v
```

Expected: `AttributeError: 'PasswordChangeRateLimiter' object has no attribute 'record_attempt'`

**Step 3: Write minimal implementation**

```python
# Add to src/user_management/middleware/rate_limit.py
async def record_attempt(self, user_id: uuid.UUID, success: bool) -> None:
    """
    Record password change attempt.

    Args:
        user_id: User ID
        success: Whether attempt was successful
    """
    redis_client = get_redis_client(async_client=True, database="main")
    key = f"password_change_attempts:{user_id}"

    if success:
        # Clear attempts on success
        await redis_client.delete(key)
        logger.info("Cleared rate limit for user %s", user_id)
    else:
        # Increment failed attempts
        await redis_client.incr(key)
        await redis_client.expire(key, self.WINDOW_SECONDS)
        logger.warning("Failed password change attempt for user %s", user_id)
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/user_management/middleware/test_rate_limit.py::test_record_attempt_increments_on_failure -v
pytest tests/user_management/middleware/test_rate_limit.py::test_record_attempt_clears_on_success -v
```

Expected: `PASSED` (both tests)

**Step 5: Commit**

```bash
git add tests/user_management/middleware/test_rate_limit.py src/user_management/middleware/rate_limit.py
git commit -m "feat(rate-limit): record password change attempts (#635)"
```

---

## Phase 3: Backend - API Integration

### Task 3.1: Integrate SessionService with UserService

**Files:**
- Modify: `src/user_management/services/user_service.py:455-499`
- Modify: `tests/user_management/services/test_user_service.py` (add integration test)

**Step 1: Write the failing test**

```python
# Add to tests/user_management/services/test_user_service.py
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_change_password_invalidates_sessions(user_service, sample_user):
    """Changing password invalidates other sessions."""
    current_token = "current.jwt.token"

    with patch('src.user_management.services.user_service.SessionService') as MockSession:
        mock_session_service = MockSession.return_value
        mock_session_service.invalidate_user_sessions = AsyncMock(return_value=2)

        success = await user_service.change_password(
            user_id=sample_user.id,
            current_password="OldPass123",
            new_password="NewPass456",
            current_token=current_token
        )

    assert success is True
    mock_session_service.invalidate_user_sessions.assert_called_once_with(
        sample_user.id,
        except_token=current_token
    )
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/user_management/services/test_user_service.py::test_change_password_invalidates_sessions -v
```

Expected: `TypeError: change_password() got an unexpected keyword argument 'current_token'`

**Step 3: Update UserService.change_password**

```python
# Modify src/user_management/services/user_service.py
from src.user_management.services.session_service import SessionService

# Update method signature at line 455
async def change_password(
    self,
    user_id: uuid.UUID,
    current_password: Optional[str],
    new_password: str,
    require_current: bool = True,
    current_token: Optional[str] = None,  # NEW parameter
) -> bool:
    """
    Change user password.

    Args:
        user_id: User ID
        current_password: Current password (for verification)
        new_password: New password
        require_current: Whether to require current password verification
        current_token: Current JWT token to preserve (NEW)

    Returns:
        True if password changed

    Raises:
        UserNotFoundError: If user not found
        InvalidCredentialsError: If current password is wrong
    """
    user = await self.get_user(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    if require_current and user.password_hash:
        if not current_password or not self.verify_password(
            current_password, user.password_hash
        ):
            raise InvalidCredentialsError("Current password is incorrect")

    user.password_hash = self.hash_password(new_password)
    user.updated_at = datetime.now(timezone.utc)
    await self.session.flush()

    # NEW: Invalidate sessions after password change
    session_service = SessionService()
    await session_service.invalidate_user_sessions(
        user_id=user_id,
        except_token=current_token
    )

    await self._audit_log(
        action=AuditAction.PASSWORD_CHANGED,
        resource_type=AuditResourceType.USER,
        resource_id=user_id,
        details={"method": "user_initiated"},
    )

    return True
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/user_management/services/test_user_service.py::test_change_password_invalidates_sessions -v
```

Expected: `PASSED`

**Step 5: Commit**

```bash
git add src/user_management/services/user_service.py tests/user_management/services/test_user_service.py
git commit -m "feat(user): integrate session invalidation on password change (#635)"
```

---

### Task 3.2: Integrate Rate Limiter with API Endpoint

**Files:**
- Modify: `backend/api/user_management/users.py:360-394`
- Create: `tests/api/user_management/test_users_password_change.py`

**Step 1: Write the failing test**

```python
# tests/api/user_management/test_users_password_change.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

def test_change_password_checks_rate_limit(client: TestClient, auth_headers):
    """Password change endpoint checks rate limit."""
    user_id = "550e8400-e29b-41d4-a716-446655440000"

    with patch('backend.api.user_management.users.PasswordChangeRateLimiter') as MockLimiter:
        mock_limiter = MockLimiter.return_value
        mock_limiter.check_rate_limit = AsyncMock(return_value=(True, 2))
        mock_limiter.record_attempt = AsyncMock()

        response = client.post(
            f"/api/users/{user_id}/change-password",
            json={
                "current_password": "OldPass123",
                "new_password": "NewPass456"
            },
            headers=auth_headers
        )

    mock_limiter.check_rate_limit.assert_called_once()
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/api/user_management/test_users_password_change.py::test_change_password_checks_rate_limit -v
```

Expected: `ImportError: cannot import name 'PasswordChangeRateLimiter'`

**Step 3: Update API endpoint**

```python
# Modify backend/api/user_management/users.py
from src.user_management.middleware.rate_limit import (
    PasswordChangeRateLimiter,
    RateLimitExceeded,
)

# Update change_password endpoint (line 367)
@router.post(
    "/{user_id}/change-password",
    response_model=PasswordChangedResponse,
    summary="Change password",
    description="Change a user's password.",
    dependencies=[Depends(require_user_management_enabled)],
)
async def change_password(
    user_id: uuid.UUID,
    password_data: PasswordChange,
    user_service: UserService = Depends(get_user_service),
    current_user: dict = Depends(get_current_user),
):
    """Change user password with rate limiting."""
    # NEW: Check rate limit
    rate_limiter = PasswordChangeRateLimiter()
    try:
        await rate_limiter.check_rate_limit(user_id)
    except RateLimitExceeded as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e),
        )

    # Attempt password change
    try:
        # Extract current token from request (if available)
        current_token = current_user.get("token")

        await user_service.change_password(
            user_id=user_id,
            current_password=password_data.current_password,
            new_password=password_data.new_password,
            require_current=password_data.current_password is not None,
            current_token=current_token,
        )

        # NEW: Record successful attempt
        await rate_limiter.record_attempt(user_id, success=True)

        return PasswordChangedResponse(
            message="Password changed successfully",
        )

    except UserNotFoundError:
        await rate_limiter.record_attempt(user_id, success=False)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )
    except InvalidCredentialsError:
        await rate_limiter.record_attempt(user_id, success=False)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/api/user_management/test_users_password_change.py::test_change_password_checks_rate_limit -v
```

Expected: `PASSED`

**Step 5: Commit**

```bash
git add backend/api/user_management/users.py tests/api/user_management/test_users_password_change.py
git commit -m "feat(api): add rate limiting to password change endpoint (#635)"
```

---

## Phase 4: Frontend - Shared Component

### Task 4.1: Create Shared Component Directory Structure

**Files:**
- Create: `shared-components/PasswordChangeForm.vue`
- Create: `shared-components/README.md`

**Step 1: Create directory and README**

```bash
mkdir -p shared-components
```

Create: `shared-components/README.md`

```markdown
# Shared Components

Vue components shared between autobot-vue and slm-admin frontends.

## Usage

Import components using the `@/../shared-components/` path:

```vue
import PasswordChangeForm from '@/../shared-components/PasswordChangeForm.vue'
```

## Components

- **PasswordChangeForm.vue** - Password change form with strength indicator and validation
```

**Step 2: Commit**

```bash
git add shared-components/README.md
git commit -m "docs(shared): add shared components directory (#635)"
```

---

### Task 4.2: Build PasswordChangeForm Component - Structure

**Files:**
- Create: `shared-components/PasswordChangeForm.vue`

**Step 1: Create component template**

```vue
<!-- shared-components/PasswordChangeForm.vue -->
<template>
  <div class="password-change-form">
    <!-- Strength Indicator: Color Bar -->
    <div v-if="newPassword" class="strength-indicator">
      <div class="strength-bar" :class="strengthClass">
        <div class="strength-fill" :style="{ width: strengthPercent }"></div>
      </div>
      <span class="strength-label">{{ strengthLabel }}</span>
    </div>

    <!-- Requirements Checklist -->
    <div v-if="newPassword" class="requirements-checklist">
      <div class="requirement" :class="{ met: hasMinLength }">
        <span class="icon">{{ hasMinLength ? '✓' : '○' }}</span>
        At least 8 characters
      </div>
      <div class="requirement" :class="{ met: hasUppercase }">
        <span class="icon">{{ hasUppercase ? '✓' : '○' }}</span>
        One uppercase letter
      </div>
      <div class="requirement" :class="{ met: hasLowercase }">
        <span class="icon">{{ hasLowercase ? '✓' : '○' }}</span>
        One lowercase letter
      </div>
      <div class="requirement" :class="{ met: hasNumber }">
        <span class="icon">{{ hasNumber ? '✓' : '○' }}</span>
        One number
      </div>
    </div>

    <!-- Form Fields -->
    <div class="form-fields">
      <input
        v-if="requireCurrentPassword"
        v-model="currentPassword"
        type="password"
        placeholder="Current Password"
        class="form-input"
        @input="clearError"
      />
      <input
        v-model="newPassword"
        type="password"
        placeholder="New Password"
        class="form-input"
        @input="validateStrength"
      />
      <input
        v-model="confirmPassword"
        type="password"
        placeholder="Confirm Password"
        class="form-input"
        @input="validateMatch"
      />
    </div>

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
      class="submit-button"
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

const passwordsMatch = computed(() => {
  return confirmPassword.value === newPassword.value
})

const isValid = computed(() => {
  return hasMinLength.value &&
         hasUppercase.value &&
         hasLowercase.value &&
         hasNumber.value &&
         passwordsMatch.value &&
         (!props.requireCurrentPassword || currentPassword.value)
})

function clearError() {
  error.value = null
}

function validateStrength() {
  clearError()
}

function validateMatch() {
  if (confirmPassword.value && !passwordsMatch.value) {
    error.value = 'Passwords do not match'
  } else {
    clearError()
  }
}

async function handleSubmit() {
  if (!isValid.value) return

  loading.value = true
  error.value = null

  try {
    // Get auth token from localStorage or auth store
    const token = localStorage.getItem('authToken') || ''

    const response = await fetch(`/api/users/${props.userId}/change-password`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
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
.password-change-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 400px;
}

.strength-indicator {
  display: flex;
  align-items: center;
  gap: 12px;
}

.strength-bar {
  flex: 1;
  height: 8px;
  background: #e5e7eb;
  border-radius: 4px;
  overflow: hidden;
}

.strength-fill {
  height: 100%;
  transition: width 0.3s, background-color 0.3s;
}

.strength-bar.weak .strength-fill { background: #ef4444; }
.strength-bar.medium .strength-fill { background: #f59e0b; }
.strength-bar.strong .strength-fill { background: #10b981; }

.strength-label {
  font-size: 14px;
  font-weight: 500;
  min-width: 60px;
}

.strength-bar.weak + .strength-label { color: #ef4444; }
.strength-bar.medium + .strength-label { color: #f59e0b; }
.strength-bar.strong + .strength-label { color: #10b981; }

.requirements-checklist {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  background: #f9fafb;
  border-radius: 6px;
}

.requirement {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: #6b7280;
  transition: color 0.2s;
}

.requirement.met {
  color: #10b981;
  font-weight: 500;
}

.requirement .icon {
  font-weight: bold;
  width: 20px;
}

.form-fields {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.form-input {
  padding: 10px 14px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 14px;
  transition: border-color 0.2s;
}

.form-input:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.warning {
  background: #fef3c7;
  border: 1px solid #f59e0b;
  padding: 10px 14px;
  border-radius: 6px;
  color: #92400e;
  font-size: 14px;
}

.error {
  background: #fee2e2;
  border: 1px solid #ef4444;
  padding: 10px 14px;
  border-radius: 6px;
  color: #991b1b;
  font-size: 14px;
}

.submit-button {
  padding: 10px 20px;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.2s;
}

.submit-button:hover:not(:disabled) {
  background: #2563eb;
}

.submit-button:disabled {
  background: #9ca3af;
  cursor: not-allowed;
}
</style>
```

**Step 2: Commit**

```bash
git add shared-components/PasswordChangeForm.vue
git commit -m "feat(shared): create PasswordChangeForm component (#635)"
```

---

## Phase 5: Frontend - AutoBot Vue Integration

### Task 5.1: Create ProfileModal Component

**Files:**
- Create: `autobot-vue/src/components/profile/ProfileModal.vue`

**Step 1: Create component**

```vue
<!-- autobot-vue/src/components/profile/ProfileModal.vue -->
<template>
  <div v-if="isOpen" class="modal-overlay" @click="handleClose">
    <div class="modal-content" @click.stop>
      <div class="modal-header">
        <h2>Profile Settings</h2>
        <button @click="handleClose" class="close-button">&times;</button>
      </div>

      <div class="modal-body">
        <!-- User Info Section -->
        <div class="profile-section">
          <h3>Account Information</h3>
          <div class="info-grid">
            <div class="info-row">
              <label>Username:</label>
              <span>{{ currentUser?.username || 'N/A' }}</span>
            </div>
            <div class="info-row">
              <label>Email:</label>
              <span>{{ currentUser?.email || 'N/A' }}</span>
            </div>
            <div class="info-row">
              <label>Last Login:</label>
              <span>{{ formatDate(currentUser?.last_login_at) }}</span>
            </div>
          </div>
        </div>

        <!-- Password Change Section -->
        <div class="profile-section">
          <h3>Change Password</h3>
          <PasswordChangeForm
            v-if="currentUser?.id"
            :user-id="currentUser.id"
            :require-current-password="true"
            @success="handlePasswordChanged"
            @error="handleError"
          />
        </div>
      </div>

      <!-- Success Toast -->
      <div v-if="successMessage" class="toast success">
        ✓ {{ successMessage }}
      </div>

      <!-- Error Toast -->
      <div v-if="errorMessage" class="toast error">
        ✗ {{ errorMessage }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import PasswordChangeForm from '@/../shared-components/PasswordChangeForm.vue'
import { useAuthStore } from '@/stores/auth'

const props = defineProps({
  isOpen: { type: Boolean, default: false }
})

const emit = defineEmits(['close'])

const authStore = useAuthStore()
const currentUser = computed(() => authStore.user)
const successMessage = ref(null)
const errorMessage = ref(null)

function handleClose() {
  emit('close')
}

function handlePasswordChanged(message) {
  successMessage.value = 'Password changed successfully. Other sessions have been logged out.'
  setTimeout(() => { successMessage.value = null }, 5000)
}

function handleError(error) {
  errorMessage.value = error
  setTimeout(() => { errorMessage.value = null }, 5000)
}

function formatDate(dateString) {
  if (!dateString) return 'Never'
  const date = new Date(dateString)
  return date.toLocaleDateString() + ' ' + date.toLocaleTimeString()
}
</script>

<style scoped>
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
  border-radius: 12px;
  width: 90%;
  max-width: 600px;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px;
  border-bottom: 1px solid #e5e7eb;
}

.modal-header h2 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  color: #111827;
}

.close-button {
  background: none;
  border: none;
  font-size: 32px;
  color: #6b7280;
  cursor: pointer;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.close-button:hover {
  background: #f3f4f6;
}

.modal-body {
  padding: 24px;
}

.profile-section {
  margin-bottom: 32px;
}

.profile-section:last-child {
  margin-bottom: 0;
}

.profile-section h3 {
  font-size: 18px;
  font-weight: 600;
  color: #111827;
  margin-bottom: 16px;
}

.info-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  padding: 12px;
  background: #f9fafb;
  border-radius: 6px;
}

.info-row label {
  font-weight: 500;
  color: #6b7280;
}

.info-row span {
  color: #111827;
}

.toast {
  position: fixed;
  bottom: 24px;
  right: 24px;
  padding: 16px 20px;
  border-radius: 8px;
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
  font-weight: 500;
  animation: slideIn 0.3s ease-out;
  z-index: 1100;
}

.toast.success {
  background: #10b981;
  color: white;
}

.toast.error {
  background: #ef4444;
  color: white;
}

@keyframes slideIn {
  from {
    transform: translateX(100%);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}
</style>
```

**Step 2: Commit**

```bash
git add autobot-vue/src/components/profile/ProfileModal.vue
git commit -m "feat(autobot-vue): create ProfileModal with password change (#635)"
```

---

## Phase 6: Frontend - SLM Admin Integration

### Task 6.1: Update UserManagementSettings to Use Shared Component

**Files:**
- Modify: `slm-admin/src/views/settings/admin/UserManagementSettings.vue`

**Step 1: Remove old password change code (lines 160-197)**

**Step 2: Import shared component and update template**

Find the password change modal section and replace with:

```vue
<script setup>
// Add import at top
import PasswordChangeForm from '@/../shared-components/PasswordChangeForm.vue'

// ... existing code ...

// Add computed for admin reset mode
const isAdminReset = computed(() => {
  // Admin resetting another user's password doesn't require current password
  return isAdmin.value && selectedUser.value?.id !== currentUser.value?.id
})
</script>

<template>
  <!-- Find the password change modal and replace content with: -->
  <div v-if="showChangePasswordModal" class="modal">
    <div class="modal-content">
      <h3>Change Password</h3>
      <PasswordChangeForm
        v-if="selectedUser?.id"
        :user-id="selectedUser.id"
        :require-current-password="!isAdminReset"
        @success="handlePasswordChangeSuccess"
        @error="handlePasswordChangeError"
      />
    </div>
  </div>
</template>
```

**Step 3: Update handlers**

```javascript
function handlePasswordChangeSuccess(message) {
  success.value = message
  showChangePasswordModal.value = false
  setTimeout(() => { success.value = null }, 3000)
}

function handlePasswordChangeError(error) {
  errorMessage.value = error
  setTimeout(() => { errorMessage.value = null }, 5000)
}
```

**Step 4: Commit**

```bash
git add slm-admin/src/views/settings/admin/UserManagementSettings.vue
git commit -m "feat(slm-admin): use shared PasswordChangeForm component (#635)"
```

---

## Phase 7: Testing & Documentation

### Task 7.1: Run All Backend Tests

**Step 1: Run tests**

```bash
cd /home/kali/Desktop/AutoBot/.worktrees/feature/user-password-change
pytest tests/user_management/services/test_session_service.py -v
pytest tests/user_management/middleware/test_rate_limit.py -v
pytest tests/user_management/services/test_user_service.py -v
pytest tests/api/user_management/test_users_password_change.py -v
```

**Step 2: Verify all pass**

Expected: All tests PASSED

**Step 3: Commit if fixes needed**

```bash
git add <any-fixed-files>
git commit -m "test(password): fix failing tests (#635)"
```

---

### Task 7.2: Update API Documentation

**Files:**
- Modify: `docs/api/COMPREHENSIVE_API_DOCUMENTATION.md`

**Step 1: Add password change endpoint documentation**

Find the Users API section and add:

```markdown
### Change User Password

**Endpoint:** `POST /api/users/{user_id}/change-password`

**Description:** Change user password with rate limiting and session invalidation.

**Rate Limit:** 3 attempts per 30 minutes

**Request:**
```json
{
  "current_password": "OldPass123",  // Optional for admin resets
  "new_password": "NewPass456"      // Must meet complexity requirements
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
  "detail": "Too many password change attempts. Try again in 27 minutes."
}
```

**Response (Invalid Current Password):**
```json
{
  "status": 401,
  "detail": "Current password is incorrect"
}
```

**Password Requirements:**
- At least 8 characters
- One uppercase letter
- One lowercase letter
- One number

**Security Notes:**
- Invalidates all other user sessions on password change
- Current session remains active
- Rate limited to prevent brute force attacks
```

**Step 2: Commit**

```bash
git add docs/api/COMPREHENSIVE_API_DOCUMENTATION.md
git commit -m "docs(api): document password change endpoint (#635)"
```

---

### Task 7.3: Update GitHub Issue

**Step 1: Add completion comment to issue**

```bash
# Use GitHub CLI to add comment
gh issue comment 635 --body "✅ **Implementation Complete**

**Backend:**
- ✅ SessionService for JWT token invalidation via Redis
- ✅ Rate limiting middleware (3 attempts / 30 min)
- ✅ Integration with UserService.change_password()
- ✅ API endpoint updated with rate limiting

**Frontend:**
- ✅ Shared PasswordChangeForm component with strength indicator
- ✅ ProfileModal in autobot-vue
- ✅ SLM admin integration

**Testing:**
- ✅ Backend unit tests
- ✅ API integration tests
- ✅ All tests passing

**Branch:** feature/user-password-change
**Ready for review and merge**"
```

**Step 2: Update issue status**

```bash
gh issue edit 635 --add-label "ready-for-review"
```

---

## Completion Checklist

- [ ] Phase 1: SessionService implemented and tested
- [ ] Phase 2: Rate limiting middleware implemented and tested
- [ ] Phase 3: Backend integration complete
- [ ] Phase 4: Shared component created
- [ ] Phase 5: AutoBot Vue integration complete
- [ ] Phase 6: SLM admin integration complete
- [ ] Phase 7: All tests passing
- [ ] Documentation updated
- [ ] GitHub issue updated with completion comment

---

## Next Steps After Implementation

1. **Code Review:** Use `superpowers:requesting-code-review` to request review
2. **Manual Testing:** Test in dev environment
3. **Merge Decision:** Use `superpowers:finishing-a-development-branch` for merge options
4. **Store in Memory:** Save completion details to Memory MCP

---

**Total Estimated Time:** 4-6 hours for complete implementation following TDD approach
