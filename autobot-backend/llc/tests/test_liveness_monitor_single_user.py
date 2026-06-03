# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Test LivenessMonitor single_user mode behavior (GH#9089)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.scheduler.liveness_monitor import LivenessMonitor
from user_management.config import DeploymentConfig, DeploymentMode, FeatureFlags


@pytest.mark.asyncio
async def test_single_user_mode_skips_db_checks() -> None:
    """In single_user mode, _check_once() returns early without DB access."""
    monitor = LivenessMonitor(poll_interval=9999)

    single_user_config = DeploymentConfig(
        mode=DeploymentMode.SINGLE_USER,
        features=FeatureFlags(),
        postgres_enabled=False,
    )

    with (
        patch("llc.scheduler.liveness_monitor.get_deployment_config", return_value=single_user_config),
        patch("llc.scheduler.liveness_monitor.get_async_session_factory") as mock_factory,
    ):
        await monitor._check_once()

        # get_async_session_factory should never be called in single_user mode
        mock_factory.assert_not_called()


@pytest.mark.asyncio
async def test_multi_user_mode_proceeds_normally() -> None:
    """In multi-user modes, _check_once() proceeds with DB checks."""
    monitor = LivenessMonitor(poll_interval=9999)

    multi_user_config = DeploymentConfig(
        mode=DeploymentMode.SINGLE_COMPANY,
        features=FeatureFlags(user_management=True),
        postgres_enabled=True,
    )

    # Create session mock matching the pattern in test_liveness_monitor.py
    session = AsyncMock()
    # Simplest test: just verify the factory is called and no exceptions are raised
    # We don't need to mock the full query chain for this test
    session.execute = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = []
    session.execute.return_value = execute_result

    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("llc.scheduler.liveness_monitor.get_deployment_config", return_value=multi_user_config),
        patch("llc.scheduler.liveness_monitor.get_async_session_factory", return_value=factory) as mock_factory,
    ):
        await monitor._check_once()

        # In multi-user mode, the factory should be called
        mock_factory.assert_called_once()
