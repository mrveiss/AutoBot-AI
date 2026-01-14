# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Database Service

Provides CRUD operations for SLM entities with state transition tracking.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.models.infrastructure import (
    Base,
    NodeState,
    ServiceType,
    SLMNode,
    SLMRole,
    SLMStateTransition,
    SLMDeployment,
    SLMMaintenanceWindow,
)
from backend.services.slm.state_machine import SLMStateMachine, InvalidStateTransition

logger = logging.getLogger(__name__)


class SLMDatabaseService:
    """
    Database service layer for SLM operations.

    Provides:
    - Node registry management with state machine
    - Role definitions
    - State transition audit logging
    - Deployment tracking
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize SLM database service.

        Args:
            db_path: Path to SQLite database (defaults to slm.db)
        """
        if db_path is None:
            db_path = "slm.db"

        self.db_path = db_path
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        Base.metadata.create_all(self.engine)

        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.state_machine = SLMStateMachine()

        logger.info("SLM database initialized at %s", db_path)

    # ==================== Node Management ====================

    def create_node(
        self,
        name: str,
        ip_address: str,
        ssh_port: int = 22,
        ssh_user: str = "autobot",
        capability_tags: Optional[List[str]] = None,
        current_role: Optional[str] = None,
    ) -> SLMNode:
        """Create a new node in UNKNOWN state."""
        with self.SessionLocal() as session:
            node = SLMNode(
                id=str(uuid4()),
                name=name,
                ip_address=ip_address,
                ssh_port=ssh_port,
                ssh_user=ssh_user,
                state=NodeState.UNKNOWN,
                capability_tags=capability_tags or [],
                current_role=current_role,
            )
            session.add(node)
            session.commit()
            session.refresh(node)

            logger.info("Created node: %s (%s)", name, ip_address)
            return node

    def get_node(self, node_id: str) -> Optional[SLMNode]:
        """Get node by ID."""
        with self.SessionLocal() as session:
            return session.query(SLMNode).filter(SLMNode.id == node_id).first()

    def get_node_by_name(self, name: str) -> Optional[SLMNode]:
        """Get node by name."""
        with self.SessionLocal() as session:
            return session.query(SLMNode).filter(SLMNode.name == name).first()

    def get_node_by_ip(self, ip_address: str) -> Optional[SLMNode]:
        """Get node by IP address."""
        with self.SessionLocal() as session:
            return session.query(SLMNode).filter(SLMNode.ip_address == ip_address).first()

    def get_all_nodes(self, state: Optional[NodeState] = None) -> List[SLMNode]:
        """Get all nodes, optionally filtered by state."""
        with self.SessionLocal() as session:
            query = session.query(SLMNode)
            if state:
                query = query.filter(SLMNode.state == state)
            return query.all()

    def delete_node(self, node_id: str) -> bool:
        """
        Delete a node by ID.

        Args:
            node_id: Node ID to delete

        Returns:
            True if node was deleted, False if not found
        """
        with self.SessionLocal() as session:
            node = session.query(SLMNode).filter(SLMNode.id == node_id).first()
            if not node:
                return False

            session.delete(node)
            session.commit()
            logger.info("Deleted node: %s", node_id)
            return True

    def update_node_state(
        self,
        node_id: str,
        new_state: NodeState,
        trigger: str = "api",
        details: Optional[Dict] = None,
        validate_transition: bool = True,
    ) -> SLMNode:
        """
        Update node state with transition validation and logging.

        Raises:
            InvalidStateTransition: If transition is not allowed
            ValueError: If node not found
        """
        with self.SessionLocal() as session:
            node = session.query(SLMNode).filter(SLMNode.id == node_id).first()
            if not node:
                raise ValueError(f"Node not found: {node_id}")

            old_state = node.state

            # Validate transition
            if validate_transition:
                self.state_machine.transition(old_state, new_state)

            # Update node
            node.state = new_state
            node.state_changed = datetime.utcnow()

            # Log transition
            transition = SLMStateTransition(
                node_id=node_id,
                from_state=old_state,
                to_state=new_state,
                trigger=trigger,
                details=details,
            )
            session.add(transition)
            session.commit()
            session.refresh(node)

            logger.info(
                "Node %s state: %s → %s (trigger: %s)",
                node.name, old_state.value, new_state.value, trigger,
            )
            return node

    def update_node_health(
        self,
        node_id: str,
        health_data: Dict,
        heartbeat_time: Optional[datetime] = None,
    ) -> SLMNode:
        """
        Update node health data and heartbeat.

        Note: health_data is accepted for API compatibility but currently
        not persisted. Future enhancement could store metrics in a separate
        health_metrics table for historical tracking.
        """
        with self.SessionLocal() as session:
            node = session.query(SLMNode).filter(SLMNode.id == node_id).first()
            if not node:
                raise ValueError(f"Node not found: {node_id}")

            node.last_health_check = datetime.utcnow()
            node.last_heartbeat = heartbeat_time or datetime.utcnow()
            node.consecutive_failures = 0  # Reset on successful health update

            session.commit()
            session.refresh(node)
            logger.debug("Updated health for node %s: %s", node.name, health_data)
            return node

    def increment_failure_count(self, node_id: str) -> int:
        """Increment consecutive failure count, return new count."""
        with self.SessionLocal() as session:
            node = session.query(SLMNode).filter(SLMNode.id == node_id).first()
            if node:
                node.consecutive_failures += 1
                session.commit()
                return node.consecutive_failures
        return 0

    def get_state_transitions(
        self, node_id: str, limit: int = 100
    ) -> List[SLMStateTransition]:
        """Get state transitions for a node."""
        with self.SessionLocal() as session:
            return (
                session.query(SLMStateTransition)
                .filter(SLMStateTransition.node_id == node_id)
                .order_by(SLMStateTransition.timestamp.desc())
                .limit(limit)
                .all()
            )

    # ==================== Role Management ====================

    def create_role(
        self,
        name: str,
        description: str = "",
        service_type: str = "stateless",
        services: Optional[List[str]] = None,
        required_tags: Optional[List[str]] = None,
        dependencies: Optional[List[str]] = None,
        health_checks: Optional[List[Dict]] = None,
        install_playbook: Optional[str] = None,
        purge_playbook: Optional[str] = None,
    ) -> SLMRole:
        """Create a new role definition."""
        with self.SessionLocal() as session:
            # Convert string to ServiceType enum
            service_type_enum = ServiceType.STATEFUL if service_type == "stateful" else ServiceType.STATELESS

            role = SLMRole(
                name=name,
                description=description,
                service_type=service_type_enum,
                services=services or [],
                required_tags=required_tags or [],
                dependencies=dependencies or [],
                health_checks=health_checks or [],
                install_playbook=install_playbook,
                purge_playbook=purge_playbook,
            )
            session.add(role)
            session.commit()
            session.refresh(role)

            logger.info("Created role: %s", name)
            return role

    def get_role(self, role_id: int) -> Optional[SLMRole]:
        """Get role by ID."""
        with self.SessionLocal() as session:
            return session.query(SLMRole).filter(SLMRole.id == role_id).first()

    def get_role_by_name(self, name: str) -> Optional[SLMRole]:
        """Get role by name."""
        with self.SessionLocal() as session:
            return session.query(SLMRole).filter(SLMRole.name == name).first()

    def get_all_roles(self) -> List[SLMRole]:
        """Get all role definitions."""
        with self.SessionLocal() as session:
            return session.query(SLMRole).all()

    # ==================== Statistics ====================

    def get_statistics(self) -> Dict:
        """Get SLM statistics."""
        with self.SessionLocal() as session:
            total_nodes = session.query(SLMNode).count()
            nodes_by_state = {}

            for state in NodeState:
                count = session.query(SLMNode).filter(
                    SLMNode.state == state
                ).count()
                if count > 0:
                    nodes_by_state[state.value] = count

            return {
                "total_nodes": total_nodes,
                "nodes_by_state": nodes_by_state,
                "total_roles": session.query(SLMRole).count(),
                "total_transitions": session.query(SLMStateTransition).count(),
            }
