#!/bin/bash

# AutoBot Enhanced Centralized Logging Deployment Script
# Deploys comprehensive centralized logging with Loki, Promtail, and enhanced monitoring
# Building upon existing rsyslog infrastructure

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/ssot-config.sh" 2>/dev/null || true
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
LOGS_DIR="$PROJECT_ROOT/logs"
CENTRALIZED_DIR="$LOGS_DIR/autobot-centralized"
CONFIG_DIR="$PROJECT_ROOT/config/logging"
SSH_KEY="${AUTOBOT_SSH_KEY:-$HOME/.ssh/autobot_key}"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# VM Configuration
declare -A VMS=(
    ["vm1-frontend"]="${AUTOBOT_FRONTEND_HOST:-172.16.168.21}"
    ["vm2-npu-worker"]="${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}"
    ["vm3-redis"]="${AUTOBOT_REDIS_HOST:-172.16.168.23}"
    ["vm4-ai-stack"]="${AUTOBOT_AI_STACK_HOST:-172.16.168.24}"
    ["vm5-browser"]="${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}"
)

# Service-specific log paths for each VM
declare -A VM_SERVICES=(
    ["vm1-frontend"]="nginx autobot-frontend"
    ["vm2-npu-worker"]="autobot-npu-worker docker"
    ["vm3-redis"]="redis-stack-server autobot-redis"
    ["vm4-ai-stack"]="autobot-ai-stack autobot-backend"
    ["vm5-browser"]="autobot-playwright docker"
)

log_info() {
    echo -e "${CYAN}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${PURPLE}[STEP]${NC} $1"
}

check_prerequisites() {
    log_step "Checking prerequisites for enhanced logging deployment..."

    # Check SSH key
    if [[ ! -f "$SSH_KEY" ]]; then
        log_error "SSH key not found at $SSH_KEY"
        log_info "Run: ./scripts/utilities/setup-ssh-keys.sh"
        exit 1
    fi

    # Check docker is available for Loki deployment
    if ! command -v docker &> /dev/null; then
        log_error "Docker is required for Loki deployment"
        exit 1
    fi

    # Check SSH connectivity to all VMs
    log_info "Testing SSH connectivity to all VMs..."
    local failed_vms=()
    for vm_name in "${!VMS[@]}"; do
        vm_ip="${VMS[$vm_name]}"
        if ! ssh -i "$SSH_KEY" -o ConnectTimeout=5 -o BatchMode=yes "${AUTOBOT_SSH_USER:-autobot}"@"$vm_ip" "echo 'test'" &>/dev/null; then
            log_warning "Cannot connect to $vm_name ($vm_ip)"
            failed_vms+=("$vm_name")
        fi
    done

    if [[ ${#failed_vms[@]} -gt 0 ]]; then
        log_error "Failed to connect to VMs: ${failed_vms[*]}"
        log_info "Check VM status with: ./scripts/vm-management/status-all-vms.sh"
        exit 1
    fi

    log_success "All prerequisites met"
}

create_enhanced_directory_structure() {
    log_step "Creating enhanced logging directory structure..."

    # Create configuration directory
    mkdir -p "$CONFIG_DIR"/{loki,promtail,grafana,alerting}

    # Create enhanced centralized structure (extends existing)
    mkdir -p "$CENTRALIZED_DIR"/{aggregated,alerts,metrics,buffer}
    mkdir -p "$CENTRALIZED_DIR/aggregated"/{by-service,by-severity,by-time}
    mkdir -p "$CENTRALIZED_DIR/alerts"/{critical,warning,performance}
    mkdir -p "$CENTRALIZED_DIR/metrics"/{performance,system,application}

    # Create VM-specific enhanced directories
    for vm_name in "${!VMS[@]}"; do
        mkdir -p "$CENTRALIZED_DIR/$vm_name"/{real-time,parsed,metrics,alerts}
    done

    # Create main machine enhanced directories
    mkdir -p "$CENTRALIZED_DIR/main-wsl"/{loki,grafana,performance,monitoring}

    log_success "Enhanced directory structure created"
}

deploy_loki_stack() {
    log_step "Deploying Loki logging stack on main machine..."

    # Create Loki configuration
    cat > "$CONFIG_DIR/loki/loki-config.yml" << 'EOF'
auth_enabled: false

server:
  http_listen_port: 3100
  grpc_listen_port: 9096

common:
  path_prefix: /tmp/loki
  storage:
    filesystem:
      chunks_directory: /tmp/loki/chunks
      rules_directory: /tmp/loki/rules
  replication_factor: 1
  ring:
    instance_addr: 127.0.0.1
    kvstore:
      store: inmemory

query_range:
  results_cache:
    cache:
      embedded_cache:
        enabled: true
        max_size_mb: 100

schema_config:
  configs:
    - from: 2020-10-24
      store: boltdb-shipper
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h

ruler:
  alertmanager_url: http://localhost:9093

# AutoBot-specific configuration
limits_config:
  enforce_metric_name: false
  reject_old_samples: true
  reject_old_samples_max_age: 168h
  max_cache_freshness_per_query: 10m
  split_queries_by_interval: 15m
EOF

    # Create Promtail configuration template
    cat > "$CONFIG_DIR/promtail/promtail-config.yml" << 'EOF'
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://${AUTOBOT_BACKEND_HOST:-172.16.168.20}:3100/loki/api/v1/push

scrape_configs:
  # AutoBot system logs
  - job_name: autobot-system
    static_configs:
      - targets:
          - localhost
        labels:
          job: autobot-system
          host: __HOST__
          __path__: /var/log/*.log

  # AutoBot application logs
  - job_name: autobot-applications
    static_configs:
      - targets:
          - localhost
        labels:
          job: autobot-applications
          host: __HOST__
          __path__: /home/autobot/logs/*.log

  # AutoBot centralized logs
  - job_name: autobot-centralized
    static_configs:
      - targets:
          - localhost
        labels:
          job: autobot-centralized
          host: __HOST__
          __path__: /home/kali/Desktop/AutoBot/logs/autobot-centralized/__HOST__/**/*.log

  # Performance monitoring logs
  - job_name: autobot-performance
    static_configs:
      - targets:
          - localhost
        labels:
          job: autobot-performance
          host: __HOST__
          __path__: /home/kali/Desktop/AutoBot/logs/performance_monitor.log

  # Docker container logs
  - job_name: autobot-docker
    docker_sd_configs:
      - host: unix:///var/run/docker.sock
        refresh_interval: 5s
    relabel_configs:
      - source_labels: ['__meta_docker_container_name']
        regex: '/(.+)'
        target_label: 'container_name'
        replacement: '${1}'
      - source_labels: ['__meta_docker_container_name']
        regex: '/autobot-.+'
        action: keep
    pipeline_stages:
      - json:
          expressions:
            output: log
            stream: stream
            time: time
      - timestamp:
          source: time
          format: RFC3339Nano
      - output:
          source: output
EOF

    # Create Loki Docker Compose
    cat > "$CONFIG_DIR/loki/docker-compose-loki.yml" << 'EOF'
version: '3.8'

services:
  loki:
    image: grafana/loki:2.9.2
    container_name: autobot-loki
    ports:
      - "3100:3100"
    volumes:
      - ./loki-config.yml:/etc/loki/local-config.yaml
      - loki-data:/tmp/loki
    command: -config.file=/etc/loki/local-config.yaml
    networks:
      - autobot-logging
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "wget --no-verbose --tries=1 --spider http://localhost:3100/ready || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3

  grafana:
    image: grafana/grafana:10.2.0
    container_name: autobot-grafana-logs
    ports:
      - "3001:3000"  # Different port to avoid conflicts
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=autobot123
      - GF_USERS_ALLOW_SIGN_UP=false
    volumes:
      - grafana-data:/var/lib/grafana
      - ./grafana-datasources.yml:/etc/grafana/provisioning/datasources/datasources.yml
      - ./grafana-dashboards.yml:/etc/grafana/provisioning/dashboards/dashboards.yml
    networks:
      - autobot-logging
    restart: unless-stopped
    depends_on:
      - loki

volumes:
  loki-data:
  grafana-data:

networks:
  autobot-logging:
    driver: bridge
EOF

    # Create Grafana datasource configuration
    cat > "$CONFIG_DIR/loki/grafana-datasources.yml" << 'EOF'
apiVersion: 1

datasources:
  - name: Loki
    type: loki
    access: proxy
    url: http://loki:3100
    isDefault: true
    jsonData:
      maxLines: 1000
EOF

    # Create Grafana dashboard provisioning
    cat > "$CONFIG_DIR/loki/grafana-dashboards.yml" << 'EOF'
apiVersion: 1

providers:
  - name: 'AutoBot Logs'
    orgId: 1
    folder: 'AutoBot'
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    allowUiUpdates: true
    options:
      path: /var/lib/grafana/dashboards
EOF

    # Deploy Loki stack
    cd "$CONFIG_DIR/loki"
    docker-compose -f docker-compose-loki.yml up -d

    log_success "Loki logging stack deployed on main machine"
    log_info "Loki available at: http://${AUTOBOT_BACKEND_HOST:-172.16.168.20}:3100"
    log_info "Grafana logs dashboard at: http://${AUTOBOT_BACKEND_HOST:-172.16.168.20}:3001 (admin/autobot123)"
}

deploy_promtail_agents() {
    log_step "Deploying Promtail agents on all VMs..."

    for vm_name in "${!VMS[@]}"; do
        vm_ip="${VMS[$vm_name]}"
        log_info "Deploying Promtail on $vm_name ($vm_ip)..."

        # Create VM-specific Promtail config
        local promtail_config=$(cat "$CONFIG_DIR/promtail/promtail-config.yml" | sed "s/__HOST__/$vm_name/g")

        # Create deployment script for VM
        cat > "/tmp/deploy-promtail-$vm_name.sh" << EOF
#!/bin/bash
set -e

# Install Promtail
wget -q https://github.com/grafana/loki/releases/download/v2.9.2/promtail-linux-amd64.zip
unzip -o promtail-linux-amd64.zip
sudo mv promtail-linux-amd64 /usr/local/bin/promtail
sudo chmod +x /usr/local/bin/promtail
rm -f promtail-linux-amd64.zip

# Create promtail user and directories
sudo useradd --system --no-create-home --shell /bin/false promtail || true
sudo mkdir -p /etc/promtail /var/lib/promtail
sudo chown promtail:promtail /var/lib/promtail

# Create promtail configuration
sudo tee /etc/promtail/config.yml > /dev/null << 'PROMTAIL_EOF'
$promtail_config
PROMTAIL_EOF

# Create systemd service
sudo tee /etc/systemd/system/promtail.service > /dev/null << 'SERVICE_EOF'
[Unit]
Description=Promtail service
After=network.target

[Service]
Type=simple
User=promtail
ExecStart=/usr/local/bin/promtail -config.file /etc/promtail/config.yml
Restart=on-failure
RestartSec=20
StandardOutput=journal
StandardError=journal
SyslogIdentifier=promtail

[Install]
WantedBy=multi-user.target
SERVICE_EOF

# Enable and start promtail
sudo systemctl daemon-reload
sudo systemctl enable promtail
sudo systemctl restart promtail
sudo systemctl status promtail --no-pager

echo "Promtail deployed successfully on $vm_name"
EOF

        # Deploy to VM
        scp -i "$SSH_KEY" "/tmp/deploy-promtail-$vm_name.sh" "${AUTOBOT_SSH_USER:-autobot}"@"$vm_ip":/tmp/
        ssh -i "$SSH_KEY" "${AUTOBOT_SSH_USER:-autobot}"@"$vm_ip" "chmod +x /tmp/deploy-promtail-$vm_name.sh && sudo /tmp/deploy-promtail-$vm_name.sh"

        rm "/tmp/deploy-promtail-$vm_name.sh"
        log_success "Promtail deployed on $vm_name"
    done
}

create_enhanced_log_aggregation() {
    log_step "Creating enhanced log aggregation and parsing..."

    # Create intelligent log parser
    cat > "$SCRIPT_DIR/enhanced-log-parser.py" << 'EOF'
#!/usr/bin/env python3
"""
AutoBot Enhanced Log Parser
Intelligent log parsing, categorization, and alerting system
"""

import re
import json
import logging
import asyncio
import aiofiles
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import argparse

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LogEntry:
    def __init__(self, timestamp: datetime, level: str, source: str, message: str, vm: str = None):
        self.timestamp = timestamp
        self.level = level
        self.source = source
        self.message = message
        self.vm = vm
        self.category = self._categorize()
        self.severity = self._assess_severity()

    def _categorize(self) -> str:
        """Categorize log entry based on content"""
        message_lower = self.message.lower()

        # Performance categories
        if any(word in message_lower for word in ['gpu', 'cpu', 'memory', 'performance', 'regression']):
            return 'performance'

        # Security categories
        if any(word in message_lower for word in ['unauthorized', 'failed login', 'security', 'attack']):
            return 'security'

        # System categories
        if any(word in message_lower for word in ['docker', 'container', 'service', 'systemd']):
            return 'system'

        # Application categories
        if any(word in message_lower for word in ['autobot', 'api', 'backend', 'frontend']):
            return 'application'

        # Network categories
        if any(word in message_lower for word in ['connection', 'timeout', 'network', 'ssh']):
            return 'network'

        return 'general'

    def _assess_severity(self) -> int:
        """Assess severity from 1-5 (5 being most critical)"""
        message_lower = self.message.lower()
        level_lower = self.level.lower()

        # Critical patterns (severity 5)
        if any(pattern in message_lower for pattern in ['fatal', 'critical', 'emergency', 'panic']):
            return 5

        # High severity (severity 4)
        if any(pattern in message_lower for pattern in ['error', 'failed', 'exception', 'crash']):
            return 4

        # Medium severity (severity 3)
        if any(pattern in message_lower for pattern in ['warning', 'warn', 'regression', 'timeout']):
            return 3

        # Low severity (severity 2)
        if level_lower in ['info', 'notice']:
            return 2

        # Very low severity (severity 1)
        return 1

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'level': self.level,
            'source': self.source,
            'message': self.message,
            'vm': self.vm,
            'category': self.category,
            'severity': self.severity
        }

class EnhancedLogParser:
    def __init__(self, centralized_dir: Path):
        self.centralized_dir = Path(centralized_dir)
        self.patterns = self._compile_patterns()
        self.alerts = []

    def _compile_patterns(self) -> Dict:
        """Compile regex patterns for different log formats"""
        return {
            'syslog': re.compile(r'(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(\w+)\s+([^:]+):\s*(.*)'),
            'autobot': re.compile(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}),\d+\s*-\s*([^-]+)\s*-\s*(\w+)\s*-\s*(.*)'),
            'nginx': re.compile(r'(\d+\.\d+\.\d+\.\d+)\s+-\s+.*\[([^\]]+)\]\s+"([^"]+)"\s+(\d+)\s+(\d+)'),
            'docker': re.compile(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.\d+Z)\s+(\w+)\s+(.*)'),
            'performance': re.compile(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}),\d+.*?(CPU:\s*([\d.]+)%|MEM:\s*([\d.]+)%|GPU:\s*([\d.]+)%)')
        }

    async def parse_log_file(self, log_file: Path, vm_name: str = None) -> List[LogEntry]:
        """Parse a single log file"""
        entries = []

        try:
            async with aiofiles.open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                async for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    entry = self._parse_line(line, log_file.name, vm_name)
                    if entry:
                        entries.append(entry)

                        # Check for alerts
                        if entry.severity >= 4:
                            await self._create_alert(entry)

        except Exception as e:
            logger.error(f"Error parsing {log_file}: {e}")

        return entries

    def _parse_line(self, line: str, source: str, vm_name: str = None) -> Optional[LogEntry]:
        """Parse a single log line"""
        # Try different patterns
        for pattern_name, pattern in self.patterns.items():
            match = pattern.match(line)
            if match:
                return self._extract_entry(match, pattern_name, source, vm_name, line)

        # Fallback for unparsed lines
        return LogEntry(
            timestamp=datetime.now(),
            level='INFO',
            source=source,
            message=line,
            vm=vm_name
        )

    def _extract_entry(self, match, pattern_name: str, source: str, vm_name: str, line: str) -> LogEntry:
        """Extract log entry from regex match"""
        try:
            if pattern_name == 'autobot':
                timestamp_str, component, level, message = match.groups()
                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                return LogEntry(timestamp, level, f"{source}:{component}", message, vm_name)

            elif pattern_name == 'syslog':
                timestamp_str, hostname, process, message = match.groups()
                # Approximate year for syslog
                current_year = datetime.now().year
                timestamp = datetime.strptime(f"{current_year} {timestamp_str}", '%Y %b %d %H:%M:%S')
                return LogEntry(timestamp, 'INFO', f"{source}:{process}", message, vm_name)

            elif pattern_name == 'performance':
                # Extract performance metrics
                timestamp_str = match.group(1)
                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                return LogEntry(timestamp, 'INFO', 'performance', line, vm_name)

            else:
                return LogEntry(datetime.now(), 'INFO', source, line, vm_name)

        except Exception as e:
            logger.warning(f"Error extracting entry: {e}")
            return LogEntry(datetime.now(), 'INFO', source, line, vm_name)

    async def _create_alert(self, entry: LogEntry):
        """Create alert for high-severity log entries"""
        alert = {
            'id': f"alert_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.alerts)}",
            'timestamp': entry.timestamp.isoformat(),
            'severity': entry.severity,
            'category': entry.category,
            'vm': entry.vm,
            'source': entry.source,
            'message': entry.message,
            'level': entry.level
        }

        self.alerts.append(alert)

        # Write alert to file
        alert_dir = self.centralized_dir / 'alerts' / ('critical' if entry.severity >= 5 else 'warning')
        alert_dir.mkdir(parents=True, exist_ok=True)

        alert_file = alert_dir / f"alert_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        async with aiofiles.open(alert_file, 'w') as f:
            await f.write(json.dumps(alert, indent=2))

        logger.warning(f"🚨 ALERT: {entry.category.upper()} alert on {entry.vm}: {entry.message}")

    async def process_vm_logs(self, vm_name: str):
        """Process all logs for a specific VM"""
        vm_dir = self.centralized_dir / vm_name
        if not vm_dir.exists():
            logger.warning(f"VM directory not found: {vm_dir}")
            return []

        all_entries = []

        # Process all log files in VM directory
        for log_file in vm_dir.rglob("*.log"):
            if log_file.is_file():
                entries = await self.parse_log_file(log_file, vm_name)
                all_entries.extend(entries)

        # Save parsed entries
        parsed_dir = vm_dir / 'parsed'
        parsed_dir.mkdir(exist_ok=True)

        parsed_file = parsed_dir / f"parsed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        parsed_data = [entry.to_dict() for entry in all_entries]

        async with aiofiles.open(parsed_file, 'w') as f:
            await f.write(json.dumps(parsed_data, indent=2))

        logger.info(f"Processed {len(all_entries)} log entries for {vm_name}")
        return all_entries

    async def generate_summary_report(self):
        """Generate comprehensive summary report"""
        summary = {
            'timestamp': datetime.now().isoformat(),
            'vms': {},
            'alerts': {
                'critical': len([a for a in self.alerts if a['severity'] >= 5]),
                'warning': len([a for a in self.alerts if a['severity'] >= 3]),
                'total': len(self.alerts)
            },
            'categories': {},
            'recent_activity': []
        }

        # Process each VM
        vm_dirs = [d for d in self.centralized_dir.iterdir() if d.is_dir() and d.name.startswith(('vm', 'main-'))]

        for vm_dir in vm_dirs:
            vm_name = vm_dir.name
            log_count = len(list(vm_dir.rglob("*.log")))
            latest_log = max(vm_dir.rglob("*.log"), key=lambda x: x.stat().st_mtime, default=None)

            summary['vms'][vm_name] = {
                'log_files': log_count,
                'latest_activity': latest_log.stat().st_mtime if latest_log else None
            }

        # Save summary
        summary_file = self.centralized_dir / 'aggregated' / f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        async with aiofiles.open(summary_file, 'w') as f:
            await f.write(json.dumps(summary, indent=2))

        return summary

async def main():
    parser = argparse.ArgumentParser(description='AutoBot Enhanced Log Parser')
    parser.add_argument('--centralized-dir', required=True, help='Path to centralized logs directory')
    parser.add_argument('--vm', help='Process specific VM only')
    parser.add_argument('--summary', action='store_true', help='Generate summary report')

    args = parser.parse_args()

    log_parser = EnhancedLogParser(args.centralized_dir)

    if args.vm:
        await log_parser.process_vm_logs(args.vm)
    else:
        # Process all VMs
        vm_dirs = [d.name for d in Path(args.centralized_dir).iterdir()
                  if d.is_dir() and d.name.startswith(('vm', 'main-'))]

        tasks = [log_parser.process_vm_logs(vm) for vm in vm_dirs]
        await asyncio.gather(*tasks)

    if args.summary:
        summary = await log_parser.generate_summary_report()
        print(json.dumps(summary, indent=2))

if __name__ == '__main__':
    asyncio.run(main())
EOF

    chmod +x "$SCRIPT_DIR/enhanced-log-parser.py"
    log_success "Enhanced log parser created"
}

create_real_time_monitoring() {
    log_step "Creating real-time monitoring and alerting system..."

    # Create real-time log monitor
    cat > "$SCRIPT_DIR/real-time-monitor.sh" << 'EOF'
#!/bin/bash

# AutoBot Real-Time Log Monitor
# Monitors logs in real-time and triggers alerts

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
CENTRALIZED_DIR="$PROJECT_ROOT/logs/autobot-centralized"
ALERT_WEBHOOK="${ALERT_WEBHOOK:-}"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Alert patterns
declare -A ALERT_PATTERNS=(
    ["CRITICAL"]="critical|fatal|emergency|panic|crash"
    ["ERROR"]="error|failed|exception|timeout"
    ["WARNING"]="warning|warn|regression|deprecated"
    ["PERFORMANCE"]="gpu.*regression|cpu.*high|memory.*full|performance.*degraded"
    ["SECURITY"]="unauthorized|failed.*login|security|attack|breach"
)

send_alert() {
    local severity="$1"
    local vm="$2"
    local message="$3"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    # Log alert locally
    echo "[$timestamp] $severity ALERT on $vm: $message" >> "$CENTRALIZED_DIR/alerts/${severity,,}.log"

    # Console output
    case $severity in
        "CRITICAL")
            echo -e "${RED}🚨 CRITICAL ALERT [$vm]: $message${NC}"
            ;;
        "ERROR")
            echo -e "${RED}❌ ERROR [$vm]: $message${NC}"
            ;;
        "WARNING")
            echo -e "${YELLOW}⚠️  WARNING [$vm]: $message${NC}"
            ;;
        "PERFORMANCE")
            echo -e "${CYAN}📊 PERFORMANCE [$vm]: $message${NC}"
            ;;
        "SECURITY")
            echo -e "${RED}🔒 SECURITY [$vm]: $message${NC}"
            ;;
    esac

    # Send webhook if configured
    if [[ -n "$ALERT_WEBHOOK" ]]; then
        curl -s -X POST "$ALERT_WEBHOOK" \
            -H "Content-Type: application/json" \
            -d "{\"severity\":\"$severity\",\"vm\":\"$vm\",\"message\":\"$message\",\"timestamp\":\"$timestamp\"}" \
            >/dev/null 2>&1
    fi
}

monitor_log_file() {
    local log_file="$1"
    local vm_name="$2"

    tail -F "$log_file" 2>/dev/null | while IFS= read -r line; do
        # Check each alert pattern
        for severity in "${!ALERT_PATTERNS[@]}"; do
            pattern="${ALERT_PATTERNS[$severity]}"
            if echo "$line" | grep -iE "$pattern" >/dev/null; then
                send_alert "$severity" "$vm_name" "$line"
                break
            fi
        done
    done
}

main() {
    echo -e "${CYAN}Starting AutoBot Real-Time Log Monitor...${NC}"
    echo "Monitoring directory: $CENTRALIZED_DIR"
    echo "Press Ctrl+C to stop"
    echo ""

    # Create alert directories
    mkdir -p "$CENTRALIZED_DIR/alerts"/{critical,error,warning,performance,security}

    # Find all current log files and start monitoring
    local pids=()

    while IFS= read -r -d '' log_file; do
        # Extract VM name from path
        vm_name=$(echo "$log_file" | sed "s|$CENTRALIZED_DIR/||" | cut -d'/' -f1)

        echo "Monitoring: $log_file ($vm_name)"
        monitor_log_file "$log_file" "$vm_name" &
        pids+=($!)

    done < <(find "$CENTRALIZED_DIR" -name "*.log" -type f -print0)

    # Monitor for new log files
    inotifywait -m -r -e create --format '%w%f' "$CENTRALIZED_DIR" 2>/dev/null | while read new_file; do
        if [[ "$new_file" == *.log ]]; then
            vm_name=$(echo "$new_file" | sed "s|$CENTRALIZED_DIR/||" | cut -d'/' -f1)
            echo "New log file detected: $new_file ($vm_name)"
            monitor_log_file "$new_file" "$vm_name" &
            pids+=($!)
        fi
    done &
    pids+=($!)

    # Cleanup on exit
    trap 'echo "Stopping monitors..."; kill "${pids[@]}" 2>/dev/null; exit 0' INT TERM

    # Wait for all background processes
    wait
}

# Check dependencies
if ! command -v inotifywait &> /dev/null; then
    echo "Installing inotify-tools..."
    sudo apt-get update -qq && sudo apt-get install -y inotify-tools
fi

main "$@"
EOF

    chmod +x "$SCRIPT_DIR/real-time-monitor.sh"
    log_success "Real-time monitoring system created"
}

create_performance_integration() {
    log_step "Creating performance monitoring integration..."

    # Create performance log aggregator
    cat > "$SCRIPT_DIR/performance-aggregator.py" << 'EOF'
#!/usr/bin/env python3
"""
AutoBot Performance Log Aggregator
Aggregates and analyzes performance metrics from all VMs
"""

import json
import re
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import argparse

class PerformanceMetrics:
    def __init__(self):
        self.cpu_values = []
        self.memory_values = []
        self.gpu_values = []
        self.api_response_times = []
        self.service_counts = []
        self.regressions = []

    def add_measurement(self, timestamp: datetime, cpu: float = None, memory: float = None,
                       gpu: float = None, api_time: float = None, services: int = None):
        if cpu is not None:
            self.cpu_values.append((timestamp, cpu))
        if memory is not None:
            self.memory_values.append((timestamp, memory))
        if gpu is not None:
            self.gpu_values.append((timestamp, gpu))
        if api_time is not None:
            self.api_response_times.append((timestamp, api_time))
        if services is not None:
            self.service_counts.append((timestamp, services))

    def add_regression(self, timestamp: datetime, metric: str, old_value: float, new_value: float):
        self.regressions.append({
            'timestamp': timestamp.isoformat(),
            'metric': metric,
            'old_value': old_value,
            'new_value': new_value,
            'change_percent': ((new_value - old_value) / old_value) * 100 if old_value > 0 else 0
        })

    def get_summary(self) -> Dict:
        def stats_for_metric(values):
            if not values:
                return None

            recent_values = [v[1] for v in values[-10:]]  # Last 10 measurements
            return {
                'current': recent_values[-1] if recent_values else None,
                'average': statistics.mean(recent_values),
                'min': min(recent_values),
                'max': max(recent_values),
                'trend': 'up' if len(recent_values) > 1 and recent_values[-1] > recent_values[0] else 'down'
            }

        return {
            'timestamp': datetime.now().isoformat(),
            'cpu': stats_for_metric(self.cpu_values),
            'memory': stats_for_metric(self.memory_values),
            'gpu': stats_for_metric(self.gpu_values),
            'api_response': stats_for_metric(self.api_response_times),
            'services': stats_for_metric(self.service_counts),
            'regressions': {
                'count': len(self.regressions),
                'recent': self.regressions[-5:] if self.regressions else []
            }
        }

class PerformanceAggregator:
    def __init__(self, centralized_dir: Path):
        self.centralized_dir = Path(centralized_dir)
        self.metrics = PerformanceMetrics()

        # Regex patterns for different performance log formats
        self.patterns = {
            'autobot_performance': re.compile(
                r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}),\d+.*?'
                r'CPU:\s*([\d.]+)%.*?'
                r'MEM:\s*([\d.]+)%.*?'
                r'GPU:\s*([\d.]+)%.*?'
                r'Services:\s*(\d+)/\d+.*?'
                r'API:\s*(\d+)ms'
            ),
            'regression_pattern': re.compile(
                r'REGRESSION.*?(\w+).*?(\d+\.?\d*).+?(\d+\.?\d*)'
            ),
            'gpu_regression': re.compile(
                r'GPU utilization dropped from ([\d.]+)% to ([\d.]+)%'
            )
        }

    def parse_performance_logs(self):
        """Parse performance logs from all sources"""
        # Main performance monitor log
        main_perf_log = self.centralized_dir.parent / 'performance_monitor.log'
        if main_perf_log.exists():
            self._parse_main_performance_log(main_perf_log)

        # VM-specific performance logs
        for vm_dir in self.centralized_dir.iterdir():
            if vm_dir.is_dir() and vm_dir.name.startswith(('vm', 'main-')):
                self._parse_vm_performance_logs(vm_dir)

    def _parse_main_performance_log(self, log_file: Path):
        """Parse main performance monitor log"""
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                # Parse performance metrics
                match = self.patterns['autobot_performance'].search(line)
                if match:
                    timestamp_str, cpu, memory, gpu, services, api_time = match.groups()
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')

                    self.metrics.add_measurement(
                        timestamp=timestamp,
                        cpu=float(cpu),
                        memory=float(memory),
                        gpu=float(gpu),
                        services=int(services),
                        api_time=float(api_time)
                    )

                # Parse GPU regressions
                gpu_match = self.patterns['gpu_regression'].search(line)
                if gpu_match:
                    old_value, new_value = gpu_match.groups()
                    timestamp = self._extract_timestamp_from_line(line)

                    self.metrics.add_regression(
                        timestamp=timestamp,
                        metric='gpu_utilization',
                        old_value=float(old_value),
                        new_value=float(new_value)
                    )

    def _parse_vm_performance_logs(self, vm_dir: Path):
        """Parse VM-specific performance logs"""
        for log_file in vm_dir.rglob("*performance*.log"):
            if log_file.is_file():
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        # VM-specific performance parsing logic
                        pass

    def _extract_timestamp_from_line(self, line: str) -> datetime:
        """Extract timestamp from log line"""
        timestamp_match = re.search(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', line)
        if timestamp_match:
            return datetime.strptime(timestamp_match.group(1), '%Y-%m-%d %H:%M:%S')
        return datetime.now()

    def generate_performance_report(self) -> Dict:
        """Generate comprehensive performance report"""
        summary = self.metrics.get_summary()

        # Add additional analysis
        report = {
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'report_type': 'performance_aggregation',
                'data_sources': ['main_performance_log', 'vm_performance_logs']
            },
            'summary': summary,
            'alerts': self._generate_performance_alerts(summary),
            'recommendations': self._generate_recommendations(summary)
        }

        return report

    def _generate_performance_alerts(self, summary: Dict) -> List[Dict]:
        """Generate performance alerts based on metrics"""
        alerts = []

        # CPU alerts
        if summary['cpu'] and summary['cpu']['current'] > 80:
            alerts.append({
                'severity': 'warning',
                'metric': 'cpu',
                'message': f"High CPU usage: {summary['cpu']['current']:.1f}%",
                'threshold': 80
            })

        # GPU alerts
        if summary['gpu'] and summary['gpu']['current'] < 5:
            alerts.append({
                'severity': 'warning',
                'metric': 'gpu',
                'message': f"Low GPU utilization: {summary['gpu']['current']:.1f}%",
                'threshold': 5
            })

        # Memory alerts
        if summary['memory'] and summary['memory']['current'] > 90:
            alerts.append({
                'severity': 'critical',
                'metric': 'memory',
                'message': f"High memory usage: {summary['memory']['current']:.1f}%",
                'threshold': 90
            })

        # API response time alerts
        if summary['api_response'] and summary['api_response']['current'] > 1000:
            alerts.append({
                'severity': 'warning',
                'metric': 'api_response',
                'message': f"Slow API response: {summary['api_response']['current']:.0f}ms",
                'threshold': 1000
            })

        return alerts

    def _generate_recommendations(self, summary: Dict) -> List[str]:
        """Generate performance recommendations"""
        recommendations = []

        if summary['gpu'] and summary['gpu']['current'] < 10:
            recommendations.append("Consider enabling GPU acceleration for AI workloads")

        if summary['api_response'] and summary['api_response']['average'] > 500:
            recommendations.append("API response times are high, consider optimizing backend")

        if summary['regressions']['count'] > 5:
            recommendations.append("Multiple regressions detected, review recent changes")

        return recommendations

    def save_report(self, report: Dict, output_dir: Path = None):
        """Save performance report to file"""
        if output_dir is None:
            output_dir = self.centralized_dir / 'metrics' / 'performance'

        output_dir.mkdir(parents=True, exist_ok=True)

        report_file = output_dir / f"performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)

        print(f"Performance report saved to: {report_file}")
        return report_file

def main():
    parser = argparse.ArgumentParser(description='AutoBot Performance Aggregator')
    parser.add_argument('--centralized-dir', required=True, help='Path to centralized logs directory')
    parser.add_argument('--output-dir', help='Output directory for reports')
    parser.add_argument('--print-summary', action='store_true', help='Print summary to console')

    args = parser.parse_args()

    aggregator = PerformanceAggregator(args.centralized_dir)
    aggregator.parse_performance_logs()

    report = aggregator.generate_performance_report()

    if args.print_summary:
        print(json.dumps(report['summary'], indent=2))

    output_dir = Path(args.output_dir) if args.output_dir else None
    aggregator.save_report(report, output_dir)

    # Print alerts
    if report['alerts']:
        print("\n🚨 Performance Alerts:")
        for alert in report['alerts']:
            print(f"  {alert['severity'].upper()}: {alert['message']}")

    # Print recommendations
    if report['recommendations']:
        print("\n💡 Recommendations:")
        for rec in report['recommendations']:
            print(f"  • {rec}")

if __name__ == '__main__':
    main()
EOF

    chmod +x "$SCRIPT_DIR/performance-aggregator.py"
    log_success "Performance monitoring integration created"
}

create_deployment_automation() {
    log_step "Creating deployment automation scripts..."

    # Create master deployment script
    cat > "$SCRIPT_DIR/deploy-logging-stack.sh" << 'EOF'
#!/bin/bash

# AutoBot Logging Stack Deployment Automation
# Orchestrates the complete deployment of enhanced logging system

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Color codes
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║            AutoBot Enhanced Logging Deployment              ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Step 1: Deploy enhanced logging system
echo -e "${YELLOW}Step 1: Deploying enhanced centralized logging...${NC}"
bash "$SCRIPT_DIR/deploy-enhanced-logging.sh"

# Step 2: Setup automation
echo -e "${YELLOW}Step 2: Setting up automation...${NC}"
bash "$SCRIPT_DIR/setup-log-automation.sh"

# Step 3: Start monitoring
echo -e "${YELLOW}Step 3: Starting real-time monitoring...${NC}"
systemd-run --user --unit=autobot-log-monitor "$SCRIPT_DIR/real-time-monitor.sh" &

# Step 4: Initial performance aggregation
echo -e "${YELLOW}Step 4: Running initial performance aggregation...${NC}"
python3 "$SCRIPT_DIR/performance-aggregator.py" --centralized-dir "$(dirname "$SCRIPT_DIR")/../logs/autobot-centralized" --print-summary

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                 Deployment Complete!                        ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}Available Commands:${NC}"
echo "  View logs:       bash $SCRIPT_DIR/view-centralized-logs.sh"
echo "  Monitor live:    bash $SCRIPT_DIR/real-time-monitor.sh"
echo "  Performance:     python3 $SCRIPT_DIR/performance-aggregator.py --centralized-dir ../logs/autobot-centralized"
echo "  Parse logs:      python3 $SCRIPT_DIR/enhanced-log-parser.py --centralized-dir ../logs/autobot-centralized"
echo ""
echo -e "${CYAN}Web Interfaces:${NC}"
echo "  Loki API:        http://${AUTOBOT_BACKEND_HOST:-172.16.168.20}:3100"
echo "  Grafana Logs:    http://${AUTOBOT_BACKEND_HOST:-172.16.168.20}:3001 (admin/autobot123)"
echo ""
echo -e "${CYAN}Log Locations:${NC}"
echo "  Centralized:     $(dirname "$SCRIPT_DIR")/../logs/autobot-centralized/"
echo "  Alerts:          $(dirname "$SCRIPT_DIR")/../logs/autobot-centralized/alerts/"
echo "  Performance:     $(dirname "$SCRIPT_DIR")/../logs/autobot-centralized/metrics/"
EOF

    chmod +x "$SCRIPT_DIR/deploy-logging-stack.sh"

    # Create status monitoring script
    cat > "$SCRIPT_DIR/logging-system-status.sh" << 'EOF'
#!/bin/bash

# AutoBot Logging System Status Check
# Comprehensive status check for all logging components

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
CENTRALIZED_DIR="$PROJECT_ROOT/logs/autobot-centralized"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

check_service() {
    local service_name="$1"
    local check_command="$2"

    echo -n "  $service_name: "
    if eval "$check_command" >/dev/null 2>&1; then
        echo -e "${GREEN}✓ Running${NC}"
        return 0
    else
        echo -e "${RED}✗ Not Running${NC}"
        return 1
    fi
}

check_vm_connectivity() {
    local vm_name="$1"
    local vm_ip="$2"

    echo -n "  $vm_name ($vm_ip): "
    if ssh -i "${AUTOBOT_SSH_KEY:-$HOME/.ssh/autobot_key}" -o ConnectTimeout=3 -o BatchMode=yes "${AUTOBOT_SSH_USER:-autobot}"@"$vm_ip" "echo test" >/dev/null 2>&1; then
        echo -e "${GREEN}✓ Connected${NC}"
        return 0
    else
        echo -e "${RED}✗ Unreachable${NC}"
        return 1
    fi
}

echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║              AutoBot Logging System Status                   ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check main services
echo -e "${BLUE}Main Services:${NC}"
check_service "Loki" "docker ps | grep autobot-loki"
check_service "Grafana" "docker ps | grep autobot-grafana-logs"
check_service "rsyslog" "systemctl is-active rsyslog"

echo ""

# Check VM connectivity
echo -e "${BLUE}VM Connectivity:${NC}"
declare -A VMS=(
    ["vm1-frontend"]="${AUTOBOT_FRONTEND_HOST:-172.16.168.21}"
    ["vm2-npu-worker"]="${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}"
    ["vm3-redis"]="${AUTOBOT_REDIS_HOST:-172.16.168.23}"
    ["vm4-ai-stack"]="${AUTOBOT_AI_STACK_HOST:-172.16.168.24}"
    ["vm5-browser"]="${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}"
)

connected_vms=0
for vm_name in "${!VMS[@]}"; do
    if check_vm_connectivity "$vm_name" "${VMS[$vm_name]}"; then
        ((connected_vms++))
    fi
done

echo ""

# Check Promtail agents
echo -e "${BLUE}Promtail Agents:${NC}"
for vm_name in "${!VMS[@]}"; do
    vm_ip="${VMS[$vm_name]}"
    echo -n "  $vm_name: "
    if ssh -i "${AUTOBOT_SSH_KEY:-$HOME/.ssh/autobot_key}" -o ConnectTimeout=3 "${AUTOBOT_SSH_USER:-autobot}"@"$vm_ip" "systemctl is-active promtail" >/dev/null 2>&1; then
        echo -e "${GREEN}✓ Active${NC}"
    else
        echo -e "${RED}✗ Inactive${NC}"
    fi
done

echo ""

# Check log collection status
echo -e "${BLUE}Log Collection Status:${NC}"
if [[ -d "$CENTRALIZED_DIR" ]]; then
    total_logs=$(find "$CENTRALIZED_DIR" -name "*.log" -type f | wc -l)
    total_size=$(du -sh "$CENTRALIZED_DIR" 2>/dev/null | cut -f1)
    latest_log=$(find "$CENTRALIZED_DIR" -name "*.log" -type f -printf "%TY-%Tm-%Td %TH:%TM %p\n" 2>/dev/null | sort -r | head -1)

    echo "  Total log files: $total_logs"
    echo "  Total size: $total_size"
    echo "  Latest activity: $latest_log"
else
    echo -e "  ${RED}Centralized directory not found${NC}"
fi

echo ""

# Check for recent alerts
echo -e "${BLUE}Recent Alerts (last hour):${NC}"
if [[ -d "$CENTRALIZED_DIR/alerts" ]]; then
    recent_alerts=$(find "$CENTRALIZED_DIR/alerts" -name "*.log" -type f -mmin -60 -exec wc -l {} + 2>/dev/null | tail -1 | awk '{print $1}' || echo "0")
    if [[ "$recent_alerts" -gt 0 ]]; then
        echo -e "  ${YELLOW}$recent_alerts alerts in the last hour${NC}"
        find "$CENTRALIZED_DIR/alerts" -name "*.log" -type f -mmin -60 -exec tail -3 {} \; 2>/dev/null | head -10
    else
        echo -e "  ${GREEN}No alerts in the last hour${NC}"
    fi
else
    echo "  Alert directory not found"
fi

echo ""

# Performance summary
echo -e "${BLUE}Performance Summary:${NC}"
if [[ -f "$PROJECT_ROOT/logs/performance_monitor.log" ]]; then
    latest_perf=$(tail -1 "$PROJECT_ROOT/logs/performance_monitor.log" 2>/dev/null | grep -oE 'CPU: [0-9.]+%|MEM: [0-9.]+%|GPU: [0-9.]+%|API: [0-9]+ms' | tr '\n' ' ')
    if [[ -n "$latest_perf" ]]; then
        echo "  Latest: $latest_perf"
    else
        echo "  No recent performance data"
    fi
else
    echo "  Performance monitor log not found"
fi

echo ""

# Overall status
echo -e "${BLUE}Overall Status:${NC}"
if [[ $connected_vms -eq 5 ]]; then
    echo -e "  ${GREEN}✓ All systems operational${NC}"
else
    echo -e "  ${YELLOW}⚠ Some components may need attention${NC}"
fi

echo ""
echo -e "${CYAN}Quick Actions:${NC}"
echo "  View logs:       bash $SCRIPT_DIR/view-centralized-logs.sh"
echo "  Real-time:       bash $SCRIPT_DIR/real-time-monitor.sh"
echo "  Performance:     python3 $SCRIPT_DIR/performance-aggregator.py --centralized-dir $CENTRALIZED_DIR --print-summary"
EOF

    chmod +x "$SCRIPT_DIR/logging-system-status.sh"

    log_success "Deployment automation scripts created"
}

create_documentation() {
    log_step "Creating comprehensive documentation..."

    cat > "$SCRIPT_DIR/../../../docs/CENTRALIZED_LOGGING_SYSTEM.md" << 'EOF'
# AutoBot Centralized Logging System

## Overview

The AutoBot Centralized Logging System provides comprehensive, real-time log collection, aggregation, and monitoring across the entire distributed VM infrastructure. The system combines traditional rsyslog functionality with modern tools like Loki and Promtail for enhanced log management.

## Architecture

### Components

1. **Loki + Grafana Stack** - Modern log aggregation and visualization
2. **Promtail Agents** - Lightweight log shippers on each VM
3. **rsyslog** - Traditional syslog forwarding (fallback)
4. **Enhanced Log Parser** - Intelligent log categorization and alerting
5. **Real-Time Monitor** - Live log monitoring with instant alerts
6. **Performance Aggregator** - Performance metrics analysis

### Infrastructure Layout

```
Main Machine (172.16.168.20)
├── Loki (port 3100) - Log aggregation
├── Grafana (port 3001) - Log visualization
├── rsyslog server (port 514) - Syslog collection
└── Enhanced parsers and monitors

VM1 Frontend (172.16.168.21)
├── Promtail agent
├── rsyslog client
└── nginx, autobot-frontend logs

VM2 NPU Worker (172.16.168.22)
├── Promtail agent
├── rsyslog client
└── autobot-npu-worker, docker logs

VM3 Redis (172.16.168.23)
├── Promtail agent
├── rsyslog client
└── redis-stack-server logs

VM4 AI Stack (172.16.168.24)
├── Promtail agent
├── rsyslog client
└── autobot-ai-stack, autobot-backend logs

VM5 Browser (172.16.168.25)
├── Promtail agent
├── rsyslog client
└── autobot-playwright, docker logs
```

## Installation & Setup

### Initial Deployment

```bash
# Deploy the complete enhanced logging system
bash scripts/logging/deploy-enhanced-logging.sh

# Or use the automated stack deployment
bash scripts/logging/deploy-logging-stack.sh
```

### Manual Component Setup

```bash
# Setup basic centralized logging (rsyslog-based)
bash scripts/logging/setup-centralized-logging.sh

# Deploy Loki stack only
cd config/logging/loki
docker-compose -f docker-compose-loki.yml up -d

# Setup Promtail agents on VMs
bash scripts/logging/deploy-enhanced-logging.sh --promtail-only
```

## Usage

### Interactive Log Viewer

```bash
# Launch the interactive log browser
bash scripts/logging/view-centralized-logs.sh
```

Features:
- Browse logs by VM
- Filter by log type (system/application/service)
- Search across all logs
- Real-time tail functionality
- Disk usage monitoring

### Real-Time Monitoring

```bash
# Start real-time log monitoring with alerts
bash scripts/logging/real-time-monitor.sh
```

Features:
- Live log tailing from all VMs
- Pattern-based alerting
- Console notifications
- Webhook integration support
- Alert categorization (Critical/Error/Warning/Performance/Security)

### Performance Analysis

```bash
# Generate performance report
python3 scripts/logging/performance-aggregator.py \
  --centralized-dir logs/autobot-centralized \
  --print-summary

# Continuous performance monitoring
while true; do
  python3 scripts/logging/performance-aggregator.py \
    --centralized-dir logs/autobot-centralized
  sleep 300  # Every 5 minutes
done
```

### Enhanced Log Parsing

```bash
# Parse all VM logs with intelligent categorization
python3 scripts/logging/enhanced-log-parser.py \
  --centralized-dir logs/autobot-centralized \
  --summary

# Parse specific VM
python3 scripts/logging/enhanced-log-parser.py \
  --centralized-dir logs/autobot-centralized \
  --vm vm1-frontend
```

## Web Interfaces

### Loki API
- **URL**: http://172.16.168.20:3100
- **Purpose**: Direct log querying and API access
- **Query Language**: LogQL

Example queries:
```
{job="autobot-system"} |= "error"
{host="vm1-frontend"} | json | line_format "{{.message}}"
rate({job="autobot-performance"}[5m])
```

### Grafana Logs Dashboard
- **URL**: http://172.16.168.20:3001
- **Credentials**: admin / autobot123
- **Features**:
  - Pre-configured AutoBot dashboards
  - Log correlation with metrics
  - Alert rule management
  - Custom dashboard creation

## Configuration

### Directory Structure

```
logs/autobot-centralized/
├── aggregated/          # Processed and categorized logs
│   ├── by-service/      # Logs grouped by service type
│   ├── by-severity/     # Logs grouped by severity level
│   └── by-time/         # Time-based log aggregation
├── alerts/              # Generated alerts
│   ├── critical/        # Critical alerts
│   ├── warning/         # Warning alerts
│   └── performance/     # Performance-related alerts
├── metrics/             # Performance and system metrics
│   ├── performance/     # Performance analysis reports
│   ├── system/          # System health metrics
│   └── application/     # Application-specific metrics
├── vm1-frontend/        # VM1 logs
│   ├── system/          # System logs (syslog, kernel, etc.)
│   ├── application/     # Application logs (nginx, autobot-frontend)
│   ├── service/         # Service logs (systemd, docker)
│   ├── real-time/       # Real-time processed logs
│   ├── parsed/          # Intelligently parsed logs
│   ├── metrics/         # VM-specific metrics
│   └── alerts/          # VM-specific alerts
├── vm2-npu-worker/      # VM2 logs (same structure)
├── vm3-redis/           # VM3 logs (same structure)
├── vm4-ai-stack/        # VM4 logs (same structure)
├── vm5-browser/         # VM5 logs (same structure)
└── main-wsl/            # Main machine logs
    ├── backend/         # Backend API logs
    ├── system/          # WSL system logs
    ├── loki/            # Loki-specific logs
    ├── grafana/         # Grafana logs
    └── performance/     # Main machine performance logs
```

### Configuration Files

```
config/logging/
├── loki/
│   ├── loki-config.yml           # Loki server configuration
│   ├── docker-compose-loki.yml   # Loki stack deployment
│   ├── grafana-datasources.yml   # Grafana data sources
│   └── grafana-dashboards.yml    # Dashboard provisioning
├── promtail/
│   └── promtail-config.yml       # Promtail agent configuration
├── grafana/
│   └── dashboards/               # Custom Grafana dashboards
└── alerting/
    └── alert-rules.yml           # Alert rule definitions
```

## Automation

### Automated Log Collection

Cron jobs automatically collect logs:
- **Service logs**: Every 15 minutes
- **Application logs**: Every hour
- **Performance analysis**: Every 5 minutes

### Log Rotation

Automatic log rotation configured:
- **Centralized logs**: 7 days retention, daily rotation
- **Local logs**: 14 days retention, daily rotation
- **Compressed storage**: Older logs automatically compressed

### Health Monitoring

System health checks:
```bash
# Check overall system status
bash scripts/logging/logging-system-status.sh

# Monitor log collection status
bash scripts/logging/log-collection-status.sh
```

## Alerting

### Alert Categories

1. **Critical** (Severity 5)
   - System failures
   - Service crashes
   - Security breaches

2. **Error** (Severity 4)
   - Application errors
   - Failed operations
   - Timeout events

3. **Warning** (Severity 3)
   - Performance degradation
   - Resource warnings
   - Configuration issues

4. **Performance** (Special category)
   - GPU regression detection
   - High CPU/memory usage
   - Slow API responses

5. **Security** (Special category)
   - Unauthorized access attempts
   - Security policy violations
   - Suspicious activity

### Alert Integration

Configure webhook alerts:
```bash
# Set webhook URL for external alert integration
export ALERT_WEBHOOK="https://your-webhook-url.com/alerts"
bash scripts/logging/real-time-monitor.sh
```

## Performance Monitoring Integration

### GPU Regression Detection

The system automatically detects and alerts on:
- GPU utilization drops
- Performance regressions
- Hardware acceleration issues

Example detection from logs:
```
🚨 REGRESSION ALERT: GPU utilization dropped from 17.0% to 8.0%
2025-09-21 11:45:53 - WARNING - REGRESSION DETECTED: GPU utilization dropped from 17.0% to 8.0%
```

### Performance Metrics Tracked

- **CPU Usage**: System and per-service CPU utilization
- **Memory Usage**: RAM usage across all VMs
- **GPU Usage**: AI acceleration hardware utilization
- **API Response Times**: Backend API performance
- **Service Health**: Running service counts and status
- **Network Latency**: Inter-VM communication performance

## Troubleshooting

### Common Issues

1. **VM Connectivity Problems**
   ```bash
   # Check SSH connectivity
   bash scripts/utilities/setup-ssh-keys.sh
   bash scripts/vm-management/status-all-vms.sh
   ```

2. **Missing Logs**
   ```bash
   # Restart log collection
   bash scripts/logging/collect-service-logs.sh
   bash scripts/logging/collect-application-logs.sh
   ```

3. **Loki/Grafana Issues**
   ```bash
   # Restart Loki stack
   cd config/logging/loki
   docker-compose -f docker-compose-loki.yml restart
   ```

4. **Promtail Agent Problems**
   ```bash
   # Check Promtail status on VM
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.21 "sudo systemctl status promtail"

   # Restart Promtail
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.21 "sudo systemctl restart promtail"
   ```

### Log Analysis Commands

```bash
# Find recent errors across all VMs
grep -r -i "error\|failed\|exception" logs/autobot-centralized/ | head -20

# Check performance regressions
grep -r "REGRESSION" logs/autobot-centralized/

# Monitor disk space usage
du -sh logs/autobot-centralized/*

# Find most active log sources
find logs/autobot-centralized/ -name "*.log" -printf "%s %p\n" | sort -rn | head -10
```

## Integration with Existing Systems

### AutoBot Monitoring Integration

The centralized logging system integrates with:
- **Performance Monitor** (`scripts/monitoring/start_monitoring.py`)
- **Backend Monitoring** (`backend/api/monitoring.py`)
- **VM Health Checks** (`scripts/vm-management/status-all-vms.sh`)

### Ansible Integration

Use Ansible for managing logging across VMs:
```bash
# Deploy configuration changes
ansible-playbook -i ansible/inventory/production.yml ansible/playbooks/update-logging-config.yml

# Restart log services
ansible all -i ansible/inventory/production.yml -m systemd -a "name=promtail state=restarted" -b
```

## Security Considerations

### Log Data Protection

- SSH key-based authentication for all VM communications
- Log data stored locally (no external transmission)
- Access controls on centralized log directories
- Automated log rotation to prevent disk exhaustion

### Sensitive Data Handling

- Automatic redaction of potential PII in logs
- Secure transmission of logs via SSH/TLS
- Configurable log retention policies
- Alert data includes only necessary information

## Maintenance

### Regular Maintenance Tasks

1. **Weekly**
   - Review alert patterns
   - Check disk usage trends
   - Validate VM connectivity

2. **Monthly**
   - Archive old log data
   - Update Promtail/Loki versions
   - Review performance trends

3. **Quarterly**
   - Update log parsing patterns
   - Optimize alert thresholds
   - Review retention policies

### Backup Recommendations

```bash
# Backup centralized logs
tar czf "autobot-logs-backup-$(date +%Y%m%d).tar.gz" logs/autobot-centralized/

# Backup configuration
tar czf "autobot-logging-config-$(date +%Y%m%d).tar.gz" config/logging/
```

## Support and Resources

### Quick Reference Commands

```bash
# System status
bash scripts/logging/logging-system-status.sh

# View logs interactively
bash scripts/logging/view-centralized-logs.sh

# Real-time monitoring
bash scripts/logging/real-time-monitor.sh

# Performance analysis
python3 scripts/logging/performance-aggregator.py --centralized-dir logs/autobot-centralized --print-summary

# Parse and categorize logs
python3 scripts/logging/enhanced-log-parser.py --centralized-dir logs/autobot-centralized --summary
```

### Documentation Links

- [Loki Documentation](https://grafana.com/docs/loki/)
- [Promtail Configuration](https://grafana.com/docs/loki/latest/clients/promtail/)
- [Grafana Log Dashboards](https://grafana.com/docs/grafana/latest/features/explore/)
- [AutoBot Architecture Documentation](docs/architecture/PHASE_5_DISTRIBUTED_ARCHITECTURE.md)

EOF

    log_success "Comprehensive documentation created"
}

main() {
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}    AutoBot Enhanced Centralized Logging System Deployment${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════${NC}"
    echo ""

    # Run all deployment steps
    check_prerequisites
    create_enhanced_directory_structure
    deploy_loki_stack
    deploy_promtail_agents
    create_enhanced_log_aggregation
    create_real_time_monitoring
    create_performance_integration
    create_deployment_automation
    create_documentation

    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}    Enhanced Centralized Logging System Deployment Complete!${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════════════${NC}"
    echo ""

    # Show access information
    echo -e "${CYAN}🌐 Web Interfaces:${NC}"
    echo "  Loki API:        http://${AUTOBOT_BACKEND_HOST:-172.16.168.20}:3100"
    echo "  Grafana Logs:    http://${AUTOBOT_BACKEND_HOST:-172.16.168.20}:3001 (admin/autobot123)"
    echo ""

    echo -e "${CYAN}🔧 Management Commands:${NC}"
    echo "  System Status:   bash scripts/logging/logging-system-status.sh"
    echo "  View Logs:       bash scripts/logging/view-centralized-logs.sh"
    echo "  Real-time:       bash scripts/logging/real-time-monitor.sh"
    echo "  Performance:     python3 scripts/logging/performance-aggregator.py --centralized-dir logs/autobot-centralized"
    echo "  Parse Logs:      python3 scripts/logging/enhanced-log-parser.py --centralized-dir logs/autobot-centralized"
    echo ""

    echo -e "${CYAN}📁 Log Locations:${NC}"
    echo "  Centralized:     $CENTRALIZED_DIR"
    echo "  Alerts:          $CENTRALIZED_DIR/alerts/"
    echo "  Performance:     $CENTRALIZED_DIR/metrics/"
    echo "  Documentation:   docs/CENTRALIZED_LOGGING_SYSTEM.md"
    echo ""

    echo -e "${CYAN}🚀 Next Steps:${NC}"
    echo "  1. Check system status: bash scripts/logging/logging-system-status.sh"
    echo "  2. Review documentation: docs/CENTRALIZED_LOGGING_SYSTEM.md"
    echo "  3. Configure alerts: Set ALERT_WEBHOOK environment variable"
    echo "  4. Access Grafana: http://${AUTOBOT_BACKEND_HOST:-172.16.168.20}:3001"
    echo ""
}

# Check if running as main script
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
