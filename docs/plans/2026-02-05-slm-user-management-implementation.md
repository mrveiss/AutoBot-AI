# SLM User Management Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate all user management functionality from main AutoBot backend to SLM server, making SLM the central authentication authority.

**Architecture:** Two PostgreSQL databases - `slm_users` (local on SLM) for fleet admins, `autobot_users` (on Redis VM) for application users. SLM manages both via dual database connections. Main AutoBot backend simplified to only authenticate against `autobot_users`.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL, Alembic, bcrypt, python-jose (JWT)

---

## Phase 1: Database Setup

### Task 1.1: Install PostgreSQL on SLM Server

**Files:**
- System: Install PostgreSQL on 172.16.168.19

**Step 1: SSH into SLM server**

```bash
ssh autobot@172.16.168.19
```

**Step 2: Install PostgreSQL**

```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib python3-dev libpq-dev
sudo systemctl enable postgresql
sudo systemctl start postgresql
```

**Step 3: Verify installation**

```bash
sudo -u postgres psql --version
```

Expected: `psql (PostgreSQL 14.x)`

**Step 4: Create database and user**

```bash
sudo -u postgres psql << 'EOF'
CREATE DATABASE slm_users;
CREATE USER slm_admin WITH PASSWORD 'GENERATE_SECURE_PASSWORD';
GRANT ALL PRIVILEGES ON DATABASE slm_users TO slm_admin;
\q
EOF
```

**Step 5: Configure PostgreSQL for local access**

```bash
sudo nano /etc/postgresql/14/main/pg_hba.conf
# Add line: host slm_users slm_admin 127.0.0.1/32 md5
sudo systemctl restart postgresql
```

**Step 6: Test connection**

```bash
psql -h 127.0.0.1 -U slm_admin -d slm_users -c "SELECT version();"
```

Expected: PostgreSQL version info

---

### Task 1.2: Setup AutoBot Users Database on Redis VM

**Files:**
- System: Configure PostgreSQL on 172.16.168.23

**Step 1: SSH into Redis VM**

```bash
ssh autobot@172.16.168.23
```

**Step 2: Verify PostgreSQL is installed**

```bash
sudo systemctl status postgresql
```

**Step 3: Create autobot_users database**

```bash
sudo -u postgres psql << 'EOF'
CREATE DATABASE autobot_users;
CREATE USER autobot_user_admin WITH PASSWORD 'GENERATE_SECURE_PASSWORD';
GRANT ALL PRIVILEGES ON DATABASE autobot_users TO autobot_user_admin;
\q
EOF
```

**Step 4: Configure PostgreSQL for network access**

```bash
sudo nano /etc/postgresql/14/main/pg_hba.conf
# Add: host autobot_users autobot_user_admin 172.16.168.0/24 md5
sudo nano /etc/postgresql/14/main/postgresql.conf
# Set: listen_addresses = '*'
sudo systemctl restart postgresql
```

**Step 5: Test remote connection from SLM**

```bash
# From SLM server (172.16.168.19)
psql -h 172.16.168.23 -U autobot_user_admin -d autobot_users -c "SELECT version();"
```

Expected: PostgreSQL version info

---

## Phase 2: Code Migration to SLM

### Task 2.1: Copy User Management Models to SLM

**Files:**
- Create: `slm-server/user_management/models/__init__.py`
- Create: `slm-server/user_management/models/base.py`
- Create: `slm-server/user_management/models/user.py`
- Create: `slm-server/user_management/models/team.py`
- Create: `slm-server/user_management/models/organization.py`
- Create: `slm-server/user_management/models/role.py`
- Create: `slm-server/user_management/models/api_key.py`
- Create: `slm-server/user_management/models/sso.py`
- Create: `slm-server/user_management/models/mfa.py`
- Create: `slm-server/user_management/models/audit.py`

**Step 1: Create directory structure**

```bash
cd /home/kali/Desktop/AutoBot/.worktrees/feature/slm-user-management/slm-server
mkdir -p user_management/models
touch user_management/__init__.py
touch user_management/models/__init__.py
```

**Step 2: Copy base.py from AutoBot**

```bash
cp /home/kali/Desktop/AutoBot/src/user_management/models/base.py \
   slm-server/user_management/models/base.py
```

**Step 3: Copy all model files**

```bash
for file in user.py team.py organization.py role.py api_key.py sso.py mfa.py audit.py; do
  cp /home/kali/Desktop/AutoBot/src/user_management/models/$file \
     slm-server/user_management/models/$file
done
```

**Step 4: Update imports in models/__init__.py**

Create: `slm-server/user_management/models/__init__.py`

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
User Management Models for SLM
"""

from user_management.models.base import Base, TimestampMixin, TenantMixin
from user_management.models.user import User
from user_management.models.team import Team, TeamMembership
from user_management.models.organization import Organization
from user_management.models.role import Role, Permission, RolePermission, UserRole
from user_management.models.api_key import APIKey
from user_management.models.sso import SSOProvider, UserSSOLink
from user_management.models.mfa import UserMFA
from user_management.models.audit import AuditLog

__all__ = [
    "Base",
    "TimestampMixin",
    "TenantMixin",
    "User",
    "Team",
    "TeamMembership",
    "Organization",
    "Role",
    "Permission",
    "RolePermission",
    "UserRole",
    "APIKey",
    "SSOProvider",
    "UserSSOLink",
    "UserMFA",
    "AuditLog",
]
```

**Step 5: Commit**

```bash
git add slm-server/user_management/
git commit -m "feat(slm): Copy user management models from AutoBot (#576)"
```

---

### Task 2.2: Create Dual Database Configuration

**Files:**
- Create: `slm-server/user_management/config.py`
- Create: `slm-server/user_management/database.py`

**Step 1: Create config.py with dual DB support**

Create: `slm-server/user_management/config.py`

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Dual Database Configuration for SLM User Management

Two PostgreSQL databases:
1. slm_users (local on 172.16.168.19) - SLM admin users
2. autobot_users (remote on 172.16.168.23) - AutoBot application users
"""

import os
from dataclasses import dataclass


@dataclass
class DatabaseConfig:
    """Database connection configuration."""

    host: str
    port: int
    database: str
    user: str
    password: str

    @property
    def url(self) -> str:
        """Generate async PostgreSQL connection URL."""
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )

    @property
    def sync_url(self) -> str:
        """Generate sync PostgreSQL connection URL (for Alembic)."""
        return (
            f"postgresql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )


def get_slm_db_config() -> DatabaseConfig:
    """Get SLM local database configuration."""
    return DatabaseConfig(
        host=os.getenv("SLM_POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("SLM_POSTGRES_PORT", "5432")),
        database=os.getenv("SLM_POSTGRES_DB", "slm_users"),
        user=os.getenv("SLM_POSTGRES_USER", "slm_admin"),
        password=os.getenv("SLM_POSTGRES_PASSWORD", ""),
    )


def get_autobot_db_config() -> DatabaseConfig:
    """Get AutoBot remote database configuration (on Redis VM)."""
    return DatabaseConfig(
        host=os.getenv("AUTOBOT_POSTGRES_HOST", "172.16.168.23"),
        port=int(os.getenv("AUTOBOT_POSTGRES_PORT", "5432")),
        database=os.getenv("AUTOBOT_POSTGRES_DB", "autobot_users"),
        user=os.getenv("AUTOBOT_POSTGRES_USER", "autobot_user_admin"),
        password=os.getenv("AUTOBOT_POSTGRES_PASSWORD", ""),
    )
```

**Step 2: Create database.py with dual engines**

Create: `slm-server/user_management/database.py`

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Dual Database Engine Management for SLM

Two SQLAlchemy async engines:
- slm_engine: Local SLM admin users
- autobot_engine: Remote AutoBot application users
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)

from user_management.config import get_slm_db_config, get_autobot_db_config

logger = logging.getLogger(__name__)

# Global engine instances
_slm_engine: AsyncEngine | None = None
_autobot_engine: AsyncEngine | None = None

# Session makers
_slm_session_maker: async_sessionmaker[AsyncSession] | None = None
_autobot_session_maker: async_sessionmaker[AsyncSession] | None = None


def get_slm_engine() -> AsyncEngine:
    """Get or create SLM database engine (local)."""
    global _slm_engine
    if _slm_engine is None:
        config = get_slm_db_config()
        _slm_engine = create_async_engine(
            config.url,
            echo=False,
            pool_size=10,
            max_overflow=10,
            pool_pre_ping=True,
        )
        logger.info("Created SLM database engine: %s", config.host)
    return _slm_engine


def get_autobot_engine() -> AsyncEngine:
    """Get or create AutoBot database engine (remote on Redis VM)."""
    global _autobot_engine
    if _autobot_engine is None:
        config = get_autobot_db_config()
        _autobot_engine = create_async_engine(
            config.url,
            echo=False,
            pool_size=20,
            max_overflow=20,
            pool_pre_ping=True,
        )
        logger.info("Created AutoBot database engine: %s", config.host)
    return _autobot_engine


def get_slm_session_maker() -> async_sessionmaker[AsyncSession]:
    """Get SLM session maker."""
    global _slm_session_maker
    if _slm_session_maker is None:
        engine = get_slm_engine()
        _slm_session_maker = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
    return _slm_session_maker


def get_autobot_session_maker() -> async_sessionmaker[AsyncSession]:
    """Get AutoBot session maker."""
    global _autobot_session_maker
    if _autobot_session_maker is None:
        engine = get_autobot_engine()
        _autobot_session_maker = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
    return _autobot_session_maker


@asynccontextmanager
async def get_slm_session() -> AsyncGenerator[AsyncSession, None]:
    """Get SLM database session (context manager)."""
    session_maker = get_slm_session_maker()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_autobot_session() -> AsyncGenerator[AsyncSession, None]:
    """Get AutoBot database session (context manager)."""
    session_maker = get_autobot_session_maker()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def health_check_slm() -> bool:
    """Check SLM database connection health."""
    try:
        async with get_slm_session() as session:
            await session.execute("SELECT 1")
        return True
    except Exception as e:
        logger.error("SLM database health check failed: %s", e)
        return False


async def health_check_autobot() -> bool:
    """Check AutoBot database connection health."""
    try:
        async with get_autobot_session() as session:
            await session.execute("SELECT 1")
        return True
    except Exception as e:
        logger.error("AutoBot database health check failed: %s", e)
        return False
```

**Step 3: Commit**

```bash
git add slm-server/user_management/config.py slm-server/user_management/database.py
git commit -m "feat(slm): Add dual database configuration (#576)"
```

---

### Task 2.3: Copy User Management Services

**Files:**
- Create: `slm-server/user_management/services/__init__.py`
- Create: `slm-server/user_management/services/base_service.py`
- Create: `slm-server/user_management/services/user_service.py`
- Create: `slm-server/user_management/services/team_service.py`
- Create: `slm-server/user_management/services/organization_service.py`

**Step 1: Create services directory**

```bash
cd slm-server/user_management
mkdir -p services
touch services/__init__.py
```

**Step 2: Copy service files**

```bash
for file in base_service.py user_service.py team_service.py organization_service.py; do
  cp /home/kali/Desktop/AutoBot/src/user_management/services/$file \
     slm-server/user_management/services/$file
done
```

**Step 3: Update services/__init__.py**

Create: `slm-server/user_management/services/__init__.py`

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
User Management Services for SLM
"""

from user_management.services.user_service import UserService
from user_management.services.team_service import TeamService
from user_management.services.organization_service import OrganizationService

user_service = UserService()
team_service = TeamService()
organization_service = OrganizationService()

__all__ = [
    "UserService",
    "TeamService",
    "OrganizationService",
    "user_service",
    "team_service",
    "organization_service",
]
```

**Step 4: Commit**

```bash
git add slm-server/user_management/services/
git commit -m "feat(slm): Copy user management services from AutoBot (#576)"
```

---

### Task 2.4: Copy Schemas and Middleware

**Files:**
- Create: `slm-server/user_management/schemas/__init__.py`
- Create: `slm-server/user_management/schemas/user.py`
- Create: `slm-server/user_management/middleware/__init__.py`
- Create: `slm-server/user_management/middleware/rbac_middleware.py`

**Step 1: Copy schemas**

```bash
cd slm-server/user_management
mkdir -p schemas
cp /home/kali/Desktop/AutoBot/src/user_management/schemas/user.py schemas/
touch schemas/__init__.py
```

**Step 2: Copy middleware**

```bash
mkdir -p middleware
cp /home/kali/Desktop/AutoBot/src/user_management/middleware/rbac_middleware.py middleware/
touch middleware/__init__.py
```

**Step 3: Commit**

```bash
git add slm-server/user_management/schemas/ slm-server/user_management/middleware/
git commit -m "feat(slm): Copy schemas and middleware from AutoBot (#576)"
```

---

## Phase 3: Alembic Migrations Setup

### Task 3.1: Setup Alembic for Dual Databases

**Files:**
- Create: `slm-server/migrations/alembic.ini`
- Create: `slm-server/migrations/env.py`
- Create: `slm-server/migrations/script.py.mako`

**Step 1: Install Alembic**

```bash
cd /home/kali/Desktop/AutoBot/.worktrees/feature/slm-user-management
pip install alembic
```

**Step 2: Initialize Alembic in slm-server**

```bash
cd slm-server
alembic init migrations
```

**Step 3: Create alembic.ini for dual databases**

Create: `slm-server/alembic.ini`

```ini
# AutoBot - AI-Powered Automation Platform
# Alembic configuration for SLM dual databases

[alembic]
script_location = migrations
prepend_sys_path = .
version_path_separator = os

# Dual database setup
# Use --name slm or --name autobot to select database
[slm]
sqlalchemy.url = driver://user:pass@localhost/slm_users

[autobot]
sqlalchemy.url = driver://user:pass@localhost/autobot_users

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

**Step 4: Update env.py for dual databases**

Create: `slm-server/migrations/env.py`

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Alembic Environment Configuration - Dual Database Support

Usage:
  alembic -n slm upgrade head      # Migrate SLM database
  alembic -n autobot upgrade head  # Migrate AutoBot database
"""

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Add parent directory to path for imports
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from user_management.models.base import Base
from user_management.config import get_slm_db_config, get_autobot_db_config

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata
target_metadata = Base.metadata


def get_url():
    """Get database URL based on --name parameter."""
    # Check which database to migrate
    db_name = context.get_x_argument(as_dictionary=True).get('name', 'slm')

    if db_name == 'slm':
        db_config = get_slm_db_config()
    elif db_name == 'autobot':
        db_config = get_autobot_db_config()
    else:
        raise ValueError(f"Unknown database: {db_name}. Use 'slm' or 'autobot'")

    return db_config.url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in async mode."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

**Step 5: Commit**

```bash
git add slm-server/alembic.ini slm-server/migrations/
git commit -m "feat(slm): Setup Alembic for dual database migrations (#576)"
```

---

### Task 3.2: Create Initial Migration

**Files:**
- Create: `slm-server/migrations/versions/20260205_001_initial_user_management.py`

**Step 1: Generate migration**

```bash
cd slm-server
alembic -x name=slm revision --autogenerate -m "Initial user management schema"
```

**Step 2: Review generated migration**

Check: `slm-server/migrations/versions/XXXX_initial_user_management.py`

Verify it includes all tables: users, teams, organizations, roles, permissions, etc.

**Step 3: Run migration on SLM database**

```bash
alembic -x name=slm upgrade head
```

Expected: All tables created in `slm_users` database

**Step 4: Run migration on AutoBot database**

```bash
alembic -x name=autobot upgrade head
```

Expected: All tables created in `autobot_users` database

**Step 5: Verify tables exist**

```bash
# SLM database
psql -h 127.0.0.1 -U slm_admin -d slm_users -c "\dt"

# AutoBot database
psql -h 172.16.168.23 -U autobot_user_admin -d autobot_users -c "\dt"
```

Expected: List of all user management tables

**Step 6: Commit**

```bash
git add slm-server/migrations/versions/
git commit -m "feat(slm): Create initial user management migration (#576)"
```

---

## Phase 4: SLM API Endpoints

### Task 4.1: Create SLM User API Endpoints

**Files:**
- Create: `slm-server/api/slm_users.py`
- Create: `slm-server/api/slm_auth.py`

**Step 1: Create slm_users.py**

Create: `slm-server/api/slm_users.py`

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Admin User Management API

Manages users in the local SLM database (172.16.168.19:5432/slm_users).
These are fleet administrators who can access the SLM admin dashboard.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from models.schemas import UserCreate, UserUpdate, UserResponse
from services.auth import get_current_user, require_admin
from user_management.database import get_slm_session
from user_management.services import user_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/slm-users", tags=["slm-users"])


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_slm_user(
    user_data: UserCreate,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_slm_session),
) -> UserResponse:
    """Create a new SLM admin user."""
    logger.info("Creating SLM user: %s", user_data.username)
    try:
        user = await user_service.create_user(db, user_data)
        return UserResponse.model_validate(user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("", response_model=List[UserResponse])
async def list_slm_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: str = Query(None),
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_slm_session),
) -> List[UserResponse]:
    """List SLM admin users with pagination and search."""
    logger.info("Listing SLM users (skip=%d, limit=%d, search=%s)", skip, limit, search)
    users = await user_service.list_users(db, skip=skip, limit=limit, search=search)
    return [UserResponse.model_validate(user) for user in users]


@router.get("/{user_id}", response_model=UserResponse)
async def get_slm_user(
    user_id: str,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_slm_session),
) -> UserResponse:
    """Get SLM user by ID."""
    user = await user_service.get_user(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return UserResponse.model_validate(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_slm_user(
    user_id: str,
    updates: UserUpdate,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_slm_session),
) -> UserResponse:
    """Update SLM user."""
    logger.info("Updating SLM user: %s", user_id)
    user = await user_service.update_user(db, user_id, updates)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return UserResponse.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_slm_user(
    user_id: str,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_slm_session),
) -> None:
    """Delete SLM user."""
    logger.info("Deleting SLM user: %s", user_id)
    success = await user_service.delete_user(db, user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
```

**Step 2: Create slm_auth.py**

Create: `slm-server/api/slm_auth.py`

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Authentication API

Handles login/logout for SLM admin users.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from models.schemas import TokenRequest, TokenResponse
from services.auth import auth_service, get_current_user
from user_management.database import get_slm_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/slm-auth", tags=["slm-auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    request: TokenRequest,
    db: Annotated[AsyncSession, Depends(get_slm_session)],
) -> TokenResponse:
    """Authenticate SLM admin user and return JWT token."""
    user = await auth_service.authenticate_user(db, request.username, request.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.info("SLM admin logged in: %s", user.username)
    return await auth_service.create_token_response(user)


@router.get("/me", response_model=dict)
async def get_current_user_info(
    current_user: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """Get current SLM admin user information."""
    return {
        "username": current_user.get("sub"),
        "is_admin": current_user.get("admin", False),
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    current_user: Annotated[dict, Depends(get_current_user)],
) -> None:
    """Logout (client-side token invalidation)."""
    logger.info("SLM admin logged out: %s", current_user.get("sub"))
```

**Step 3: Commit**

```bash
git add slm-server/api/slm_users.py slm-server/api/slm_auth.py
git commit -m "feat(slm): Add SLM admin user management API endpoints (#576)"
```

---

### Task 4.2: Create AutoBot User API Endpoints

**Files:**
- Create: `slm-server/api/autobot_users.py`
- Create: `slm-server/api/autobot_teams.py`

**Step 1: Create autobot_users.py**

Create: `slm-server/api/autobot_users.py`

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot User Management API

Manages users in the remote AutoBot database (172.16.168.23:5432/autobot_users).
These are application users who can access AutoBot chat and tools.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from models.schemas import UserCreate, UserUpdate, UserResponse
from services.auth import require_admin
from user_management.database import get_autobot_session
from user_management.services import user_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/autobot-users", tags=["autobot-users"])


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_autobot_user(
    user_data: UserCreate,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_autobot_session),
) -> UserResponse:
    """Create a new AutoBot application user."""
    logger.info("Creating AutoBot user: %s", user_data.username)
    try:
        user = await user_service.create_user(db, user_data)
        return UserResponse.model_validate(user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("", response_model=List[UserResponse])
async def list_autobot_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: str = Query(None),
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_autobot_session),
) -> List[UserResponse]:
    """List AutoBot users with pagination and search."""
    logger.info(
        "Listing AutoBot users (skip=%d, limit=%d, search=%s)", skip, limit, search
    )
    users = await user_service.list_users(db, skip=skip, limit=limit, search=search)
    return [UserResponse.model_validate(user) for user in users]


@router.get("/{user_id}", response_model=UserResponse)
async def get_autobot_user(
    user_id: str,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_autobot_session),
) -> UserResponse:
    """Get AutoBot user by ID."""
    user = await user_service.get_user(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return UserResponse.model_validate(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_autobot_user(
    user_id: str,
    updates: UserUpdate,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_autobot_session),
) -> UserResponse:
    """Update AutoBot user."""
    logger.info("Updating AutoBot user: %s", user_id)
    user = await user_service.update_user(db, user_id, updates)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return UserResponse.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_autobot_user(
    user_id: str,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_autobot_session),
) -> None:
    """Delete AutoBot user."""
    logger.info("Deleting AutoBot user: %s", user_id)
    success = await user_service.delete_user(db, user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
```

**Step 2: Register new routers in main.py**

Modify: `slm-server/main.py`

Find the router registration section and add:

```python
# User Management APIs
from api.slm_users import router as slm_users_router
from api.slm_auth import router as slm_auth_router
from api.autobot_users import router as autobot_users_router

app.include_router(slm_users_router, prefix="/api")
app.include_router(slm_auth_router, prefix="/api")
app.include_router(autobot_users_router, prefix="/api")
```

**Step 3: Commit**

```bash
git add slm-server/api/autobot_users.py slm-server/main.py
git commit -m "feat(slm): Add AutoBot user management API endpoints (#576)"
```

---

## Phase 5: AutoBot Backend Updates

### Task 5.1: Update AutoBot Auth to Use Remote Database

**Files:**
- Modify: `backend/api/auth.py`
- Create: `backend/database/user_db.py`

**Step 1: Create user database connection utility**

Create: `backend/database/user_db.py`

```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
User Database Connection for AutoBot Backend

Connects to remote AutoBot user database on Redis VM.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


def get_autobot_user_engine() -> AsyncEngine:
    """Get or create AutoBot user database engine."""
    global _engine
    if _engine is None:
        host = os.getenv("AUTOBOT_POSTGRES_HOST", "172.16.168.23")
        port = int(os.getenv("AUTOBOT_POSTGRES_PORT", "5432"))
        database = os.getenv("AUTOBOT_POSTGRES_DB", "autobot_users")
        user = os.getenv("AUTOBOT_POSTGRES_USER", "autobot_user_admin")
        password = os.getenv("AUTOBOT_POSTGRES_PASSWORD", "")

        url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"

        _engine = create_async_engine(
            url,
            echo=False,
            pool_size=20,
            max_overflow=20,
            pool_pre_ping=True,
        )
        logger.info("Created AutoBot user database engine: %s:%d", host, port)
    return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Get session maker."""
    global _session_maker
    if _session_maker is None:
        engine = get_autobot_user_engine()
        _session_maker = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
    return _session_maker


@asynccontextmanager
async def get_user_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get user database session (context manager)."""
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

**Step 2: Update auth.py to use new database**

Modify: `backend/api/auth.py`

Replace the database import at the top:

```python
# OLD: from services.database import get_db
# NEW:
from backend.database.user_db import get_user_db_session as get_db
```

**Step 3: Test authentication endpoint**

```bash
# Start AutoBot backend
cd /home/kali/Desktop/AutoBot
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8001

# Test login endpoint
curl -X POST https://172.16.168.20:8443/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "password": "testpass"}'
```

Expected: JWT token or 401 error

**Step 4: Commit**

```bash
git add backend/database/user_db.py backend/api/auth.py
git commit -m "feat(backend): Connect auth to remote AutoBot user database (#576)"
```

---

### Task 5.2: Remove Old User Management from AutoBot

**Files:**
- Delete: `src/user_management/` (entire directory)
- Delete: `backend/api/user_management/` (entire directory)

**Step 1: Remove src/user_management**

```bash
cd /home/kali/Desktop/AutoBot/.worktrees/feature/slm-user-management
git rm -r src/user_management/
```

**Step 2: Remove backend/api/user_management**

```bash
git rm -r backend/api/user_management/
```

**Step 3: Update imports in other files**

Search for any remaining imports:

```bash
grep -r "from src.user_management" backend/ src/
grep -r "from backend.api.user_management" backend/ src/
```

Remove or update any found imports.

**Step 4: Commit**

```bash
git commit -m "refactor(backend): Remove user management code - migrated to SLM (#576)"
```

---

## Phase 6: Frontend Updates

### Task 6.1: Update SLM Admin UserManagementSettings

**Files:**
- Modify: `slm-admin/src/views/settings/admin/UserManagementSettings.vue`

**Step 1: Update API base URL**

Modify: `slm-admin/src/views/settings/admin/UserManagementSettings.vue`

Change the API base from AutoBot to SLM:

```typescript
// OLD
const API_BASE = '/autobot-api'

// NEW
const SLM_API_BASE = 'http://172.16.168.19:8000/api'
```

**Step 2: Add dual user management state**

Add new reactive state:

```typescript
// Separate state for SLM vs AutoBot users
const slmUsers = ref<UserResponse[]>([])
const autobotUsers = ref<UserResponse[]>([])
const activeTab = ref<'slm-admins' | 'autobot-users' | 'teams'>('slm-admins')
```

**Step 3: Add API functions for both databases**

```typescript
async function loadSLMUsers(): Promise<void> {
  loading.value = true
  error.value = null

  try {
    const response = await fetch(`${SLM_API_BASE}/slm-users`, {
      headers: { Authorization: `Bearer ${authStore.token}` }
    })
    slmUsers.value = await response.json()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load SLM users'
  } finally {
    loading.value = false
  }
}

async function loadAutoBotUsers(): Promise<void> {
  loading.value = true
  error.value = null

  try {
    const response = await fetch(`${SLM_API_BASE}/autobot-users`, {
      headers: { Authorization: `Bearer ${authStore.token}` }
    })
    autobotUsers.value = await response.json()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load AutoBot users'
  } finally {
    loading.value = false
  }
}
```

**Step 4: Update template with tabs**

Update the template to show tabs:

```vue
<template>
  <div class="p-6 space-y-6">
    <!-- Tab Navigation -->
    <div class="border-b border-gray-200">
      <nav class="flex gap-4">
        <button
          @click="activeTab = 'slm-admins'"
          :class="[
            'px-4 py-2 font-medium border-b-2 transition-colors',
            activeTab === 'slm-admins'
              ? 'border-primary-600 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          ]"
        >
          SLM Administrators
        </button>
        <button
          @click="activeTab = 'autobot-users'"
          :class="[
            'px-4 py-2 font-medium border-b-2 transition-colors',
            activeTab === 'autobot-users'
              ? 'border-primary-600 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          ]"
        >
          AutoBot Users
        </button>
        <button
          @click="activeTab = 'teams'"
          :class="[
            'px-4 py-2 font-medium border-b-2 transition-colors',
            activeTab === 'teams'
              ? 'border-primary-600 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          ]"
        >
          Teams
        </button>
      </nav>
    </div>

    <!-- SLM Admins Tab -->
    <div v-if="activeTab === 'slm-admins'">
      <h2 class="text-lg font-semibold mb-4">SLM Fleet Administrators</h2>
      <p class="text-sm text-gray-600 mb-4">
        These users can access the SLM admin dashboard to manage the entire AutoBot fleet.
      </p>
      <!-- User table for slmUsers -->
    </div>

    <!-- AutoBot Users Tab -->
    <div v-if="activeTab === 'autobot-users'">
      <h2 class="text-lg font-semibold mb-4">AutoBot Application Users</h2>
      <p class="text-sm text-gray-600 mb-4">
        These users can access AutoBot chat interface and tools.
      </p>
      <!-- User table for autobotUsers -->
    </div>

    <!-- Teams Tab -->
    <div v-if="activeTab === 'teams'">
      <h2 class="text-lg font-semibold mb-4">AutoBot Teams</h2>
      <p class="text-sm text-gray-600 mb-4">
        Organize AutoBot users into teams for collaboration.
      </p>
      <!-- Team management UI -->
    </div>
  </div>
</template>
```

**Step 5: Update onMounted to load both**

```typescript
onMounted(async () => {
  if (isAdmin.value) {
    await loadSLMUsers()
    await loadAutoBotUsers()
  }
})
```

**Step 6: Test in browser**

```bash
# Sync to frontend VM
./scripts/utilities/sync-to-vm.sh frontend slm-admin/src/ /home/autobot/AutoBot/slm-admin/src/

# Open in browser
# Navigate to: http://172.16.168.21:5173/settings/admin/users
```

**Step 7: Commit**

```bash
git add slm-admin/src/views/settings/admin/UserManagementSettings.vue
git commit -m "feat(slm-admin): Add dual user management UI for SLM and AutoBot (#576)"
```

---

## Phase 7: Environment Configuration

### Task 7.1: Update .env Files

**Files:**
- Modify: `.env.example`
- Create: `slm-server/.env.example`

**Step 1: Update main .env.example**

Modify: `.env.example`

Add PostgreSQL configuration for AutoBot users:

```bash
# AutoBot User Database (on Redis VM)
AUTOBOT_POSTGRES_HOST=172.16.168.23
AUTOBOT_POSTGRES_PORT=5432
AUTOBOT_POSTGRES_DB=autobot_users
AUTOBOT_POSTGRES_USER=autobot_user_admin
AUTOBOT_POSTGRES_PASSWORD=<GENERATE_SECURE_PASSWORD>
```

**Step 2: Create SLM .env.example**

Create: `slm-server/.env.example`

```bash
# SLM User Management Configuration

# SLM Local Database
SLM_POSTGRES_HOST=127.0.0.1
SLM_POSTGRES_PORT=5432
SLM_POSTGRES_DB=slm_users
SLM_POSTGRES_USER=slm_admin
SLM_POSTGRES_PASSWORD=<GENERATE_SECURE_PASSWORD>

# AutoBot Remote Database (on Redis VM)
AUTOBOT_POSTGRES_HOST=172.16.168.23
AUTOBOT_POSTGRES_PORT=5432
AUTOBOT_POSTGRES_DB=autobot_users
AUTOBOT_POSTGRES_USER=autobot_user_admin
AUTOBOT_POSTGRES_PASSWORD=<GENERATE_SECURE_PASSWORD>

# JWT Secret (shared with AutoBot for token validation)
SECRET_KEY=<GENERATE_SECURE_SECRET>
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

**Step 3: Commit**

```bash
git add .env.example slm-server/.env.example
git commit -m "docs(config): Add PostgreSQL configuration for dual databases (#576)"
```

---

## Phase 8: Testing & Verification

### Task 8.1: Create Initial Admin Users

**Files:**
- Create: `slm-server/scripts/create_admin.py`

**Step 1: Create admin user creation script**

Create: `slm-server/scripts/create_admin.py`

```python
#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Create Initial Admin Users

Creates admin users in both SLM and AutoBot databases.
"""

import asyncio
import sys

from user_management.database import get_slm_session, get_autobot_session
from user_management.services import user_service
from user_management.schemas.user import UserCreate


async def create_slm_admin():
    """Create initial SLM admin user."""
    async with get_slm_session() as db:
        user_data = UserCreate(
            username="slm_admin",
            password="ChangeMe123!",
            email="admin@slm.local",
            is_admin=True,
        )
        user = await user_service.create_user(db, user_data)
        print(f"✅ Created SLM admin user: {user.username}")


async def create_autobot_admin():
    """Create initial AutoBot admin user."""
    async with get_autobot_session() as db:
        user_data = UserCreate(
            username="autobot_admin",
            password="ChangeMe123!",
            email="admin@autobot.local",
            is_admin=True,
        )
        user = await user_service.create_user(db, user_data)
        print(f"✅ Created AutoBot admin user: {user.username}")


async def main():
    """Create admin users in both databases."""
    try:
        await create_slm_admin()
        await create_autobot_admin()
        print("\n✅ All admin users created successfully")
        print("⚠️  IMPORTANT: Change default passwords immediately!")
    except Exception as e:
        print(f"❌ Error creating admin users: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
```

**Step 2: Run the script**

```bash
cd slm-server
python scripts/create_admin.py
```

Expected:
```
✅ Created SLM admin user: slm_admin
✅ Created AutoBot admin user: autobot_admin

✅ All admin users created successfully
⚠️  IMPORTANT: Change default passwords immediately!
```

**Step 3: Verify users exist**

```bash
# SLM database
psql -h 127.0.0.1 -U slm_admin -d slm_users -c "SELECT username, is_admin FROM users;"

# AutoBot database
psql -h 172.16.168.23 -U autobot_user_admin -d autobot_users -c "SELECT username, is_admin FROM users;"
```

**Step 4: Commit**

```bash
git add slm-server/scripts/create_admin.py
git commit -m "feat(slm): Add admin user creation script (#576)"
```

---

### Task 8.2: End-to-End Testing

**Files:**
- Create: `tests/integration/test_user_management_migration.py`

**Step 1: Test SLM admin login**

```bash
curl -X POST http://172.16.168.19:8000/api/slm-auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "slm_admin", "password": "ChangeMe123!"}'
```

Expected: JWT token

**Step 2: Test AutoBot user login**

```bash
curl -X POST https://172.16.168.20:8443/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "autobot_admin", "password": "ChangeMe123!"}'
```

Expected: JWT token

**Step 3: Test SLM managing AutoBot users**

```bash
# Get SLM admin token
SLM_TOKEN=$(curl -s -X POST http://172.16.168.19:8000/api/slm-auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "slm_admin", "password": "ChangeMe123!"}' | jq -r '.access_token')

# Create AutoBot user from SLM
curl -X POST http://172.16.168.19:8000/api/autobot-users \
  -H "Authorization: Bearer $SLM_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "TestPass123!",
    "email": "test@autobot.local",
    "is_admin": false
  }'
```

Expected: Created user JSON

**Step 4: Test AutoBot can authenticate new user**

```bash
curl -X POST https://172.16.168.20:8443/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "password": "TestPass123!"}'
```

Expected: JWT token (proves AutoBot reads from same database)

**Step 5: Test SLM admin UI**

1. Open browser: http://172.16.168.21:5173
2. Login as SLM admin
3. Navigate to Settings → User Management
4. Verify two tabs: "SLM Administrators" and "AutoBot Users"
5. Verify SLM admin appears in first tab
6. Verify AutoBot users appear in second tab
7. Create a new AutoBot user
8. Verify it appears in the list

**Step 6: Document test results**

Create: `docs/testing/user-management-migration-results.md`

Document all test results with timestamps and screenshots.

**Step 7: Commit**

```bash
git add docs/testing/
git commit -m "test(slm): Document user management migration test results (#576)"
```

---

## Phase 9: Documentation & Cleanup

### Task 9.1: Update Documentation

**Files:**
- Modify: `docs/developer/PHASE_5_DEVELOPER_SETUP.md`
- Modify: `docs/api/COMPREHENSIVE_API_DOCUMENTATION.md`
- Create: `docs/architecture/user-management-architecture.md`

**Step 1: Update developer setup guide**

Modify: `docs/developer/PHASE_5_DEVELOPER_SETUP.md`

Add section on PostgreSQL databases:

```markdown
## PostgreSQL Databases

AutoBot uses two PostgreSQL databases for user management:

### 1. SLM Users Database
- **Location:** SLM Server (172.16.168.19:5432)
- **Database:** `slm_users`
- **Purpose:** Fleet administrator authentication
- **Managed by:** SLM server

### 2. AutoBot Users Database
- **Location:** Redis VM (172.16.168.23:5432)
- **Database:** `autobot_users`
- **Purpose:** Application user authentication
- **Managed by:** SLM server (remotely)
- **Used by:** AutoBot backend (for auth)

### Environment Configuration

Add to `.env`:

```
AUTOBOT_POSTGRES_HOST=172.16.168.23
AUTOBOT_POSTGRES_PORT=5432
AUTOBOT_POSTGRES_DB=autobot_users
AUTOBOT_POSTGRES_USER=autobot_user_admin
AUTOBOT_POSTGRES_PASSWORD=<password>
```

Add to `slm-server/.env`:

```
SLM_POSTGRES_HOST=127.0.0.1
SLM_POSTGRES_DB=slm_users
SLM_POSTGRES_USER=slm_admin
SLM_POSTGRES_PASSWORD=<password>

AUTOBOT_POSTGRES_HOST=172.16.168.23
AUTOBOT_POSTGRES_DB=autobot_users
AUTOBOT_POSTGRES_USER=autobot_user_admin
AUTOBOT_POSTGRES_PASSWORD=<password>
```
```

**Step 2: Update API documentation**

Modify: `docs/api/COMPREHENSIVE_API_DOCUMENTATION.md`

Add new SLM endpoints section.

**Step 3: Create architecture document**

Create: `docs/architecture/user-management-architecture.md`

Copy content from design document and update with implementation details.

**Step 4: Commit**

```bash
git add docs/
git commit -m "docs(slm): Update documentation for user management migration (#576)"
```

---

### Task 9.2: Final Cleanup and PR

**Step 1: Run all tests**

```bash
# Backend tests
pytest tests/

# Frontend type check
cd slm-admin
npm run type-check
```

**Step 2: Update system state**

Modify: `docs/system-state.md`

Add entry:

```markdown
## 2026-02-05 - User Management Migration (#576)

**Status:** ✅ Complete

Migrated all user management from main AutoBot backend to SLM server.

**Changes:**
- Two PostgreSQL databases: `slm_users` (SLM local) + `autobot_users` (Redis VM)
- SLM manages both user populations via dual database connections
- AutoBot backend simplified to only authenticate (no user management)
- SLM admin UI has tabs for SLM admins vs AutoBot users

**Impact:**
- SLM is now central authentication authority
- Clean separation: fleet admins vs application users
- No migration needed for end users (transparent change)
```

**Step 3: Create PR**

```bash
git push origin feature/slm-user-management-576

gh pr create \
  --title "feat(slm): Migrate user management to SLM (#576)" \
  --body "$(cat <<'EOF'
## Summary

Migrates all user management functionality from main AutoBot backend to SLM server, establishing SLM as the central authentication authority.

## Architecture

- **Two PostgreSQL databases:**
  - `slm_users` (local on SLM) - Fleet administrators
  - `autobot_users` (Redis VM) - Application users
- **SLM manages both** via dual database connections
- **Direct database access** for instant consistency

## Changes

- ✅ Copied all user management code to `slm-server/user_management/`
- ✅ Created dual database configuration with separate engines
- ✅ Setup Alembic migrations for both databases
- ✅ Added SLM API endpoints (`/api/slm-users`, `/api/autobot-users`)
- ✅ Updated AutoBot backend to connect to `autobot_users` database
- ✅ Removed old user management code from AutoBot
- ✅ Updated SLM admin UI with dual user management tabs
- ✅ Created admin user creation script
- ✅ End-to-end testing complete

## Testing

- [x] SLM admin can login
- [x] AutoBot user can login
- [x] SLM can create/manage AutoBot users
- [x] AutoBot authenticates against remote database
- [x] SLM admin UI shows both user populations
- [x] All API endpoints functional

## Related

- Design: docs/plans/2026-02-05-slm-user-management-design.md
- Implementation: docs/plans/2026-02-05-slm-user-management-implementation.md

🤖 Generated with Claude Code
EOF
)"
```

**Step 4: Final commit**

```bash
git add docs/system-state.md
git commit -m "docs(system): Update system state for user management migration (#576)"
git push
```

---

## Success Criteria Checklist

- [ ] SLM PostgreSQL database created on 172.16.168.19:5432
- [ ] AutoBot PostgreSQL database created on 172.16.168.23:5432
- [ ] All user management code migrated to `slm-server/user_management/`
- [ ] Dual database configuration working (two engines)
- [ ] Alembic migrations applied to both databases
- [ ] SLM admin API endpoints functional (`/api/slm-users`, `/api/slm-auth`)
- [ ] AutoBot user API endpoints functional (`/api/autobot-users`)
- [ ] AutoBot backend connects to remote `autobot_users` database
- [ ] Old user management code removed from AutoBot
- [ ] SLM admin UI shows dual user management tabs
- [ ] Initial admin users created in both databases
- [ ] SLM admin login works
- [ ] AutoBot user login works
- [ ] SLM can create/manage AutoBot users remotely
- [ ] AutoBot authenticates users from shared database
- [ ] All tests passing
- [ ] Documentation updated
- [ ] PR created and ready for review

---

## Rollback Plan

If issues arise during deployment:

1. **Restore AutoBot user management:**
   ```bash
   git revert <migration-commit-sha>
   git push
   ```

2. **Revert database changes:**
   ```bash
   # SLM database
   alembic -x name=slm downgrade base

   # AutoBot database
   alembic -x name=autobot downgrade base
   ```

3. **Restore AutoBot backend:**
   - Re-add `src/user_management/`
   - Re-add `backend/api/user_management/`
   - Revert `backend/api/auth.py` changes

4. **Restore frontend:**
   - Revert `UserManagementSettings.vue` to call AutoBot APIs

---

## Post-Migration Tasks

After successful deployment:

1. **Security:**
   - [ ] Change all default passwords
   - [ ] Rotate JWT secret keys
   - [ ] Enable PostgreSQL SSL connections
   - [ ] Review firewall rules for PostgreSQL ports

2. **Monitoring:**
   - [ ] Add PostgreSQL connection pool metrics
   - [ ] Monitor database query performance
   - [ ] Set up alerts for database connection failures

3. **Backup:**
   - [ ] Configure automated PostgreSQL backups
   - [ ] Test backup restoration procedures
   - [ ] Document disaster recovery process

4. **Future Enhancements:**
   - [ ] Add SSO integration (Phase 4 from #576)
   - [ ] Implement 2FA/MFA (Phase 5 from #576)
   - [ ] Add API key management (Phase 5 from #576)
   - [ ] Implement team-based permissions

---

**End of Implementation Plan**
