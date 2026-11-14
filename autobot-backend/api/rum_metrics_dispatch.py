# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Record a frontend RUM metrics batch to Prometheus (Issue #476).

Moved out of ``api/rum.py`` unchanged (#16375), so the router file keeps only
the routes and their access posture.
"""

from typing import List

from api.schemas_analytics import (
    RumApiCallMetric,
    RumCriticalIssueMetric,
    RumJsErrorMetric,
    RumMetrics,
    RumPageMetrics,
    RumResourceMetric,
    RumSessionMetric,
    RumUserActionMetric,
    RumWebSocketMetric,
)


def _process_page_metrics(metrics_manager, page_metrics: RumPageMetrics) -> None:
    """Process page performance metrics."""
    if page_metrics.load_time_seconds is not None:
        metrics_manager.record_frontend_page_load(page_metrics.page, page_metrics.load_time_seconds)
    if page_metrics.fcp_seconds is not None:
        metrics_manager.record_frontend_fcp(page_metrics.page, page_metrics.fcp_seconds)
    if page_metrics.lcp_seconds is not None:
        metrics_manager.record_frontend_lcp(page_metrics.page, page_metrics.lcp_seconds)
    if page_metrics.tti_seconds is not None:
        metrics_manager.record_frontend_tti(page_metrics.page, page_metrics.tti_seconds)
    if page_metrics.dom_loaded_seconds is not None:
        metrics_manager.record_frontend_dom_loaded(page_metrics.page, page_metrics.dom_loaded_seconds)


def _process_api_calls(metrics_manager, api_calls: List[RumApiCallMetric]) -> None:
    """Process API call metrics."""
    for call in api_calls:
        metrics_manager.record_frontend_api_request(
            endpoint=call.endpoint,
            method=call.method,
            status=call.status,
            latency_seconds=call.latency_seconds,
            is_slow=call.is_slow,
            is_timeout=call.is_timeout,
        )
        if call.error_type:
            metrics_manager.record_frontend_api_error(call.endpoint, call.method, call.error_type)


def _process_js_errors(metrics_manager, js_errors: List[RumJsErrorMetric]) -> None:
    """Process JavaScript error metrics."""
    for error in js_errors:
        if error.is_rejection:
            metrics_manager.record_frontend_unhandled_rejection(error.page)
        else:
            metrics_manager.record_frontend_js_error(error.error_type, error.page)
        if error.component:
            metrics_manager.record_frontend_component_error(error.component, error.error_type)


def _process_user_actions(metrics_manager, user_actions: List[RumUserActionMetric]) -> None:
    """Process user action metrics."""
    for action in user_actions:
        metrics_manager.record_frontend_user_action(action.action_type, action.page)
        if action.form_name and action.form_status:
            metrics_manager.record_frontend_form_submission(action.form_name, action.form_status)


def _process_session_metric(metrics_manager, session: RumSessionMetric) -> None:
    """Process session metrics."""
    if session.event == "start":
        metrics_manager.record_frontend_session_start()
    elif session.event == "end" and session.duration_seconds is not None:
        metrics_manager.record_frontend_session_duration(session.duration_seconds)


def _process_websocket_events(metrics_manager, websocket_events: List[RumWebSocketMetric]) -> None:
    """Process WebSocket event metrics."""
    for ws_event in websocket_events:
        metrics_manager.record_frontend_ws_event(ws_event.event)
        if ws_event.direction and ws_event.event_type:
            metrics_manager.record_frontend_ws_message(ws_event.direction, ws_event.event_type)


def _process_resources(metrics_manager, resources: List[RumResourceMetric]) -> None:
    """Process resource load metrics."""
    for resource in resources:
        metrics_manager.record_frontend_resource_load(resource.resource_type, resource.load_time_seconds)
        if resource.is_slow:
            metrics_manager.record_frontend_slow_resource(resource.resource_type)


def _process_critical_issues(metrics_manager, critical_issues: List[RumCriticalIssueMetric]) -> None:
    """Process critical issue metrics."""
    for issue in critical_issues:
        metrics_manager.record_frontend_critical_issue(issue.issue_type)


def dispatch_and_tally_rum_metrics(metrics_manager, metrics: RumMetrics) -> int:
    """Record one RUM metrics batch to Prometheus; returns how many were recorded. Ref: #1088."""
    recorded_count = 0

    if metrics.page_metrics:
        _process_page_metrics(metrics_manager, metrics.page_metrics)
        recorded_count += 1

    if metrics.api_calls:
        _process_api_calls(metrics_manager, metrics.api_calls)
        recorded_count += len(metrics.api_calls)

    if metrics.js_errors:
        _process_js_errors(metrics_manager, metrics.js_errors)
        recorded_count += len(metrics.js_errors)

    if metrics.user_actions:
        _process_user_actions(metrics_manager, metrics.user_actions)
        recorded_count += len(metrics.user_actions)

    if metrics.session:
        _process_session_metric(metrics_manager, metrics.session)
        recorded_count += 1

    if metrics.websocket_events:
        _process_websocket_events(metrics_manager, metrics.websocket_events)
        recorded_count += len(metrics.websocket_events)

    if metrics.resources:
        _process_resources(metrics_manager, metrics.resources)
        recorded_count += len(metrics.resources)

    if metrics.critical_issues:
        _process_critical_issues(metrics_manager, metrics.critical_issues)
        recorded_count += len(metrics.critical_issues)

    return recorded_count
