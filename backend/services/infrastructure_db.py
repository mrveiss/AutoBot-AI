"""
Infrastructure Database Service Layer

Provides complete CRUD operations and business logic for infrastructure management,
including host provisioning, credential management, deployment tracking, and audit logging.
"""

import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, Session, joinedload
from cryptography.fernet import Fernet

from backend.models.infrastructure import (
    Base,
    InfraHost,
    InfraRole,
    InfraCredential,
    InfraDeployment,
    InfraAuditLog
)

logger = logging.getLogger(__name__)


class InfrastructureDB:
    """
    Database service layer for infrastructure management operations.

    Provides:
    - Host inventory management
    - Role definitions and assignments
    - Encrypted credential storage
    - Deployment tracking
    - Comprehensive audit logging
    """

    def __init__(self, db_path: Optional[str] = None, encryption_key: Optional[bytes] = None):
        """
        Initialize infrastructure database service.

        Args:
            db_path: Path to SQLite database file (defaults to autobot_data.db)
            encryption_key: Fernet encryption key for credentials (auto-generated if not provided)
        """
        # Use existing autobot_data.db database
        if db_path is None:
            db_path = os.environ.get('DATABASE_PATH', '/home/kali/Desktop/AutoBot/autobot_data.db')

        self.db_path = db_path
        self.engine = create_engine(f'sqlite:///{db_path}', echo=False)

        # Create all tables if they don't exist
        Base.metadata.create_all(self.engine)
        logger.info(f"Infrastructure database initialized at {db_path}")

        # Create session factory
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

        # Initialize Fernet encryption for credentials
        if encryption_key is None:
            # Generate or load encryption key
            key_path = Path(db_path).parent / '.infra_encryption_key'
            if key_path.exists():
                with open(key_path, 'rb') as f:
                    encryption_key = f.read()
            else:
                encryption_key = Fernet.generate_key()
                with open(key_path, 'wb') as f:
                    f.write(encryption_key)
                os.chmod(key_path, 0o600)  # Restrict permissions
                logger.warning(f"Generated new encryption key at {key_path}")

        self.fernet = Fernet(encryption_key)

        # Initialize default roles
        self._init_roles()

    def _init_roles(self):
        """Initialize default infrastructure roles if database is empty."""
        with self.SessionLocal() as session:
            count = session.query(InfraRole).count()
            if count == 0:
                roles = [
                    InfraRole(
                        name='frontend',
                        description='Vue.js frontend server (port 5173)',
                        ansible_playbook_path='ansible/playbooks/deploy_role.yml',
                        required_ports=[5173]
                    ),
                    InfraRole(
                        name='redis',
                        description='Redis Stack data layer (port 6379)',
                        ansible_playbook_path='ansible/playbooks/deploy_role.yml',
                        required_ports=[6379]
                    ),
                    InfraRole(
                        name='npu-worker',
                        description='NPU hardware acceleration worker (port 8081)',
                        ansible_playbook_path='ansible/playbooks/deploy_role.yml',
                        required_ports=[8081]
                    ),
                    InfraRole(
                        name='ai-stack',
                        description='AI processing stack (port 8080)',
                        ansible_playbook_path='ansible/playbooks/deploy_role.yml',
                        required_ports=[8080]
                    ),
                    InfraRole(
                        name='browser',
                        description='Playwright browser automation (port 3000)',
                        ansible_playbook_path='ansible/playbooks/deploy_role.yml',
                        required_ports=[3000]
                    )
                ]
                session.add_all(roles)
                session.commit()
                logger.info("Initialized 5 default infrastructure roles")

    # ==================== Role Management ====================

    def get_roles(self) -> List[InfraRole]:
        """Get all infrastructure roles."""
        with self.SessionLocal() as session:
            return session.query(InfraRole).all()

    def get_role_by_name(self, name: str) -> Optional[InfraRole]:
        """Get role by name."""
        with self.SessionLocal() as session:
            return session.query(InfraRole).filter(InfraRole.name == name).first()

    # ==================== Host Management ====================

    def create_host(self, host_data: Dict[str, Any]) -> InfraHost:
        """
        Create new infrastructure host.

        Args:
            host_data: Dictionary with host details (hostname, ip_address, role_id, etc.)

        Returns:
            Created InfraHost instance
        """
        with self.SessionLocal() as session:
            host = InfraHost(**host_data)
            session.add(host)
            session.commit()
            session.refresh(host)

            # Audit log
            self._create_audit_log(
                session,
                action='create_host',
                resource_type='host',
                resource_id=host.id,
                details={'hostname': host.hostname, 'ip_address': host.ip_address}
            )

            logger.info(f"Created host: {host.hostname} ({host.ip_address})")
            return host

    def get_host(self, host_id: int) -> Optional[InfraHost]:
        """
        Get host by ID with eagerly loaded relationships.

        Uses eager loading to prevent N+1 queries and session detachment issues.
        """
        with self.SessionLocal() as session:
            return session.query(InfraHost).options(
                joinedload(InfraHost.role),
                joinedload(InfraHost.credentials),
                joinedload(InfraHost.deployments)
            ).filter(InfraHost.id == host_id).first()

    def get_host_by_ip(self, ip_address: str) -> Optional[InfraHost]:
        """
        Get host by IP address with eagerly loaded relationships.

        Uses eager loading to prevent N+1 queries and session detachment issues.
        """
        with self.SessionLocal() as session:
            return session.query(InfraHost).options(
                joinedload(InfraHost.role),
                joinedload(InfraHost.credentials),
                joinedload(InfraHost.deployments)
            ).filter(InfraHost.ip_address == ip_address).first()

    def get_hosts(self, filters: Optional[Dict] = None, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """
        Get hosts with optional filters and database-level pagination.

        PERFORMANCE OPTIMIZATIONS:
        - Uses eager loading (joinedload) to prevent N+1 query problem
        - Implements database-level pagination with OFFSET/LIMIT
        - Single query with JOINs instead of 101+ queries for 100 hosts

        Args:
            filters: Optional dict with filters (role, status)
            page: Page number (starts at 1)
            page_size: Number of hosts per page (default: 20)

        Returns:
            Dictionary containing:
            - hosts: List of InfraHost instances with eagerly loaded relationships
            - total: Total number of hosts matching filters
            - page: Current page number
            - page_size: Number of items per page
            - total_pages: Total number of pages
        """
        with self.SessionLocal() as session:
            # Build query with eager loading to prevent N+1 query problem
            # This loads all relationships in a single query with JOINs
            query = session.query(InfraHost).options(
                joinedload(InfraHost.role),           # Eager load role relationship
                joinedload(InfraHost.credentials),    # Eager load credentials relationship
                joinedload(InfraHost.deployments)     # Eager load deployments relationship
            )

            # Apply filters
            if filters:
                if 'role' in filters:
                    query = query.join(InfraRole).filter(InfraRole.name == filters['role'])
                if 'status' in filters:
                    query = query.filter(InfraHost.status == filters['status'])

            # Get total count for pagination metadata (before applying LIMIT/OFFSET)
            total_count = query.count()

            # Apply database-level pagination with OFFSET and LIMIT
            # This ensures only the requested page is loaded from database
            offset = (page - 1) * page_size
            hosts = query.offset(offset).limit(page_size).all()

            # Calculate total pages
            total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 0

            logger.info(
                f"Retrieved {len(hosts)} hosts (page {page}/{total_pages}, "
                f"total: {total_count}, filters: {filters})"
            )

            return {
                'hosts': hosts,
                'total': total_count,
                'page': page,
                'page_size': page_size,
                'total_pages': total_pages
            }

    def update_host_status(self, host_id: int, status: str, user_id: Optional[str] = None):
        """
        Update host status.

        Args:
            host_id: Host ID
            status: New status (new, provisioning, deployed, healthy, degraded, failed)
            user_id: Optional user ID for audit log
        """
        with self.SessionLocal() as session:
            host = session.query(InfraHost).filter(InfraHost.id == host_id).first()
            if host:
                old_status = host.status
                host.status = status
                host.last_seen_at = datetime.utcnow()
                session.commit()

                # Audit log
                self._create_audit_log(
                    session,
                    action='update_host_status',
                    resource_type='host',
                    resource_id=host_id,
                    details={'old_status': old_status, 'new_status': status},
                    user_id=user_id
                )

                logger.info(f"Updated host {host_id} status: {old_status} → {status}")

    def delete_host(self, host_id: int, user_id: Optional[str] = None):
        """
        Delete host (cascades to credentials and deployments).

        Args:
            host_id: Host ID to delete
            user_id: Optional user ID for audit log
        """
        with self.SessionLocal() as session:
            host = session.query(InfraHost).filter(InfraHost.id == host_id).first()
            if host:
                hostname = host.hostname
                session.delete(host)
                session.commit()

                # Audit log
                self._create_audit_log(
                    session,
                    action='delete_host',
                    resource_type='host',
                    resource_id=host_id,
                    details={'hostname': hostname},
                    user_id=user_id
                )

                logger.info(f"Deleted host {host_id} ({hostname})")

    # ==================== Credential Management ====================

    def store_ssh_credential(
        self,
        host_id: int,
        credential_type: str,
        value: str,
        user_id: Optional[str] = None
    ) -> InfraCredential:
        """
        Store encrypted SSH credential.

        Args:
            host_id: Host ID
            credential_type: 'password' or 'ssh_key'
            value: Plain text credential to encrypt
            user_id: Optional user ID for audit log

        Returns:
            Created InfraCredential instance
        """
        with self.SessionLocal() as session:
            # Encrypt credential
            encrypted_value = self.fernet.encrypt(value.encode()).decode()

            credential = InfraCredential(
                host_id=host_id,
                credential_type=credential_type,
                encrypted_value=encrypted_value,
                is_active=True
            )
            session.add(credential)
            session.commit()
            session.refresh(credential)

            # Audit log (without sensitive details)
            self._create_audit_log(
                session,
                action='store_credential',
                resource_type='credential',
                resource_id=credential.id,
                details={'host_id': host_id, 'credential_type': credential_type},
                user_id=user_id
            )

            logger.info(f"Stored {credential_type} credential for host {host_id}")
            return credential

    def get_active_credential(self, host_id: int, credential_type: str = 'ssh_key') -> Optional[str]:
        """
        Get decrypted active credential for host.

        Args:
            host_id: Host ID
            credential_type: Type of credential to retrieve

        Returns:
            Decrypted credential string or None
        """
        with self.SessionLocal() as session:
            credential = session.query(InfraCredential).filter(
                InfraCredential.host_id == host_id,
                InfraCredential.credential_type == credential_type,
                InfraCredential.is_active == True
            ).first()

            if credential:
                # Decrypt and return
                decrypted = self.fernet.decrypt(credential.encrypted_value.encode()).decode()
                return decrypted

            return None

    def deactivate_credentials(self, host_id: int, credential_type: Optional[str] = None, user_id: Optional[str] = None):
        """
        Deactivate credentials (for rotation).

        Args:
            host_id: Host ID
            credential_type: Optional specific credential type to deactivate
            user_id: Optional user ID for audit log
        """
        with self.SessionLocal() as session:
            query = session.query(InfraCredential).filter(
                InfraCredential.host_id == host_id,
                InfraCredential.is_active == True
            )

            if credential_type:
                query = query.filter(InfraCredential.credential_type == credential_type)

            credentials = query.all()

            for cred in credentials:
                cred.is_active = False

            session.commit()

            # Audit log
            self._create_audit_log(
                session,
                action='deactivate_credentials',
                resource_type='credential',
                resource_id=None,
                details={'host_id': host_id, 'credential_type': credential_type, 'count': len(credentials)},
                user_id=user_id
            )

            logger.info(f"Deactivated {len(credentials)} credentials for host {host_id}")

    # ==================== Deployment Management ====================

    def create_deployment(
        self,
        host_id: int,
        role: str,
        status: str = 'queued',
        user_id: Optional[str] = None
    ) -> InfraDeployment:
        """
        Create deployment record.

        Args:
            host_id: Host ID
            role: Role being deployed
            status: Initial status (default: 'queued')
            user_id: Optional user ID for audit log

        Returns:
            Created InfraDeployment instance
        """
        with self.SessionLocal() as session:
            deployment = InfraDeployment(
                host_id=host_id,
                role=role,
                status=status
            )
            session.add(deployment)
            session.commit()
            session.refresh(deployment)

            # Audit log
            self._create_audit_log(
                session,
                action='create_deployment',
                resource_type='deployment',
                resource_id=deployment.id,
                details={'host_id': host_id, 'role': role, 'status': status},
                user_id=user_id
            )

            logger.info(f"Created deployment {deployment.id} for host {host_id} (role: {role})")
            return deployment

    def update_deployment_status(
        self,
        deployment_id: int,
        status: str,
        error_message: Optional[str] = None,
        user_id: Optional[str] = None
    ):
        """
        Update deployment status.

        Args:
            deployment_id: Deployment ID
            status: New status (queued, running, success, failed, rolled_back)
            error_message: Optional error message if failed
            user_id: Optional user ID for audit log
        """
        with self.SessionLocal() as session:
            deployment = session.query(InfraDeployment).filter(
                InfraDeployment.id == deployment_id
            ).first()

            if deployment:
                old_status = deployment.status
                deployment.status = status

                if error_message:
                    deployment.error_message = error_message

                if status == 'running' and not deployment.started_at:
                    deployment.started_at = datetime.utcnow()
                elif status in ('success', 'failed', 'rolled_back'):
                    deployment.completed_at = datetime.utcnow()

                session.commit()

                # Audit log
                self._create_audit_log(
                    session,
                    action='update_deployment_status',
                    resource_type='deployment',
                    resource_id=deployment_id,
                    details={'old_status': old_status, 'new_status': status, 'has_error': bool(error_message)},
                    user_id=user_id
                )

                logger.info(f"Updated deployment {deployment_id} status: {old_status} → {status}")

    def get_deployments(self, host_id: Optional[int] = None, status: Optional[str] = None) -> List[InfraDeployment]:
        """
        Get deployments with optional filters.

        Args:
            host_id: Optional host ID filter
            status: Optional status filter

        Returns:
            List of InfraDeployment instances
        """
        with self.SessionLocal() as session:
            query = session.query(InfraDeployment)

            if host_id:
                query = query.filter(InfraDeployment.host_id == host_id)
            if status:
                query = query.filter(InfraDeployment.status == status)

            return query.order_by(InfraDeployment.created_at.desc()).all()

    # ==================== Audit Logging ====================

    def _create_audit_log(
        self,
        session: Session,
        action: str,
        resource_type: str,
        resource_id: Optional[int],
        details: Optional[Dict] = None,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ):
        """
        Internal method to create audit log entry.

        Args:
            session: Active database session
            action: Action performed
            resource_type: Type of resource affected
            resource_id: ID of affected resource
            details: Additional details as JSON
            user_id: User or service account
            ip_address: Source IP address
        """
        audit_log = InfraAuditLog(
            user_id=user_id or 'system',
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address
        )
        session.add(audit_log)
        session.commit()

    def get_audit_logs(
        self,
        resource_type: Optional[str] = None,
        resource_id: Optional[int] = None,
        limit: int = 100
    ) -> List[InfraAuditLog]:
        """
        Get audit logs with optional filters.

        Args:
            resource_type: Optional resource type filter
            resource_id: Optional resource ID filter
            limit: Maximum number of logs to return (default: 100)

        Returns:
            List of InfraAuditLog instances
        """
        with self.SessionLocal() as session:
            query = session.query(InfraAuditLog)

            if resource_type:
                query = query.filter(InfraAuditLog.resource_type == resource_type)
            if resource_id:
                query = query.filter(InfraAuditLog.resource_id == resource_id)

            return query.order_by(InfraAuditLog.timestamp.desc()).limit(limit).all()

    # ==================== Statistics & Health ====================

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get infrastructure statistics.

        Returns:
            Dictionary with counts and metrics
        """
        with self.SessionLocal() as session:
            stats = {
                'total_hosts': session.query(InfraHost).count(),
                'hosts_by_status': {},
                'total_roles': session.query(InfraRole).count(),
                'total_deployments': session.query(InfraDeployment).count(),
                'deployments_by_status': {},
                'active_credentials': session.query(InfraCredential).filter(
                    InfraCredential.is_active == True
                ).count(),
            }

            # Count hosts by status
            for status in ['new', 'provisioning', 'deployed', 'healthy', 'degraded', 'failed']:
                count = session.query(InfraHost).filter(InfraHost.status == status).count()
                if count > 0:
                    stats['hosts_by_status'][status] = count

            # Count deployments by status
            for status in ['queued', 'running', 'success', 'failed', 'rolled_back']:
                count = session.query(InfraDeployment).filter(InfraDeployment.status == status).count()
                if count > 0:
                    stats['deployments_by_status'][status] = count

            return stats
