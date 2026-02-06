# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Frontend Metrics Recorder

Metrics for Real User Monitoring (RUM) data collected from the frontend.
Created as part of Issue #476 - Implement frontend metrics export to Prometheus.

Covers:
- Page performance metrics (load time, FCP, LCP, TTI)
- Frontend API call metrics (latency, errors)
- JavaScript error tracking
- User interaction metrics
- Session duration and activity
"""

from prometheus_client import Counter, Gauge, Histogram

from .base import BaseMetricsRecorder


class FrontendMetricsRecorder(BaseMetricsRecorder):
    """Recorder for frontend Real User Monitoring (RUM) metrics."""

    def _init_metrics(self) -> None:
        """
        Initialize frontend metrics.

        Issue #665: Refactored to use helper methods per category to reduce
        function length from 191 lines to under 50 lines.
        """
        self._init_page_performance_metrics()
        self._init_api_call_metrics()
        self._init_javascript_error_metrics()
        self._init_user_interaction_metrics()
        self._init_session_metrics()
        self._init_websocket_metrics()
        self._init_resource_timing_metrics()
        self._init_critical_issues_metrics()

    def _init_page_performance_metrics(self) -> None:
        """
        Initialize page performance metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.page_load_seconds = Histogram(
            "autobot_frontend_page_load_seconds",
            "Page load time in seconds",
            ["page"],
            buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 15.0, 30.0],
            registry=self.registry,
        )

        self.first_contentful_paint_seconds = Histogram(
            "autobot_frontend_first_contentful_paint_seconds",
            "First Contentful Paint (FCP) time in seconds",
            ["page"],
            buckets=[0.1, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0],
            registry=self.registry,
        )

        self.largest_contentful_paint_seconds = Histogram(
            "autobot_frontend_largest_contentful_paint_seconds",
            "Largest Contentful Paint (LCP) time in seconds",
            ["page"],
            buckets=[0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 10.0],
            registry=self.registry,
        )

        self.time_to_interactive_seconds = Histogram(
            "autobot_frontend_time_to_interactive_seconds",
            "Time to Interactive (TTI) in seconds",
            ["page"],
            buckets=[0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 7.5, 10.0, 15.0],
            registry=self.registry,
        )

        self.dom_content_loaded_seconds = Histogram(
            "autobot_frontend_dom_content_loaded_seconds",
            "DOM Content Loaded time in seconds",
            ["page"],
            buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0],
            registry=self.registry,
        )

    def _init_api_call_metrics(self) -> None:
        """
        Initialize frontend API call metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.api_requests_total = Counter(
            "autobot_frontend_api_requests_total",
            "Total frontend API requests",
            ["endpoint", "method", "status"],  # status: success, error, timeout
            registry=self.registry,
        )

        self.api_latency_seconds = Histogram(
            "autobot_frontend_api_latency_seconds",
            "Frontend API request latency in seconds",
            ["endpoint", "method"],
            buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
            registry=self.registry,
        )

        self.api_errors_total = Counter(
            "autobot_frontend_api_errors_total",
            "Total frontend API errors",
            ["endpoint", "method", "error_type"],  # error_type: network, http, timeout
            registry=self.registry,
        )

        self.api_slow_requests_total = Counter(
            "autobot_frontend_api_slow_requests_total",
            "Total slow frontend API requests (>1s)",
            ["endpoint", "method"],
            registry=self.registry,
        )

        self.api_timeout_requests_total = Counter(
            "autobot_frontend_api_timeout_requests_total",
            "Total frontend API request timeouts (>30s)",
            ["endpoint", "method"],
            registry=self.registry,
        )

    def _init_javascript_error_metrics(self) -> None:
        """
        Initialize JavaScript error tracking metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.js_errors_total = Counter(
            "autobot_frontend_js_errors_total",
            "Total JavaScript errors",
            ["error_type", "page"],  # error_type: syntax, reference, type, etc.
            registry=self.registry,
        )

        self.unhandled_rejections_total = Counter(
            "autobot_frontend_unhandled_rejections_total",
            "Total unhandled Promise rejections",
            ["page"],
            registry=self.registry,
        )

        self.errors_by_component_total = Counter(
            "autobot_frontend_errors_by_component_total",
            "Total errors by Vue component",
            ["component", "error_type"],
            registry=self.registry,
        )

    def _init_user_interaction_metrics(self) -> None:
        """
        Initialize user interaction metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.user_actions_total = Counter(
            "autobot_frontend_user_actions_total",
            "Total user actions/interactions",
            ["action_type", "page"],  # action_type: click, submit, navigation, etc.
            registry=self.registry,
        )

        self.form_submissions_total = Counter(
            "autobot_frontend_form_submissions_total",
            "Total form submissions",
            ["form_name", "status"],  # status: success, validation_error, server_error
            registry=self.registry,
        )

    def _init_session_metrics(self) -> None:
        """
        Initialize session tracking metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.session_duration_seconds = Histogram(
            "autobot_frontend_session_duration_seconds",
            "User session duration in seconds",
            buckets=[60, 300, 600, 1800, 3600, 7200, 14400, 28800],  # 1m to 8h
            registry=self.registry,
        )

        self.active_sessions = Gauge(
            "autobot_frontend_active_sessions",
            "Current number of active frontend sessions",
            registry=self.registry,
        )

        self.sessions_total = Counter(
            "autobot_frontend_sessions_total",
            "Total frontend sessions started",
            registry=self.registry,
        )

    def _init_websocket_metrics(self) -> None:
        """
        Initialize WebSocket metrics from frontend perspective.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.ws_connection_events_total = Counter(
            "autobot_frontend_ws_connection_events_total",
            "WebSocket connection events from frontend",
            ["event"],  # event: connect, disconnect, error, reconnect
            registry=self.registry,
        )

        self.ws_messages_total = Counter(
            "autobot_frontend_ws_messages_total",
            "WebSocket messages from frontend",
            ["direction", "event_type"],  # direction: sent, received
            registry=self.registry,
        )

    def _init_resource_timing_metrics(self) -> None:
        """
        Initialize resource timing metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.slow_resources_total = Counter(
            "autobot_frontend_slow_resources_total",
            "Total slow resource loads (>1s)",
            ["resource_type"],  # resource_type: script, stylesheet, image, font
            registry=self.registry,
        )

        self.resource_load_seconds = Histogram(
            "autobot_frontend_resource_load_seconds",
            "Resource load time in seconds",
            ["resource_type"],
            buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
            registry=self.registry,
        )

    def _init_critical_issues_metrics(self) -> None:
        """
        Initialize critical issues metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.critical_issues_total = Counter(
            "autobot_frontend_critical_issues_total",
            "Total critical issues reported from frontend",
            ["issue_type"],  # issue_type: api_timeout, error, crash
            registry=self.registry,
        )

    # =========================================================================
    # Page Performance Methods
    # =========================================================================

    def record_page_load(self, page: str, load_time_seconds: float) -> None:
        """Record page load time."""
        self.page_load_seconds.labels(page=page).observe(load_time_seconds)

    def record_first_contentful_paint(self, page: str, fcp_seconds: float) -> None:
        """Record First Contentful Paint time."""
        self.first_contentful_paint_seconds.labels(page=page).observe(fcp_seconds)

    def record_largest_contentful_paint(self, page: str, lcp_seconds: float) -> None:
        """Record Largest Contentful Paint time."""
        self.largest_contentful_paint_seconds.labels(page=page).observe(lcp_seconds)

    def record_time_to_interactive(self, page: str, tti_seconds: float) -> None:
        """Record Time to Interactive."""
        self.time_to_interactive_seconds.labels(page=page).observe(tti_seconds)

    def record_dom_content_loaded(self, page: str, dcl_seconds: float) -> None:
        """Record DOM Content Loaded time."""
        self.dom_content_loaded_seconds.labels(page=page).observe(dcl_seconds)

    # =========================================================================
    # API Call Methods
    # =========================================================================

    def record_api_request(
        self,
        endpoint: str,
        method: str,
        status: str,
        latency_seconds: float,
        is_slow: bool = False,
        is_timeout: bool = False,
    ) -> None:
        """Record a frontend API request."""
        # Normalize endpoint to prevent high cardinality
        normalized_endpoint = self._normalize_endpoint(endpoint)

        self.api_requests_total.labels(
            endpoint=normalized_endpoint, method=method, status=status
        ).inc()
        self.api_latency_seconds.labels(
            endpoint=normalized_endpoint, method=method
        ).observe(latency_seconds)

        if is_slow:
            self.api_slow_requests_total.labels(
                endpoint=normalized_endpoint, method=method
            ).inc()

        if is_timeout:
            self.api_timeout_requests_total.labels(
                endpoint=normalized_endpoint, method=method
            ).inc()

    def record_api_error(
        self, endpoint: str, method: str, error_type: str
    ) -> None:
        """Record a frontend API error."""
        normalized_endpoint = self._normalize_endpoint(endpoint)
        self.api_errors_total.labels(
            endpoint=normalized_endpoint, method=method, error_type=error_type
        ).inc()

    def _normalize_endpoint(self, endpoint: str) -> str:
        """Normalize endpoint to prevent high cardinality from dynamic IDs."""
        # Remove query parameters
        if "?" in endpoint:
            endpoint = endpoint.split("?")[0]

        # Replace numeric IDs with placeholder
        import re

        endpoint = re.sub(r"/\d+", "/{id}", endpoint)

        # Replace UUIDs with placeholder
        endpoint = re.sub(
            r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "/{uuid}",
            endpoint,
            flags=re.IGNORECASE,
        )

        return endpoint

    # =========================================================================
    # JavaScript Error Methods
    # =========================================================================

    def record_js_error(self, error_type: str, page: str) -> None:
        """Record a JavaScript error."""
        self.js_errors_total.labels(error_type=error_type, page=page).inc()

    def record_unhandled_rejection(self, page: str) -> None:
        """Record an unhandled Promise rejection."""
        self.unhandled_rejections_total.labels(page=page).inc()

    def record_component_error(self, component: str, error_type: str) -> None:
        """Record a Vue component error."""
        self.errors_by_component_total.labels(
            component=component, error_type=error_type
        ).inc()

    # =========================================================================
    # User Interaction Methods
    # =========================================================================

    def record_user_action(self, action_type: str, page: str) -> None:
        """Record a user action/interaction."""
        self.user_actions_total.labels(action_type=action_type, page=page).inc()

    def record_form_submission(self, form_name: str, status: str) -> None:
        """Record a form submission."""
        self.form_submissions_total.labels(form_name=form_name, status=status).inc()

    # =========================================================================
    # Session Methods
    # =========================================================================

    def record_session_duration(self, duration_seconds: float) -> None:
        """Record session duration."""
        self.session_duration_seconds.observe(duration_seconds)

    def set_active_sessions(self, count: int) -> None:
        """Set active session count."""
        self.active_sessions.set(count)

    def record_session_start(self) -> None:
        """Record a new session starting."""
        self.sessions_total.inc()

    # =========================================================================
    # WebSocket Methods
    # =========================================================================

    def record_ws_connection_event(self, event: str) -> None:
        """Record a WebSocket connection event."""
        self.ws_connection_events_total.labels(event=event).inc()

    def record_ws_message(self, direction: str, event_type: str) -> None:
        """Record a WebSocket message."""
        self.ws_messages_total.labels(
            direction=direction, event_type=event_type
        ).inc()

    # =========================================================================
    # Resource Timing Methods
    # =========================================================================

    def record_slow_resource(self, resource_type: str) -> None:
        """Record a slow resource load."""
        self.slow_resources_total.labels(resource_type=resource_type).inc()

    def record_resource_load(self, resource_type: str, load_time_seconds: float) -> None:
        """Record resource load time."""
        self.resource_load_seconds.labels(resource_type=resource_type).observe(
            load_time_seconds
        )

    # =========================================================================
    # Critical Issue Methods
    # =========================================================================

    def record_critical_issue(self, issue_type: str) -> None:
        """Record a critical issue from frontend."""
        self.critical_issues_total.labels(issue_type=issue_type).inc()


__all__ = ["FrontendMetricsRecorder"]
