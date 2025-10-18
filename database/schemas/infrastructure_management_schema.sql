-- Infrastructure Management Platform Schema
-- Manages hosts, SSH keys, deployments, services, and health monitoring
-- Database: data/infrastructure_management.db (SQLite)
-- Created: 2025-10-11

-- ============================================================================
-- CRITICAL: Enable Foreign Keys Globally
-- ============================================================================
-- Must be set BEFORE any table creation to ensure referential integrity
PRAGMA foreign_keys = ON;

-- ============================================================================
-- CORE TABLES
-- ============================================================================

-- ssh_keys: SSH key management for host authentication
CREATE TABLE IF NOT EXISTS ssh_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,                     -- e.g., "autobot_frontend_key"
    public_key TEXT NOT NULL,                      -- SSH public key content
    private_key_path TEXT NOT NULL,                -- Path to private key file
    fingerprint TEXT NOT NULL UNIQUE,              -- SSH key fingerprint (SHA256)
    key_type TEXT DEFAULT 'rsa',                   -- Key type: rsa, ed25519, ecdsa
    key_bits INTEGER DEFAULT 4096,                 -- Key size in bits
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP NULL,                   -- Last time key was used for connection
    is_active INTEGER DEFAULT 1,                   -- Active status (0=inactive, 1=active)

    -- Constraints
    CHECK (is_active IN (0, 1)),
    CHECK (key_type IN ('rsa', 'ed25519', 'ecdsa', 'dsa')),
    CHECK (key_bits > 0)
);

-- hosts: Infrastructure host/VM management
CREATE TABLE IF NOT EXISTS hosts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,                     -- Unique label (e.g., "frontend-vm", "redis-server")
    ip_address TEXT NOT NULL UNIQUE,               -- IP address (e.g., "172.16.168.21")
    ssh_port INTEGER DEFAULT 22,                   -- SSH port
    role TEXT NOT NULL,                            -- Role: frontend, redis, npu_worker, ai_stack, browser
    status TEXT DEFAULT 'new',                     -- Status: new, provisioning, deployed, healthy, unhealthy, failed
    ssh_key_id INTEGER NOT NULL,                   -- Foreign key to ssh_keys
    ssh_username TEXT DEFAULT 'autobot',           -- SSH username for connection
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_health_check TIMESTAMP NULL,              -- Last successful health check
    metadata TEXT DEFAULT '{}',                    -- JSON: specs, notes, custom fields

    -- Constraints
    FOREIGN KEY (ssh_key_id) REFERENCES ssh_keys(id) ON DELETE RESTRICT,
    CHECK (status IN ('new', 'provisioning', 'deployed', 'healthy', 'unhealthy', 'failed', 'maintenance', 'decommissioned')),
    CHECK (role IN ('frontend', 'redis', 'npu_worker', 'ai_stack', 'browser', 'backend', 'monitoring')),
    CHECK (ssh_port > 0 AND ssh_port <= 65535),
    CHECK (json_valid(metadata))
);

-- deployments: Deployment and operation audit trail
CREATE TABLE IF NOT EXISTS deployments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    host_id INTEGER NOT NULL,                      -- Foreign key to hosts
    action TEXT NOT NULL,                          -- Action: provision, deploy, redeploy, recover, update, restart
    status TEXT DEFAULT 'running',                 -- Status: running, success, failed, cancelled
    playbook_name TEXT,                            -- Ansible playbook name (e.g., "deploy_frontend.yml")
    playbook_version TEXT,                         -- Playbook version/commit hash
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL,                   -- Completion timestamp
    duration_seconds INTEGER,                      -- Execution duration in seconds
    output_log_path TEXT,                          -- Path to detailed log file
    output_summary TEXT,                           -- Brief summary or first 1000 chars of output
    initiated_by TEXT DEFAULT 'system',            -- User or system identifier
    metadata TEXT DEFAULT '{}',                    -- JSON: additional context (variables, tags, etc.)
    error_message TEXT,                            -- Error details if failed
    retry_count INTEGER DEFAULT 0,                 -- Number of retry attempts
    parent_deployment_id INTEGER,                  -- For linked/dependent deployments

    -- Constraints
    FOREIGN KEY (host_id) REFERENCES hosts(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_deployment_id) REFERENCES deployments(id) ON DELETE SET NULL,
    CHECK (action IN ('provision', 'deploy', 'redeploy', 'recover', 'update', 'restart', 'configure', 'backup', 'restore')),
    CHECK (status IN ('pending', 'running', 'success', 'failed', 'cancelled', 'timeout')),
    CHECK (duration_seconds IS NULL OR duration_seconds >= 0),
    CHECK (retry_count >= 0),
    CHECK (json_valid(metadata))
);

-- services: Service tracking per host
CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    host_id INTEGER NOT NULL,                      -- Foreign key to hosts
    service_name TEXT NOT NULL,                    -- Service name (e.g., "redis-stack-server", "nginx")
    service_type TEXT DEFAULT 'systemd',           -- Service type: systemd, docker, manual, supervisor
    status TEXT DEFAULT 'unknown',                 -- Status: running, stopped, failed, unknown, starting, stopping
    port INTEGER,                                  -- Primary service port
    additional_ports TEXT,                         -- JSON array of additional ports
    auto_restart INTEGER DEFAULT 1,                -- Auto-restart enabled (0=no, 1=yes)
    restart_policy TEXT DEFAULT 'on-failure',      -- Restart policy: always, on-failure, unless-stopped, no
    health_check_endpoint TEXT,                    -- HTTP endpoint for health checks (e.g., "/health")
    health_check_interval INTEGER DEFAULT 60,      -- Health check interval in seconds
    last_check TIMESTAMP NULL,                     -- Last health check timestamp
    last_status_change TIMESTAMP NULL,             -- Last time status changed
    process_id INTEGER,                            -- Current process ID (if available)
    uptime_seconds INTEGER,                        -- Service uptime in seconds
    version TEXT,                                  -- Service/application version
    config_path TEXT,                              -- Path to configuration file
    metadata TEXT DEFAULT '{}',                    -- JSON: custom service metadata

    -- Constraints
    FOREIGN KEY (host_id) REFERENCES hosts(id) ON DELETE CASCADE,
    CHECK (status IN ('running', 'stopped', 'failed', 'unknown', 'starting', 'stopping', 'degraded')),
    CHECK (service_type IN ('systemd', 'docker', 'manual', 'supervisor', 'kubernetes')),
    CHECK (auto_restart IN (0, 1)),
    CHECK (restart_policy IN ('always', 'on-failure', 'unless-stopped', 'no')),
    CHECK (port IS NULL OR (port > 0 AND port <= 65535)),
    CHECK (health_check_interval > 0),
    CHECK (uptime_seconds IS NULL OR uptime_seconds >= 0),
    CHECK (json_valid(metadata)),
    CHECK (json_valid(additional_ports) OR additional_ports IS NULL),
    UNIQUE (host_id, service_name)                 -- Unique service per host
);

-- host_health: Time-series health metrics tracking
CREATE TABLE IF NOT EXISTS host_health (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    host_id INTEGER NOT NULL,                      -- Foreign key to hosts
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Metric collection timestamp
    cpu_usage REAL,                                -- CPU usage percentage (0-100)
    memory_usage REAL,                             -- Memory usage percentage (0-100)
    memory_total_mb INTEGER,                       -- Total memory in MB
    memory_used_mb INTEGER,                        -- Used memory in MB
    disk_usage REAL,                               -- Disk usage percentage (0-100)
    disk_total_gb INTEGER,                         -- Total disk space in GB
    disk_used_gb INTEGER,                          -- Used disk space in GB
    network_latency_ms REAL,                       -- Network latency in milliseconds
    network_rx_mbps REAL,                          -- Network receive speed in Mbps
    network_tx_mbps REAL,                          -- Network transmit speed in Mbps
    load_average_1m REAL,                          -- 1-minute load average
    load_average_5m REAL,                          -- 5-minute load average
    load_average_15m REAL,                         -- 15-minute load average
    service_count_healthy INTEGER DEFAULT 0,       -- Number of healthy services
    service_count_total INTEGER DEFAULT 0,         -- Total number of services
    temperature_celsius REAL,                      -- CPU/system temperature (if available)
    uptime_seconds INTEGER,                        -- System uptime in seconds
    is_reachable INTEGER DEFAULT 1,                -- Host reachability (0=unreachable, 1=reachable)

    -- Constraints
    FOREIGN KEY (host_id) REFERENCES hosts(id) ON DELETE CASCADE,
    CHECK (cpu_usage IS NULL OR (cpu_usage >= 0 AND cpu_usage <= 100)),
    CHECK (memory_usage IS NULL OR (memory_usage >= 0 AND memory_usage <= 100)),
    CHECK (disk_usage IS NULL OR (disk_usage >= 0 AND disk_usage <= 100)),
    CHECK (network_latency_ms IS NULL OR network_latency_ms >= 0),
    CHECK (service_count_healthy >= 0),
    CHECK (service_count_total >= 0),
    CHECK (service_count_healthy <= service_count_total),
    CHECK (is_reachable IN (0, 1)),
    CHECK (uptime_seconds IS NULL OR uptime_seconds >= 0)
);

-- deployment_logs: Detailed deployment execution logs
CREATE TABLE IF NOT EXISTS deployment_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deployment_id INTEGER NOT NULL,                -- Foreign key to deployments
    log_level TEXT DEFAULT 'info',                 -- Log level: debug, info, warning, error, critical
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    message TEXT NOT NULL,                         -- Log message content
    task_name TEXT,                                -- Ansible task name (if applicable)
    module_name TEXT,                              -- Ansible module name (if applicable)

    -- Constraints
    FOREIGN KEY (deployment_id) REFERENCES deployments(id) ON DELETE CASCADE,
    CHECK (log_level IN ('debug', 'info', 'warning', 'error', 'critical'))
);

-- service_dependencies: Service dependency mapping
CREATE TABLE IF NOT EXISTS service_dependencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id INTEGER NOT NULL,                   -- Foreign key to services (dependent service)
    depends_on_service_id INTEGER NOT NULL,        -- Foreign key to services (dependency)
    dependency_type TEXT DEFAULT 'required',       -- Type: required, optional, recommended
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE,
    FOREIGN KEY (depends_on_service_id) REFERENCES services(id) ON DELETE CASCADE,
    CHECK (dependency_type IN ('required', 'optional', 'recommended')),
    CHECK (service_id != depends_on_service_id),   -- Prevent self-dependency
    UNIQUE (service_id, depends_on_service_id)     -- Prevent duplicate dependencies
);

-- alerts: Infrastructure monitoring alerts and notifications
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_type TEXT NOT NULL,                      -- Type: host_down, service_failed, high_cpu, high_memory, disk_full
    severity TEXT DEFAULT 'warning',               -- Severity: info, warning, error, critical
    host_id INTEGER,                               -- Foreign key to hosts (optional)
    service_id INTEGER,                            -- Foreign key to services (optional)
    title TEXT NOT NULL,                           -- Alert title
    description TEXT,                              -- Detailed alert description
    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP NULL,                    -- Resolution timestamp
    resolved_by TEXT,                              -- User who resolved the alert
    status TEXT DEFAULT 'active',                  -- Status: active, acknowledged, resolved, ignored
    notification_sent INTEGER DEFAULT 0,           -- Notification sent flag (0=no, 1=yes)
    metadata TEXT DEFAULT '{}',                    -- JSON: additional context

    -- Constraints
    FOREIGN KEY (host_id) REFERENCES hosts(id) ON DELETE CASCADE,
    FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE,
    CHECK (alert_type IN ('host_down', 'host_unreachable', 'service_failed', 'high_cpu', 'high_memory', 'disk_full', 'deployment_failed', 'custom')),
    CHECK (severity IN ('info', 'warning', 'error', 'critical')),
    CHECK (status IN ('active', 'acknowledged', 'resolved', 'ignored', 'auto_resolved')),
    CHECK (notification_sent IN (0, 1)),
    CHECK (json_valid(metadata))
);

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

-- SSH Keys indexes
CREATE INDEX IF NOT EXISTS idx_ssh_keys_active
    ON ssh_keys(is_active, last_used_at DESC);

-- Hosts indexes
CREATE INDEX IF NOT EXISTS idx_hosts_role_status
    ON hosts(role, status);

CREATE INDEX IF NOT EXISTS idx_hosts_ip_address
    ON hosts(ip_address);

CREATE INDEX IF NOT EXISTS idx_hosts_last_health_check
    ON hosts(last_health_check DESC);

CREATE INDEX IF NOT EXISTS idx_hosts_ssh_key
    ON hosts(ssh_key_id);

-- Deployments indexes
CREATE INDEX IF NOT EXISTS idx_deployments_host_status
    ON deployments(host_id, status, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_deployments_action
    ON deployments(action, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_deployments_status
    ON deployments(status, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_deployments_initiated_by
    ON deployments(initiated_by, started_at DESC);

-- Services indexes
CREATE INDEX IF NOT EXISTS idx_services_host
    ON services(host_id, status);

CREATE INDEX IF NOT EXISTS idx_services_status
    ON services(status, last_check DESC);

CREATE INDEX IF NOT EXISTS idx_services_health_check
    ON services(last_check DESC);

-- Host Health indexes (critical for time-series queries)
CREATE INDEX IF NOT EXISTS idx_host_health_host_timestamp
    ON host_health(host_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_host_health_timestamp
    ON host_health(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_host_health_reachability
    ON host_health(is_reachable, timestamp DESC);

-- Deployment Logs indexes
CREATE INDEX IF NOT EXISTS idx_deployment_logs_deployment
    ON deployment_logs(deployment_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_deployment_logs_level
    ON deployment_logs(log_level, timestamp DESC);

-- Service Dependencies indexes
CREATE INDEX IF NOT EXISTS idx_service_dependencies_service
    ON service_dependencies(service_id);

CREATE INDEX IF NOT EXISTS idx_service_dependencies_depends_on
    ON service_dependencies(depends_on_service_id);

-- Alerts indexes
CREATE INDEX IF NOT EXISTS idx_alerts_status_severity
    ON alerts(status, severity, triggered_at DESC);

CREATE INDEX IF NOT EXISTS idx_alerts_host
    ON alerts(host_id, status, triggered_at DESC);

CREATE INDEX IF NOT EXISTS idx_alerts_service
    ON alerts(service_id, status, triggered_at DESC);

CREATE INDEX IF NOT EXISTS idx_alerts_type
    ON alerts(alert_type, triggered_at DESC);

-- ============================================================================
-- TRIGGERS FOR AUTOMATION
-- ============================================================================

-- Trigger: Auto-update hosts.updated_at on any change
CREATE TRIGGER IF NOT EXISTS trg_hosts_updated_at
AFTER UPDATE ON hosts
WHEN OLD.updated_at = NEW.updated_at  -- Only if not manually set
BEGIN
    UPDATE hosts
    SET updated_at = CURRENT_TIMESTAMP
    WHERE id = NEW.id;
END;

-- Trigger: Auto-calculate deployment duration on completion
CREATE TRIGGER IF NOT EXISTS trg_deployments_calculate_duration
AFTER UPDATE OF completed_at ON deployments
WHEN NEW.completed_at IS NOT NULL AND OLD.completed_at IS NULL
BEGIN
    UPDATE deployments
    SET duration_seconds = CAST((julianday(NEW.completed_at) - julianday(NEW.started_at)) * 86400 AS INTEGER)
    WHERE id = NEW.id;
END;

-- Trigger: Update ssh_keys.last_used_at when used in deployment
CREATE TRIGGER IF NOT EXISTS trg_deployments_update_key_usage
AFTER INSERT ON deployments
BEGIN
    UPDATE ssh_keys
    SET last_used_at = CURRENT_TIMESTAMP
    WHERE id = (SELECT ssh_key_id FROM hosts WHERE id = NEW.host_id);
END;

-- Trigger: Auto-update service.last_status_change when status changes
CREATE TRIGGER IF NOT EXISTS trg_services_status_change
AFTER UPDATE OF status ON services
WHEN OLD.status != NEW.status
BEGIN
    UPDATE services
    SET last_status_change = CURRENT_TIMESTAMP
    WHERE id = NEW.id;
END;

-- Trigger: Create alert when deployment fails
CREATE TRIGGER IF NOT EXISTS trg_deployments_failed_alert
AFTER UPDATE OF status ON deployments
WHEN NEW.status = 'failed' AND OLD.status != 'failed'
BEGIN
    INSERT INTO alerts (alert_type, severity, host_id, title, description, metadata)
    SELECT
        'deployment_failed',
        'error',
        NEW.host_id,
        'Deployment Failed: ' || NEW.action,
        NEW.error_message,
        json_object('deployment_id', NEW.id, 'playbook_name', NEW.playbook_name)
    WHERE NEW.error_message IS NOT NULL;
END;

-- Trigger: Auto-resolve alert when host becomes healthy
CREATE TRIGGER IF NOT EXISTS trg_hosts_auto_resolve_alerts
AFTER UPDATE OF status ON hosts
WHEN NEW.status = 'healthy' AND OLD.status IN ('unhealthy', 'failed')
BEGIN
    UPDATE alerts
    SET status = 'auto_resolved',
        resolved_at = CURRENT_TIMESTAMP,
        resolved_by = 'system'
    WHERE host_id = NEW.id
      AND status = 'active'
      AND alert_type IN ('host_down', 'host_unreachable');
END;

-- ============================================================================
-- VIEWS FOR DASHBOARD AND ANALYTICS
-- ============================================================================

-- View: Current host status overview
CREATE VIEW IF NOT EXISTS v_host_status_overview AS
SELECT
    h.id,
    h.name,
    h.ip_address,
    h.role,
    h.status,
    h.last_health_check,
    sk.name as ssh_key_name,
    COUNT(DISTINCT s.id) as total_services,
    SUM(CASE WHEN s.status = 'running' THEN 1 ELSE 0 END) as running_services,
    MAX(hh.timestamp) as last_health_metric,
    hh.cpu_usage,
    hh.memory_usage,
    hh.disk_usage,
    hh.is_reachable
FROM hosts h
LEFT JOIN ssh_keys sk ON h.ssh_key_id = sk.id
LEFT JOIN services s ON h.id = s.host_id
LEFT JOIN host_health hh ON h.id = hh.host_id
    AND hh.timestamp = (SELECT MAX(timestamp) FROM host_health WHERE host_id = h.id)
GROUP BY h.id;

-- View: Recent deployments with host information
CREATE VIEW IF NOT EXISTS v_recent_deployments AS
SELECT
    d.id,
    d.action,
    d.status,
    d.playbook_name,
    d.started_at,
    d.completed_at,
    d.duration_seconds,
    d.initiated_by,
    h.name as host_name,
    h.ip_address as host_ip,
    h.role as host_role,
    d.error_message
FROM deployments d
JOIN hosts h ON d.host_id = h.id
ORDER BY d.started_at DESC;

-- View: Service health summary per host
CREATE VIEW IF NOT EXISTS v_service_health_summary AS
SELECT
    h.id as host_id,
    h.name as host_name,
    h.role as host_role,
    COUNT(s.id) as total_services,
    SUM(CASE WHEN s.status = 'running' THEN 1 ELSE 0 END) as running_services,
    SUM(CASE WHEN s.status = 'stopped' THEN 1 ELSE 0 END) as stopped_services,
    SUM(CASE WHEN s.status = 'failed' THEN 1 ELSE 0 END) as failed_services,
    SUM(CASE WHEN s.status = 'unknown' THEN 1 ELSE 0 END) as unknown_services,
    MAX(s.last_check) as last_service_check
FROM hosts h
LEFT JOIN services s ON h.id = s.host_id
GROUP BY h.id;

-- View: Active alerts by severity
CREATE VIEW IF NOT EXISTS v_active_alerts AS
SELECT
    a.id,
    a.alert_type,
    a.severity,
    a.title,
    a.description,
    a.triggered_at,
    a.status,
    h.name as host_name,
    h.ip_address as host_ip,
    s.service_name,
    CAST((julianday('now') - julianday(a.triggered_at)) * 24 AS INTEGER) as hours_active
FROM alerts a
LEFT JOIN hosts h ON a.host_id = h.id
LEFT JOIN services s ON a.service_id = s.id
WHERE a.status IN ('active', 'acknowledged')
ORDER BY
    CASE a.severity
        WHEN 'critical' THEN 1
        WHEN 'error' THEN 2
        WHEN 'warning' THEN 3
        ELSE 4
    END,
    a.triggered_at DESC;

-- View: Host health trends (last 24 hours average)
CREATE VIEW IF NOT EXISTS v_host_health_24h AS
SELECT
    h.id as host_id,
    h.name as host_name,
    h.role as host_role,
    COUNT(hh.id) as metric_count,
    AVG(hh.cpu_usage) as avg_cpu_usage,
    MAX(hh.cpu_usage) as max_cpu_usage,
    AVG(hh.memory_usage) as avg_memory_usage,
    MAX(hh.memory_usage) as max_memory_usage,
    AVG(hh.disk_usage) as avg_disk_usage,
    AVG(hh.network_latency_ms) as avg_network_latency,
    MIN(hh.timestamp) as period_start,
    MAX(hh.timestamp) as period_end
FROM hosts h
LEFT JOIN host_health hh ON h.id = hh.host_id
WHERE hh.timestamp >= datetime('now', '-24 hours')
GROUP BY h.id;

-- View: Deployment success rate by host
CREATE VIEW IF NOT EXISTS v_deployment_success_rate AS
SELECT
    h.id as host_id,
    h.name as host_name,
    h.role as host_role,
    COUNT(d.id) as total_deployments,
    SUM(CASE WHEN d.status = 'success' THEN 1 ELSE 0 END) as successful_deployments,
    SUM(CASE WHEN d.status = 'failed' THEN 1 ELSE 0 END) as failed_deployments,
    ROUND(100.0 * SUM(CASE WHEN d.status = 'success' THEN 1 ELSE 0 END) / COUNT(d.id), 2) as success_rate,
    AVG(d.duration_seconds) as avg_deployment_time,
    MAX(d.started_at) as last_deployment
FROM hosts h
LEFT JOIN deployments d ON h.id = d.host_id
WHERE d.started_at >= datetime('now', '-30 days')
GROUP BY h.id
HAVING COUNT(d.id) > 0;

-- View: Service dependencies with status
CREATE VIEW IF NOT EXISTS v_service_dependencies_status AS
SELECT
    s1.id as service_id,
    s1.service_name,
    s1.status as service_status,
    h1.name as host_name,
    sd.dependency_type,
    s2.id as depends_on_service_id,
    s2.service_name as depends_on_service_name,
    s2.status as depends_on_status,
    h2.name as depends_on_host_name
FROM service_dependencies sd
JOIN services s1 ON sd.service_id = s1.id
JOIN services s2 ON sd.depends_on_service_id = s2.id
JOIN hosts h1 ON s1.host_id = h1.id
JOIN hosts h2 ON s2.host_id = h2.id;

-- ============================================================================
-- SAMPLE QUERIES (Commented as examples)
-- ============================================================================

-- Get all unhealthy hosts with latest metrics:
-- SELECT * FROM v_host_status_overview
-- WHERE status IN ('unhealthy', 'failed') OR is_reachable = 0;

-- Get deployment history for specific host:
-- SELECT * FROM v_recent_deployments
-- WHERE host_name = 'frontend-vm'
-- ORDER BY started_at DESC LIMIT 10;

-- Get services with dependencies that are down:
-- SELECT * FROM v_service_dependencies_status
-- WHERE dependency_type = 'required' AND depends_on_status != 'running';

-- Get average CPU usage per host (last hour):
-- SELECT host_id, AVG(cpu_usage) as avg_cpu
-- FROM host_health
-- WHERE timestamp >= datetime('now', '-1 hour')
-- GROUP BY host_id
-- ORDER BY avg_cpu DESC;

-- Get critical alerts that need attention:
-- SELECT * FROM v_active_alerts
-- WHERE severity IN ('critical', 'error')
-- ORDER BY triggered_at DESC;

-- Find hosts with disk usage > 80%:
-- SELECT h.name, h.ip_address, hh.disk_usage, hh.timestamp
-- FROM hosts h
-- JOIN host_health hh ON h.id = hh.host_id
-- WHERE hh.disk_usage > 80
--   AND hh.timestamp = (SELECT MAX(timestamp) FROM host_health WHERE host_id = h.id);

-- Get deployment success rate per playbook:
-- SELECT
--     playbook_name,
--     COUNT(*) as total_runs,
--     SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successes,
--     ROUND(100.0 * SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate
-- FROM deployments
-- WHERE started_at >= datetime('now', '-30 days')
-- GROUP BY playbook_name
-- ORDER BY total_runs DESC;
