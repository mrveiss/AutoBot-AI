#!/bin/bash

# AutoBot Performance Monitoring Installation Script
# Installs and configures the comprehensive performance monitoring system
# for the distributed AutoBot infrastructure

set -e

# Define color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Comprehensive logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

info() {
    echo -e "${CYAN}[INFO]${NC} $1"
}

# Check if running as root or with sudo
check_permissions() {
    if [[ $EUID -eq 0 ]]; then
        error "This script should not be run as root. Run as regular user with sudo privileges."
        exit 1
    fi

    if ! sudo -n true 2>/dev/null; then
        error "This script requires sudo privileges. Please run with a user that has sudo access."
        exit 1
    fi
}

# Check system requirements
check_system_requirements() {
    log "Checking system requirements..."

    # Check OS
    if [[ ! -f /etc/os-release ]]; then
        error "Cannot determine operating system"
        exit 1
    fi

    source /etc/os-release
    info "Operating System: $PRETTY_NAME"

    # Check Python version
    if ! command -v python3 &> /dev/null; then
        error "Python 3 is required but not installed"
        exit 1
    fi

    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    info "Python version: $PYTHON_VERSION"

    # Check minimum Python 3.8
    if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)"; then
        error "Python 3.8 or higher is required"
        exit 1
    fi

    # Check available memory (minimum 4GB)
    TOTAL_MEM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    TOTAL_MEM_GB=$((TOTAL_MEM_KB / 1024 / 1024))

    info "Total memory: ${TOTAL_MEM_GB}GB"

    if [[ $TOTAL_MEM_GB -lt 4 ]]; then
        warning "Less than 4GB RAM available. Performance monitoring may be limited."
    fi

    # Check disk space (minimum 5GB free)
    AVAILABLE_SPACE=$(df / | tail -1 | awk '{print $4}')
    AVAILABLE_GB=$((AVAILABLE_SPACE / 1024 / 1024))

    info "Available disk space: ${AVAILABLE_GB}GB"

    if [[ $AVAILABLE_GB -lt 5 ]]; then
        error "At least 5GB free disk space is required"
        exit 1
    fi

    success "System requirements check passed"
}

# Install system dependencies
install_system_dependencies() {
    log "Installing system dependencies..."

    # Update package lists
    sudo apt-get update -qq

    # Install required packages
    PACKAGES=(
        "python3-pip"
        "python3-venv"
        "python3-dev"
        "build-essential"
        "curl"
        "wget"
        "redis-tools"
        "htop"
        "iotop"
        "netstat-nat"
        "tcpdump"
        "nmap"
        "iftop"
        "nethogs"
        "dstat"
        "sysstat"
        "lsof"
        "strace"
        "nginx"  # For reverse proxy (optional)
        "nodejs"
        "npm"
        "git"
    )

    for package in "${PACKAGES[@]}"; do
        if ! dpkg -l | grep -q "^ii  $package "; then
            info "Installing $package..."
            sudo apt-get install -y "$package" > /dev/null 2>&1
        else
            info "$package already installed"
        fi
    done

    success "System dependencies installed"
}

# Install Python dependencies
install_python_dependencies() {
    log "Installing Python dependencies..."

    # Create virtual environment if it doesn't exist
    if [[ ! -d "/home/kali/Desktop/AutoBot/venv" ]]; then
        info "Creating Python virtual environment..."
        cd /home/kali/Desktop/AutoBot
        python3 -m venv venv
    fi

    # Activate virtual environment
    source /home/kali/Desktop/AutoBot/venv/bin/activate

    # Upgrade pip
    pip install --upgrade pip > /dev/null 2>&1

    # Install monitoring-specific Python packages
    PYTHON_PACKAGES=(
        "redis>=4.5.0"
        "aiohttp>=3.8.0"
        "aiofiles>=22.1.0"
        "numpy>=1.21.0"
        "matplotlib>=3.5.0"
        "seaborn>=0.11.0"
        "plotly>=5.0.0"
        "psutil>=5.8.0"
        "pyyaml>=6.0"
        "asyncio-mqtt>=0.11.0"
        "websockets>=10.0"
        "jinja2>=3.0.0"
        "aiohttp-jinja2>=1.5.0"
        "prometheus-client>=0.15.0"
        "py-cpuinfo>=8.0.0"
        "GPUtil>=1.4.0"  # For GPU monitoring
        "nvidia-ml-py3>=7.352.0"  # For NVIDIA GPU monitoring
    )

    info "Installing Python monitoring packages..."
    for package in "${PYTHON_PACKAGES[@]}"; do
        pip install "$package" > /dev/null 2>&1 || warning "Failed to install $package"
    done

    # Install optional packages for enhanced functionality
    OPTIONAL_PACKAGES=(
        "openvino-dev"  # Intel OpenVINO for NPU monitoring
        "tensorflow>=2.10.0"  # For AI performance monitoring
        "torch>=1.12.0"  # PyTorch for GPU benchmarking
    )

    info "Installing optional Python packages..."
    for package in "${OPTIONAL_PACKAGES[@]}"; do
        pip install "$package" > /dev/null 2>&1 || warning "Optional package $package not installed"
    done

    deactivate

    success "Python dependencies installed"
}

# Set up monitoring directories and permissions
setup_directories() {
    log "Setting up monitoring directories..."

    DIRECTORIES=(
        "/home/kali/Desktop/AutoBot/logs/performance"
        "/home/kali/Desktop/AutoBot/logs/benchmarks"
        "/home/kali/Desktop/AutoBot/logs/metrics"
        "/home/kali/Desktop/AutoBot/logs/alerts"
        "/home/kali/Desktop/AutoBot/monitoring/templates"
        "/home/kali/Desktop/AutoBot/monitoring/static"
        "/home/kali/Desktop/AutoBot/config/monitoring"
    )

    for dir in "${DIRECTORIES[@]}"; do
        if [[ ! -d "$dir" ]]; then
            mkdir -p "$dir"
            info "Created directory: $dir"
        fi
    done

    # Set appropriate permissions
    chmod -R 755 /home/kali/Desktop/AutoBot/monitoring/
    chmod -R 755 /home/kali/Desktop/AutoBot/logs/

    success "Monitoring directories configured"
}

# Configure system monitoring tools
configure_system_monitoring() {
    log "Configuring system monitoring tools..."

    # Enable system monitoring services
    sudo systemctl enable --now sysstat || warning "Could not enable sysstat service"

    # Configure log rotation for monitoring logs
    sudo tee /etc/logrotate.d/autobot-monitoring > /dev/null << EOF
/home/kali/Desktop/AutoBot/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 kali kali
    postrotate
        /bin/systemctl reload autobot-monitoring.service 2>/dev/null || true
    endscript
}

/home/kali/Desktop/AutoBot/logs/performance/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 kali kali
}

/home/kali/Desktop/AutoBot/logs/benchmarks/*.log {
    weekly
    rotate 12
    compress
    delaycompress
    missingok
    notifempty
    create 644 kali kali
}
EOF

    info "Log rotation configured"

    # Configure system limits for monitoring
    sudo tee /etc/security/limits.d/autobot-monitoring.conf > /dev/null << EOF
# AutoBot Performance Monitoring Limits
kali soft nofile 65536
kali hard nofile 65536
kali soft nproc 32768
kali hard nproc 32768
EOF

    info "System limits configured for monitoring"

    success "System monitoring tools configured"
}

# Install and configure monitoring service
install_monitoring_service() {
    log "Installing AutoBot monitoring service..."

    # Create systemd service file
    sudo tee /etc/systemd/system/autobot-monitoring.service > /dev/null << EOF
[Unit]
Description=AutoBot Performance Monitoring System
After=network.target redis.service
Wants=network.target

[Service]
Type=simple
User=kali
Group=kali
WorkingDirectory=/home/kali/Desktop/AutoBot
Environment=PYTHONPATH=/home/kali/Desktop/AutoBot
Environment=PATH=/home/kali/Desktop/AutoBot/venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/home/kali/Desktop/AutoBot/venv/bin/python /home/kali/Desktop/AutoBot/monitoring/monitor_control.py --start
ExecStop=/home/kali/Desktop/AutoBot/venv/bin/python /home/kali/Desktop/AutoBot/monitoring/monitor_control.py --stop
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=autobot-monitoring

# Resource limits
LimitNOFILE=65536
LimitNPROC=32768

# Security settings
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=false
ReadWritePaths=/home/kali/Desktop/AutoBot/logs
ReadWritePaths=/tmp

[Install]
WantedBy=multi-user.target
EOF

    # Reload systemd and enable service
    sudo systemctl daemon-reload
    sudo systemctl enable autobot-monitoring.service

    info "AutoBot monitoring service installed and enabled"

    # Create monitoring control script
    sudo tee /usr/local/bin/autobot-monitor > /dev/null << EOF
#!/bin/bash
# AutoBot Performance Monitoring Control Script

cd /home/kali/Desktop/AutoBot
source venv/bin/activate
exec python monitoring/monitor_control.py "\$@"
EOF

    sudo chmod +x /usr/local/bin/autobot-monitor

    info "Created autobot-monitor command"

    success "Monitoring service installed"
}

# Configure dashboard reverse proxy (optional)
configure_dashboard_proxy() {
    log "Configuring dashboard reverse proxy..."

    # Create nginx configuration for dashboard
    sudo tee /etc/nginx/sites-available/autobot-dashboard > /dev/null << EOF
server {
    listen 80;
    server_name autobot-dashboard localhost;

    # Main dashboard
    location / {
        proxy_pass http://127.0.0.1:9090;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;
    }

    # WebSocket endpoint
    location /ws {
        proxy_pass http://127.0.0.1:9090;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Static files
    location /static/ {
        alias /home/kali/Desktop/AutoBot/monitoring/static/;
        expires 1d;
        add_header Cache-Control "public, immutable";
    }

    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
}
EOF

    # Enable the site
    sudo ln -sf /etc/nginx/sites-available/autobot-dashboard /etc/nginx/sites-enabled/

    # Test nginx configuration
    if sudo nginx -t > /dev/null 2>&1; then
        sudo systemctl reload nginx || warning "Could not reload nginx"
        info "Dashboard reverse proxy configured (http://localhost/)"
    else
        warning "Nginx configuration test failed, skipping proxy setup"
        sudo rm -f /etc/nginx/sites-enabled/autobot-dashboard
    fi
}

# Install GPU monitoring tools (if NVIDIA GPU present)
install_gpu_monitoring() {
    log "Checking for GPU monitoring capabilities..."

    # Check for NVIDIA GPU
    if command -v nvidia-smi &> /dev/null; then
        info "NVIDIA GPU detected, GPU monitoring will be available"

        # Install nvidia-ml-py for detailed GPU monitoring
        source /home/kali/Desktop/AutoBot/venv/bin/activate
        pip install nvidia-ml-py3 > /dev/null 2>&1 || warning "Could not install nvidia-ml-py3"
        deactivate

        success "GPU monitoring tools installed"
    else
        info "No NVIDIA GPU detected, GPU monitoring will be disabled"
    fi

    # Check for Intel GPU/NPU
    if lspci | grep -i "intel.*graphics" > /dev/null; then
        info "Intel GPU detected"

        # Try to install Intel GPU tools
        if command -v intel_gpu_top &> /dev/null; then
            info "Intel GPU monitoring tools available"
        else
            warning "Intel GPU tools not found, install intel-gpu-tools for enhanced monitoring"
        fi
    fi
}

# Create monitoring scripts and utilities
create_monitoring_utilities() {
    log "Creating monitoring utility scripts..."

    # Create quick status script
    cat > /home/kali/Desktop/AutoBot/scripts/monitor-status.sh << 'EOF'
#!/bin/bash
# Quick AutoBot monitoring status check

echo "🤖 AutoBot Performance Monitoring Status"
echo "========================================"

# Check if monitoring service is running
if systemctl is-active --quiet autobot-monitoring.service; then
    echo "✅ Monitoring Service: Running"
else
    echo "❌ Monitoring Service: Stopped"
fi

# Check dashboard accessibility
if curl -s http://localhost:9090 > /dev/null; then
    echo "✅ Dashboard: Accessible (http://localhost:9090)"
else
    echo "❌ Dashboard: Not accessible"
fi

# Show recent monitoring activity
echo ""
echo "📊 Recent Monitoring Activity:"
tail -5 /home/kali/Desktop/AutoBot/logs/monitoring_control.log 2>/dev/null || echo "No recent logs"

# Show system resource usage
echo ""
echo "🖥️  Current System Resources:"
echo "CPU: $(top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print 100 - $1"%"}')"
echo "Memory: $(free | grep Mem | awk '{printf("%.1f%%\n", ($3/$2) * 100.0)}')"
echo "Disk: $(df / | tail -1 | awk '{print $5}')"
EOF

    chmod +x /home/kali/Desktop/AutoBot/scripts/monitor-status.sh

    # Create benchmark runner script
    cat > /home/kali/Desktop/AutoBot/scripts/run-benchmark.sh << 'EOF'
#!/bin/bash
# AutoBot Performance Benchmark Runner

BENCHMARK_TYPE=${1:-comprehensive}
DURATION=${2:-60}

echo "🚀 Running AutoBot Performance Benchmark"
echo "Type: $BENCHMARK_TYPE"
echo "Duration: ${DURATION}s"
echo ""

cd /home/kali/Desktop/AutoBot
source venv/bin/activate

python monitoring/monitor_control.py --benchmark "$BENCHMARK_TYPE" --benchmark-duration "$DURATION"
EOF

    chmod +x /home/kali/Desktop/AutoBot/scripts/run-benchmark.sh

    # Create optimization runner script
    cat > /home/kali/Desktop/AutoBot/scripts/run-optimization.sh << 'EOF'
#!/bin/bash
# AutoBot Performance Optimization Runner

echo "🔧 Running AutoBot Performance Optimization"
echo ""

cd /home/kali/Desktop/AutoBot
source venv/bin/activate

python monitoring/monitor_control.py --optimize-once
EOF

    chmod +x /home/kali/Desktop/AutoBot/scripts/run-optimization.sh

    success "Monitoring utility scripts created"
}

# Validate installation
validate_installation() {
    log "Validating installation..."

    # Check if monitoring files exist
    REQUIRED_FILES=(
        "/home/kali/Desktop/AutoBot/monitoring/performance_monitor.py"
        "/home/kali/Desktop/AutoBot/monitoring/performance_dashboard.py"
        "/home/kali/Desktop/AutoBot/monitoring/performance_optimizer.py"
        "/home/kali/Desktop/AutoBot/monitoring/performance_benchmark.py"
        "/home/kali/Desktop/AutoBot/monitoring/monitor_control.py"
        "/home/kali/Desktop/AutoBot/monitoring/monitoring_config.yaml"
    )

    for file in "${REQUIRED_FILES[@]}"; do
        if [[ ! -f "$file" ]]; then
            error "Required file missing: $file"
            return 1
        fi
    done

    # Test Python imports
    source /home/kali/Desktop/AutoBot/venv/bin/activate

    if ! python -c "import redis, aiohttp, psutil, numpy, matplotlib, yaml" > /dev/null 2>&1; then
        error "Python dependency validation failed"
        deactivate
        return 1
    fi

    deactivate

    # Test monitoring service
    if ! sudo systemctl is-enabled autobot-monitoring.service > /dev/null; then
        error "Monitoring service is not enabled"
        return 1
    fi

    success "Installation validation passed"
    return 0
}

# Main installation function
main() {
    echo -e "${GREEN}🤖 AutoBot Performance Monitoring Installation${NC}"
    echo "=============================================="
    echo ""
    echo "This script will install and configure the comprehensive"
    echo "performance monitoring system for AutoBot's distributed"
    echo "infrastructure across 6 VMs."
    echo ""

    # Confirm installation
    read -p "Continue with installation? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 0
    fi

    # Check permissions
    check_permissions

    # Install components
    check_system_requirements
    install_system_dependencies
    install_python_dependencies
    setup_directories
    configure_system_monitoring
    install_monitoring_service
    configure_dashboard_proxy
    install_gpu_monitoring
    create_monitoring_utilities

    # Validate installation
    if validate_installation; then
        echo ""
        echo -e "${GREEN}🎉 Installation Complete!${NC}"
        echo "=============================================="
        echo ""
        echo "AutoBot Performance Monitoring has been successfully installed."
        echo ""
        echo "📋 What's Installed:"
        echo "  ✅ Performance monitoring system"
        echo "  ✅ Real-time dashboard (port 9090)"
        echo "  ✅ Automatic optimization engine"
        echo "  ✅ Comprehensive benchmarking suite"
        echo "  ✅ Distributed system monitoring (6 VMs)"
        echo "  ✅ Hardware acceleration monitoring"
        echo "  ✅ Systemd service integration"
        echo ""
        echo "🚀 Quick Start Commands:"
        echo "  Start monitoring: sudo systemctl start autobot-monitoring"
        echo "  Check status: bash scripts/monitor-status.sh"
        echo "  Run benchmark: bash scripts/run-benchmark.sh"
        echo "  Manual control: autobot-monitor --help"
        echo ""
        echo "📊 Dashboard Access:"
        echo "  Direct: http://localhost:9090"
        echo "  Nginx proxy: http://localhost (if configured)"
        echo ""
        echo "📂 Key Locations:"
        echo "  Configuration: /home/kali/Desktop/AutoBot/monitoring/monitoring_config.yaml"
        echo "  Logs: /home/kali/Desktop/AutoBot/logs/"
        echo "  Scripts: /home/kali/Desktop/AutoBot/scripts/"
        echo ""
        echo "⚠️  Next Steps:"
        echo "  1. Review configuration in monitoring_config.yaml"
        echo "  2. Start the monitoring service: sudo systemctl start autobot-monitoring"
        echo "  3. Access the dashboard at http://localhost:9090"
        echo "  4. Run initial benchmark: bash scripts/run-benchmark.sh comprehensive"
        echo ""

        # Offer to start service
        read -p "Start AutoBot monitoring service now? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            sudo systemctl start autobot-monitoring.service
            sleep 3

            if systemctl is-active --quiet autobot-monitoring.service; then
                success "AutoBot monitoring service started successfully!"
                echo ""
                echo "🌐 Dashboard should be available at: http://localhost:9090"
                echo "📊 Check status with: bash scripts/monitor-status.sh"
            else
                warning "Service started but may not be running correctly"
                echo "Check logs with: journalctl -u autobot-monitoring.service -f"
            fi
        fi

    else
        error "Installation validation failed"
        exit 1
    fi
}

# Handle script interruption
trap 'echo -e "\n${YELLOW}Installation interrupted${NC}"; exit 1' INT TERM

# Run main installation
main "$@"
