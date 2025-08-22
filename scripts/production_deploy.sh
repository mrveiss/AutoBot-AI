#!/bin/bash
# AutoBot Production Deployment Script
# Comprehensive production deployment with security and monitoring

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_ENV="${DEPLOY_ENV:-production}"
BACKUP_DIR="${PROJECT_ROOT}/backups/$(date +%Y%m%d_%H%M%S)"

# Logging
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
    exit 1
}

# Pre-deployment checks
pre_deployment_checks() {
    log "🔍 Running pre-deployment checks..."

    # Check Docker
    if ! command -v docker &> /dev/null; then
        error "Docker is not installed"
    fi

    if ! command -v docker-compose &> /dev/null; then
        error "Docker Compose is not installed"
    fi

    # Check required files
    required_files=(
        "docker/Dockerfile.production"
        "docker/compose/docker-compose.production.yml"
        ".dockerignore"
        "requirements.txt"
        "main.py"
    )

    for file in "${required_files[@]}"; do
        if [[ ! -f "$PROJECT_ROOT/$file" ]]; then
            error "Required file not found: $file"
        fi
    done

    # Check disk space (minimum 5GB)
    available_space=$(df "$PROJECT_ROOT" | awk 'NR==2 {print $4}')
    if [[ $available_space -lt 5242880 ]]; then
        warn "Low disk space. Available: $((available_space/1024/1024))GB"
    fi

    log "✅ Pre-deployment checks passed"
}

# Backup existing data
backup_data() {
    log "📦 Creating backup of existing data..."

    mkdir -p "$BACKUP_DIR"

    # Backup data directory
    if [[ -d "$PROJECT_ROOT/data" ]]; then
        cp -r "$PROJECT_ROOT/data" "$BACKUP_DIR/"
        log "✅ Data directory backed up"
    fi

    # Backup configuration
    if [[ -d "$PROJECT_ROOT/config" ]]; then
        cp -r "$PROJECT_ROOT/config" "$BACKUP_DIR/"
        log "✅ Configuration backed up"
    fi

    # Backup logs
    if [[ -d "$PROJECT_ROOT/logs" ]]; then
        tar -czf "$BACKUP_DIR/logs.tar.gz" -C "$PROJECT_ROOT" logs/
        log "✅ Logs archived"
    fi

    log "📦 Backup completed: $BACKUP_DIR"
}

# Generate SSL certificates for production
generate_ssl_certs() {
    log "🔐 Generating SSL certificates..."

    SSL_DIR="$PROJECT_ROOT/docker/nginx/ssl"
    mkdir -p "$SSL_DIR"

    if [[ ! -f "$SSL_DIR/autobot.crt" ]]; then
        # Generate self-signed certificate for development/testing
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout "$SSL_DIR/autobot.key" \
            -out "$SSL_DIR/autobot.crt" \
            -subj "/C=US/ST=State/L=City/O=AutoBot/OU=IT/CN=localhost"

        chmod 600 "$SSL_DIR/autobot.key"
        chmod 644 "$SSL_DIR/autobot.crt"

        log "✅ SSL certificates generated"
    else
        log "✅ SSL certificates already exist"
    fi
}

# Build and deploy containers
deploy_containers() {
    log "🚀 Building and deploying containers..."

    cd "$PROJECT_ROOT"

    # Build images
    log "Building AutoBot images..."
    docker-compose -f docker/compose/docker-compose.production.yml build --no-cache

    # Create necessary volumes and networks
    log "Creating Docker volumes and networks..."
    docker-compose -f docker/compose/docker-compose.production.yml up -d --remove-orphans

    # Wait for services to be healthy
    log "Waiting for services to become healthy..."
    for service in redis ollama autobot-backend autobot-frontend; do
        timeout=120
        while ! docker-compose -f docker/compose/docker-compose.production.yml ps "$service" | grep -q "healthy\|Up" && [[ $timeout -gt 0 ]]; do
            echo -n "."
            sleep 2
            ((timeout-=2))
        done

        if [[ $timeout -eq 0 ]]; then
            error "Service $service failed to start within timeout"
        fi

        log "✅ Service $service is running"
    done
}

# Run post-deployment tests
post_deployment_tests() {
    log "🧪 Running post-deployment tests..."

    # Health check tests
    services=(
        "http://localhost:8001/api/system/health:Backend"
        "http://localhost/health:Frontend"
        "http://localhost:6379:Redis"
        "http://localhost:11434/api/tags:Ollama"
    )

    for service_info in "${services[@]}"; do
        IFS=':' read -r url name <<< "$service_info"

        if curl -f -s "$url" > /dev/null; then
            log "✅ $name health check passed"
        else
            error "$name health check failed"
        fi
    done

    # Run phase validation
    if [[ -f "$PROJECT_ROOT/scripts/phase_validation_system.py" ]]; then
        log "Running comprehensive system validation..."
        if python "$PROJECT_ROOT/scripts/phase_validation_system.py"; then
            log "✅ System validation passed"
        else
            warn "System validation found issues - check logs"
        fi
    fi
}

# Setup monitoring and alerting
setup_monitoring() {
    log "📊 Setting up monitoring and alerting..."

    # Deploy monitoring stack if requested
    if [[ "${ENABLE_MONITORING:-true}" == "true" ]]; then
        docker-compose -f docker/compose/docker-compose.production.yml --profile monitoring up -d

        # Wait for monitoring services
        sleep 10

        # Check Prometheus
        if curl -f -s "http://localhost:9090/-/healthy" > /dev/null; then
            log "✅ Prometheus is running"
        else
            warn "Prometheus health check failed"
        fi

        # Check Grafana
        if curl -f -s "http://localhost:3000/api/health" > /dev/null; then
            log "✅ Grafana is running"
        else
            warn "Grafana health check failed"
        fi
    fi
}

# Display deployment summary
deployment_summary() {
    log "🎉 Deployment completed successfully!"

    echo ""
    echo -e "${BLUE}📊 AutoBot Production Deployment Summary${NC}"
    echo "=============================================="
    echo ""
    echo -e "${GREEN}✅ Services Running:${NC}"
    echo "  • Backend API: http://localhost:8001"
    echo "  • Frontend: http://localhost (HTTP) / https://localhost (HTTPS)"
    echo "  • Redis: localhost:6379"
    echo "  • Ollama LLM: http://localhost:11434"

    if [[ "${ENABLE_MONITORING:-true}" == "true" ]]; then
        echo ""
        echo -e "${GREEN}📊 Monitoring Services:${NC}"
        echo "  • Prometheus: http://localhost:9090"
        echo "  • Grafana: http://localhost:3000 (admin/autobot123)"
    fi

    echo ""
    echo -e "${GREEN}📁 Important Paths:${NC}"
    echo "  • Data: $PROJECT_ROOT/data"
    echo "  • Logs: $PROJECT_ROOT/logs"
    echo "  • Config: $PROJECT_ROOT/config"
    echo "  • Backup: $BACKUP_DIR"

    echo ""
    echo -e "${GREEN}🔧 Management Commands:${NC}"
    echo "  • View logs: docker-compose -f docker/compose/docker-compose.production.yml logs -f"
    echo "  • Stop services: docker-compose -f docker/compose/docker-compose.production.yml down"
    echo "  • Update services: docker-compose -f docker/compose/docker-compose.production.yml pull && docker-compose -f docker/compose/docker-compose.production.yml up -d"
    echo "  • System validation: python scripts/phase_validation_system.py"

    echo ""
    echo -e "${YELLOW}⚠️  Next Steps:${NC}"
    echo "  1. Configure proper SSL certificates for production"
    echo "  2. Set up external monitoring and backup systems"
    echo "  3. Configure firewall rules for your environment"
    echo "  4. Review and update security settings"

    echo ""
}

# Cleanup on exit
cleanup() {
    if [[ $? -ne 0 ]]; then
        error "Deployment failed. Check logs above for details."
        echo "Rollback: docker-compose -f docker/compose/docker-compose.production.yml down && rm -f docker-compose.override.yml"
    fi
}

trap cleanup EXIT

# Main deployment flow
main() {
    log "🚀 Starting AutoBot Production Deployment"
    log "Environment: $DEPLOY_ENV"
    log "Project Root: $PROJECT_ROOT"

    pre_deployment_checks
    backup_data
    generate_ssl_certs
    deploy_containers
    post_deployment_tests
    setup_monitoring
    deployment_summary

    log "🎯 AutoBot is now running in production mode!"
}

# Script entry point
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
