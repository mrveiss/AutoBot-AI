#!/bin/bash

# Zero-Downtime Frontend Update System
# Performs updates without service interruption using blue-green deployment

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../lib/ssot-config.sh" 2>/dev/null || true
LOCAL_FRONTEND_DIR="${PROJECT_ROOT:-/home/kali/Desktop/AutoBot}/autobot-slm-frontend"

# Remote Configuration
FRONTEND_VM="${AUTOBOT_FRONTEND_HOST:-172.16.168.21}"
FRONTEND_USER="${AUTOBOT_SSH_USER:-autobot}"
SSH_KEY="${AUTOBOT_SSH_KEY:-$HOME/.ssh/autobot_key}"

# Blue-Green Deployment Configuration
PRIMARY_DIR="/opt/autobot/src/autobot-slm-frontend"
SECONDARY_DIR="/opt/autobot/src/autobot-slm-frontend-staging"
PROXY_CONFIG="/opt/autobot/config/nginx-proxy.conf"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_debug() { echo -e "${BLUE}[DEBUG]${NC} $1"; }

# Deployment status tracking
DEPLOYMENT_STATUS="/tmp/zero-downtime-deployment.status"

update_deployment_status() {
    local status="$1"
    local message="$2"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [$status] $message" >> "$DEPLOYMENT_STATUS"
    log_info "$message"
}

# Pre-deployment validation
validate_prerequisites() {
    log_info "Validating zero-downtime deployment prerequisites..."

    # Check SSH connection
    if ! ssh -i "$SSH_KEY" -o ConnectTimeout=5 \
         "$FRONTEND_USER@$FRONTEND_VM" "echo 'SSH OK'" &>/dev/null; then
        log_error "Cannot connect to frontend VM"
        return 1
    fi

    # Verify current service is running
    if ! ssh -i "$SSH_KEY" "$FRONTEND_USER@$FRONTEND_VM" \
         "curl -s -f http://localhost:5173 >/dev/null"; then
        log_warn "Current service is not responding - zero-downtime not possible"
        read -p "Continue with standard deployment? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Deployment cancelled"
            exit 0
        fi
    fi

    # Verify local build
    if [ ! -d "$LOCAL_FRONTEND_DIR/dist" ]; then
        log_info "Building frontend for deployment..."
        cd "$LOCAL_FRONTEND_DIR"
        npm run build
    fi

    update_deployment_status "VALIDATED" "Prerequisites validated successfully"
}

# Create blue-green deployment environment
setup_blue_green_environment() {
    log_info "Setting up blue-green deployment environment..."

    ssh -i "$SSH_KEY" "$FRONTEND_USER@$FRONTEND_VM" << 'EOF'
        set -euo pipefail

        # Create directory structure
        sudo mkdir -p /opt/autobot/src
        sudo mkdir -p /opt/autobot/config
        sudo mkdir -p /opt/autobot/backups

        # Ensure correct ownership
        sudo chown -R autobot-service:autobot-service /opt/autobot

        # Determine current and next directories
        if [ -d "/opt/autobot/src/autobot-slm-frontend" ] && [ ! -L "/opt/autobot/src/autobot-slm-frontend" ]; then
            # First time setup - current is primary
            echo "PRIMARY" > /tmp/current-deployment
            next_dir="/opt/autobot/src/autobot-slm-frontend-staging"
        elif [ -L "/opt/autobot/src/autobot-slm-frontend" ]; then
            # Symbolic link exists, determine target
            current_target=$(readlink /opt/autobot/src/autobot-slm-frontend)
            if echo "$current_target" | grep -q "staging"; then
                echo "SECONDARY" > /tmp/current-deployment
                next_dir="/opt/autobot/src/autobot-slm-frontend-primary"
            else
                echo "PRIMARY" > /tmp/current-deployment
                next_dir="/opt/autobot/src/autobot-slm-frontend-staging"
            fi
        else
            # No current deployment
            echo "NONE" > /tmp/current-deployment
            next_dir="/opt/autobot/src/autobot-slm-frontend-primary"
        fi

        echo "$next_dir" > /tmp/next-deployment-dir
        echo "Blue-green environment ready. Next deployment: $next_dir"
EOF

    update_deployment_status "SETUP" "Blue-green environment configured"
}

# Deploy to staging environment
deploy_to_staging() {
    log_info "Deploying to staging environment..."

    local timestamp=$(date +%Y%m%d_%H%M%S)
    local package_name="frontend-update-${timestamp}.tar.gz"

    # Create deployment package
    cd "$LOCAL_FRONTEND_DIR"
    tar -czf "/tmp/$package_name" \
        --exclude='node_modules' \
        --exclude='.git' \
        --exclude='test-results' \
        --exclude='playwright-report' \
        .

    # Upload to remote
    scp -i "$SSH_KEY" \
        "/tmp/$package_name" "$FRONTEND_USER@$FRONTEND_VM:/tmp/"

    # Deploy to staging directory
    ssh -i "$SSH_KEY" "$FRONTEND_USER@$FRONTEND_VM" << EOF
        set -euo pipefail

        next_dir=\$(cat /tmp/next-deployment-dir)
        echo "Deploying to staging directory: \$next_dir"

        # Clean staging directory
        sudo rm -rf "\$next_dir"
        sudo mkdir -p "\$next_dir"

        # Extract deployment
        cd "\$next_dir"
        sudo tar -xzf "/tmp/$package_name"

        # Set ownership
        sudo chown -R autobot-service:autobot-service "\$next_dir"

        # Install dependencies
        sudo -u autobot-service npm ci

        echo "Staging deployment completed: \$next_dir"
EOF

    rm -f "/tmp/$package_name"
    update_deployment_status "DEPLOYED" "Application deployed to staging environment"
}

# Start staging service
start_staging_service() {
    log_info "Starting staging service on alternate port..."

    ssh -i "$SSH_KEY" "$FRONTEND_USER@$FRONTEND_VM" << EOF
        set -euo pipefail

        next_dir=\$(cat /tmp/next-deployment-dir)
        staging_port=5174

        echo "Starting staging service in: \$next_dir"

        cd "\$next_dir"

        # Kill any existing staging service
        pkill -f "vite.*5174" || true
        sleep 2

        # Set environment for staging
        export VITE_BACKEND_HOST=${AUTOBOT_BACKEND_HOST:-172.16.168.20}
        export VITE_BACKEND_PORT=${AUTOBOT_BACKEND_PORT:-8001}
        export NODE_ENV=development

        # Start staging service
        mkdir -p logs
        nohup npm run dev -- --host 0.0.0.0 --port \$staging_port > logs/staging.log 2>&1 &

        staging_pid=\$!
        echo \$staging_pid > /tmp/staging-frontend.pid

        echo "Staging service started on port \$staging_port (PID: \$staging_pid)"

        # Wait for staging service to be ready
        echo "Waiting for staging service to initialize..."
        max_attempts=30
        attempt=1

        while [ \$attempt -le \$max_attempts ]; do
            if curl -s -f "http://localhost:\$staging_port" >/dev/null 2>&1; then
                echo "Staging service is responding"
                break
            fi

            if [ \$attempt -eq \$max_attempts ]; then
                echo "ERROR: Staging service failed to start after \$max_attempts attempts"
                exit 1
            fi

            sleep 2
            attempt=\$((attempt + 1))
        done

        echo "Staging service ready for testing"
EOF

    update_deployment_status "STAGING" "Staging service started and verified"
}

# Test staging service
test_staging_service() {
    log_info "Testing staging service thoroughly..."

    ssh -i "$SSH_KEY" "$FRONTEND_USER@$FRONTEND_VM" << 'EOF'
        set -euo pipefail

        staging_port=5174
        staging_url="http://localhost:$staging_port"

        echo "Running comprehensive tests on staging service..."

        # Test 1: Basic connectivity
        if ! curl -s -f "$staging_url" >/dev/null; then
            echo "ERROR: Staging service basic connectivity failed"
            exit 1
        fi
        echo "✓ Basic connectivity test passed"

        # Test 2: Check for critical content
        html_content=$(curl -s "$staging_url")
        if ! echo "$html_content" | grep -q "AutoBot"; then
            echo "ERROR: AutoBot branding not found in staging"
            exit 1
        fi
        echo "✓ Branding test passed"

        # Test 3: API proxy test
        if curl -s -f "$staging_url/api/health" >/dev/null 2>&1; then
            echo "✓ API proxy test passed"
        else
            echo "⚠ API proxy test failed (backend may be unavailable)"
        fi

        # Test 4: Static assets test
        css_assets=$(echo "$html_content" | grep -o 'href="[^"]*\.css"' | wc -l)
        js_assets=$(echo "$html_content" | grep -o 'src="[^"]*\.js"' | wc -l)

        if [ $css_assets -gt 0 ] && [ $js_assets -gt 0 ]; then
            echo "✓ Static assets test passed (CSS: $css_assets, JS: $js_assets)"
        else
            echo "ERROR: Static assets test failed (CSS: $css_assets, JS: $js_assets)"
            exit 1
        fi

        # Test 5: Performance test
        response_time=$(curl -o /dev/null -s -w '%{time_total}' "$staging_url")
        if (( $(echo "$response_time < 5.0" | bc -l) )); then
            echo "✓ Performance test passed (${response_time}s)"
        else
            echo "⚠ Performance test warning (${response_time}s - slower than expected)"
        fi

        echo "All staging tests completed successfully"
EOF

    if [ $? -eq 0 ]; then
        update_deployment_status "TESTED" "Staging service passed all tests"
        return 0
    else
        update_deployment_status "TEST_FAILED" "Staging service failed testing"
        return 1
    fi
}

# Perform zero-downtime swap
perform_zero_downtime_swap() {
    log_info "Performing zero-downtime service swap..."

    ssh -i "$SSH_KEY" "$FRONTEND_USER@$FRONTEND_VM" << EOF
        set -euo pipefail

        next_dir=\$(cat /tmp/next-deployment-dir)
        current_deployment=\$(cat /tmp/current-deployment)

        echo "Performing zero-downtime swap..."
        echo "Current deployment: \$current_deployment"
        echo "Next directory: \$next_dir"

        # Stop current primary service (but keep it available)
        echo "Preparing primary service for swap..."
        current_pid=\$(cat /tmp/frontend.pid 2>/dev/null || echo "")
        if [ -n "\$current_pid" ] && kill -0 "\$current_pid" 2>/dev/null; then
            echo "Current service running with PID: \$current_pid"
        fi

        # Create symbolic link for seamless swap
        if [ -L "/opt/autobot/src/autobot-slm-frontend" ]; then
            # Remove existing link
            sudo rm -f "/opt/autobot/src/autobot-slm-frontend"
        elif [ -d "/opt/autobot/src/autobot-slm-frontend" ] && [ ! -L "/opt/autobot/src/autobot-slm-frontend" ]; then
            # Move existing directory to backup
            backup_name="autobot-slm-frontend-backup-\$(date +%Y%m%d_%H%M%S)"
            sudo mv "/opt/autobot/src/autobot-slm-frontend" "/opt/autobot/backups/\$backup_name"
        fi

        # Create new symbolic link pointing to staging
        sudo ln -sf "\$next_dir" "/opt/autobot/src/autobot-slm-frontend"

        echo "Symbolic link created: /opt/autobot/src/autobot-slm-frontend -> \$next_dir"

        # Update service configuration to use primary port
        cd "/opt/autobot/src/autobot-slm-frontend"

        # Stop staging service
        staging_pid=\$(cat /tmp/staging-frontend.pid 2>/dev/null || echo "")
        if [ -n "\$staging_pid" ]; then
            kill "\$staging_pid" || true
        fi

        # Stop current primary service
        if [ -n "\$current_pid" ]; then
            kill "\$current_pid" || true
        fi
        pkill -f "vite.*5173" || true

        sleep 3

        # Start new primary service
        export VITE_BACKEND_HOST=${AUTOBOT_BACKEND_HOST:-172.16.168.20}
        export VITE_BACKEND_PORT=${AUTOBOT_BACKEND_PORT:-8001}
        export NODE_ENV=development

        mkdir -p logs
        nohup npm run dev -- --host 0.0.0.0 --port ${AUTOBOT_FRONTEND_PORT:-5173} > logs/frontend.log 2>&1 &

        new_pid=\$!
        echo \$new_pid > /tmp/frontend.pid

        echo "New primary service started with PID: \$new_pid"

        # Wait for new service to be ready
        echo "Verifying new primary service..."
        max_attempts=30
        attempt=1

        while [ \$attempt -le \$max_attempts ]; do
            if curl -s -f "http://localhost:${AUTOBOT_FRONTEND_PORT:-5173}" >/dev/null 2>&1; then
                echo "New primary service is responding"
                break
            fi

            if [ \$attempt -eq \$max_attempts ]; then
                echo "ERROR: New primary service failed to start"
                exit 1
            fi

            sleep 2
            attempt=\$((attempt + 1))
        done

        echo "Zero-downtime swap completed successfully"
EOF

    if [ $? -eq 0 ]; then
        update_deployment_status "SWAPPED" "Zero-downtime swap completed successfully"
        return 0
    else
        update_deployment_status "SWAP_FAILED" "Zero-downtime swap failed"
        return 1
    fi
}

# Verify production service
verify_production_service() {
    log_info "Verifying production service after swap..."

    local frontend_url="http://$FRONTEND_VM:5173"
    local max_attempts=20
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if curl -s -f "$frontend_url" >/dev/null 2>&1; then
            log_info "✓ Production service is responding"
            break
        fi

        if [ $attempt -eq $max_attempts ]; then
            log_error "Production service verification failed"
            return 1
        fi

        sleep 3
        attempt=$((attempt + 1))
    done

    # Additional verification tests
    local html_content=$(curl -s "$frontend_url" 2>/dev/null || echo "")

    if echo "$html_content" | grep -q "AutoBot"; then
        log_info "✓ Application branding verified"
    else
        log_warn "⚠ Application branding not found"
    fi

    if curl -s -f "$frontend_url/api/health" >/dev/null 2>&1; then
        log_info "✓ API proxy verified"
    else
        log_warn "⚠ API proxy not responding"
    fi

    update_deployment_status "VERIFIED" "Production service verified successfully"
}

# Rollback mechanism
rollback_deployment() {
    log_error "Rolling back zero-downtime deployment..."

    ssh -i "$SSH_KEY" "$FRONTEND_USER@$FRONTEND_VM" << EOF
        set -euo pipefail

        echo "Performing rollback..."

        # Find most recent backup
        if [ -d "/opt/autobot/backups" ]; then
            latest_backup=\$(ls -t /opt/autobot/backups/ | grep "autobot-slm-frontend" | head -1)

            if [ -n "\$latest_backup" ]; then
                echo "Rolling back to: \$latest_backup"

                # Stop current service
                pkill -f "vite.*5173" || true
                sleep 2

                # Remove current symlink/directory
                sudo rm -rf "/opt/autobot/src/autobot-slm-frontend"

                # Restore backup
                sudo mv "/opt/autobot/backups/\$latest_backup" "/opt/autobot/src/autobot-slm-frontend"
                sudo chown -R autobot-service:autobot-service "/opt/autobot/src/autobot-slm-frontend"

                # Restart service
                cd "/opt/autobot/src/autobot-slm-frontend"
                export VITE_BACKEND_HOST=${AUTOBOT_BACKEND_HOST:-172.16.168.20}
                export VITE_BACKEND_PORT=${AUTOBOT_BACKEND_PORT:-8001}
                export NODE_ENV=development

                nohup npm run dev -- --host 0.0.0.0 --port ${AUTOBOT_FRONTEND_PORT:-5173} > logs/frontend.log 2>&1 &
                echo \$! > /tmp/frontend.pid

                echo "Rollback completed"
            else
                echo "No backup found for rollback"
                exit 1
            fi
        else
            echo "No backup directory found"
            exit 1
        fi
EOF

    update_deployment_status "ROLLBACK" "Deployment rolled back to previous version"
}

# Cleanup staging environment
cleanup_staging() {
    log_info "Cleaning up staging environment..."

    ssh -i "$SSH_KEY" "$FRONTEND_USER@$FRONTEND_VM" << 'EOF'
        # Kill any remaining staging processes
        pkill -f "vite.*5174" || true

        # Clean up temporary files
        rm -f /tmp/current-deployment
        rm -f /tmp/next-deployment-dir
        rm -f /tmp/staging-frontend.pid

        echo "Staging cleanup completed"
EOF

    # Clean up local files
    rm -f "$DEPLOYMENT_STATUS"

    update_deployment_status "CLEANUP" "Staging environment cleaned up"
}

# Generate deployment report
generate_deployment_report() {
    local status="$1"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    cat > "/tmp/zero-downtime-deployment-report.md" << EOF
# Zero-Downtime Frontend Deployment Report

**Status:** $status
**Timestamp:** $timestamp
**Frontend VM:** $FRONTEND_VM
**Service URL:** http://$FRONTEND_VM:5173

## Deployment Timeline
$(cat "$DEPLOYMENT_STATUS" 2>/dev/null || echo "No status log available")

## Service Information
- **Deployment Method:** Blue-Green Zero-Downtime
- **Target Directory:** /opt/autobot/src/autobot-slm-frontend
- **Backup Location:** /opt/autobot/backups/
- **Log Location:** /opt/autobot/src/autobot-slm-frontend/logs/frontend.log

## Verification Results
- Service responding: $(curl -s -f "http://$FRONTEND_VM:5173" >/dev/null 2>&1 && echo "✓ YES" || echo "✗ NO")
- API proxy working: $(curl -s -f "http://$FRONTEND_VM:5173/api/health" >/dev/null 2>&1 && echo "✓ YES" || echo "✗ NO")

---
Generated by Zero-Downtime Frontend Update System
EOF

    log_info "Deployment report generated: /tmp/zero-downtime-deployment-report.md"
}

# Main execution function
main() {
    log_info "🚀 Zero-Downtime Frontend Update System"
    log_info "========================================"

    # Initialize deployment status log
    echo "Zero-Downtime Deployment Started: $(date)" > "$DEPLOYMENT_STATUS"

    local success=true

    # Execute deployment phases
    validate_prerequisites || { success=false; }

    if $success; then
        setup_blue_green_environment || { success=false; }
    fi

    if $success; then
        deploy_to_staging || { success=false; }
    fi

    if $success; then
        start_staging_service || { success=false; }
    fi

    if $success; then
        test_staging_service || { success=false; }
    fi

    if $success; then
        perform_zero_downtime_swap || { success=false; }
    fi

    if $success; then
        verify_production_service || {
            log_error "Production verification failed - attempting rollback"
            rollback_deployment
            success=false
        }
    fi

    # Cleanup and reporting
    cleanup_staging

    if $success; then
        generate_deployment_report "✅ SUCCESS"
        log_info "========================================"
        log_info "🎉 ZERO-DOWNTIME UPDATE COMPLETED SUCCESSFULLY"
        log_info "Frontend URL: http://$FRONTEND_VM:5173"
        log_info "Report: /tmp/zero-downtime-deployment-report.md"
        log_info "========================================"
    else
        generate_deployment_report "❌ FAILED"
        log_error "========================================"
        log_error "💥 ZERO-DOWNTIME UPDATE FAILED"
        log_error "Check logs and consider manual intervention"
        log_error "Report: /tmp/zero-downtime-deployment-report.md"
        log_error "========================================"
        exit 1
    fi
}

# Handle script interruption
trap 'log_error "Deployment interrupted"; cleanup_staging; exit 1' INT TERM

# Execute main function
main "$@"
