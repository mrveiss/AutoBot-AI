# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Database Helpers - Shared utility functions for database operations.

This module provides common database operations used across both
synchronous and asynchronous database pool modules.

Extracted to eliminate code duplication (Issue #292).
"""

from typing import Any, Dict, List


def join_results(
    main_results: List[Dict[str, Any]],
    related_data: Dict[Any, List[Any]],
    join_key: str,
    related_key: str,
) -> List[Dict[str, Any]]:
    """
    Join main results with related data to prevent N+1 queries.

    This utility function attaches related data to main query results
    based on a shared key, enabling efficient batch loading patterns.

    Args:
        main_results: List of main query results (dicts)
        related_data: Dict of related data grouped by key value
        join_key: Key in main results to join on
        related_key: Name for related data in result

    Returns:
        main_results with related data attached

    Example:
        # Instead of N+1 queries:
        # for user in users:
        #     orders = get_orders_for_user(user.id)  # N queries

        # Use batch loading:
        users = get_all_users()
        all_orders = get_orders_for_user_ids([u['id'] for u in users])
        orders_by_user = group_by(all_orders, 'user_id')
        result = join_results(users, orders_by_user, 'id', 'orders')
    """
    for item in main_results:
        key_value = item.get(join_key)
        item[related_key] = related_data.get(key_value, [])
    return main_results
