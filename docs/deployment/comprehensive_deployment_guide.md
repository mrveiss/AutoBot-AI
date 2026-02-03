# AutoBot Comprehensive Deployment Guide

Complete deployment guide for AutoBot across different environments, from development to production, including Docker, cloud platforms, and enterprise deployments.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Development Environment](#development-environment)
- [Production Environment](#production-environment)
- [Docker Deployment](#docker-deployment)
- [Cloud Deployments](#cloud-deployments)
- [Enterprise Deployment](#enterprise-deployment)
- [Security Configuration](#security-configuration)
- [Monitoring & Maintenance](#monitoring--maintenance)
- [Troubleshooting](#troubleshooting)

## Overview

AutoBot can be deployed in various configurations depending on your needs:

| Deployment Type | Use Case | Complexity | Scalability |
|----------------|----------|------------|-------------|
| Development | Local development, testing | Low | Single user |
| Standalone | Small teams, prototyping | Medium | 5-10 users |
| Docker | Containerized deployment | Medium | 10-50 users |
| Cloud | Scalable cloud deployment | High | 50+ users |
| Enterprise | Large organizations | Very High | 1000+ users |

### Architecture Components

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │    Backend      │    │   AI Services   │
│   (Vue.js)      │◄──►│   (FastAPI)     │◄──►│   (Ollama/LLM)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Web Server    │    │   Database      │    │   Redis Cache   │
│   (Nginx)       │    │   (SQLite/PG)   │    │   (Memory)      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Prerequisites

### System Requirements

#### Minimum Requirements
- **CPU**: 4 cores, 2.0 GHz
- **RAM**: 8 GB
- **Storage**: 50 GB available space
- **OS**: Ubuntu 20.04+, CentOS 8+, Windows 10+, macOS 10.15+

#### Recommended Requirements
- **CPU**: 8+ cores, 3.0 GHz (Intel/AMD)
- **RAM**: 16+ GB
- **Storage**: 100+ GB SSD
- **GPU**: Optional (NVIDIA RTX series for acceleration)
- **NPU**: Intel Arc or newer (for NPU acceleration)

### Software Dependencies

#### Core Dependencies
```bash
# Python 3.10+
python3 --version  # Should be 3.10 or higher

# Node.js 18+
node --version     # Should be 18.0.0 or higher
npm --version      # Should be 9.0.0 or higher

# Docker (optional but recommended)
docker --version   # Should be 20.0.0 or higher
docker-compose --version  # Should be 2.0.0 or higher
```

#### Optional Dependencies
```bash
# Redis (for enhanced performance)
redis-server --version

# PostgreSQL (for production databases)
psql --version

# Nginx (for production web serving)
nginx -v

# Git (for deployment from repository)
git --version
```

## Quick Start

### One-Command Deployment

```bash
# Clone and deploy AutoBot in one command
curl -fsSL https://raw.githubusercontent.com/your-org/autobot/main/scripts/quick-deploy.sh | bash
```

This script will:
1. Check system requirements
2. Install dependencies
3. Configure AutoBot
4. Start all services
5. Open browser to localhost:5173

### Manual Quick Start

```bash
# 1. Clone repository
git clone https://github.com/your-org/autobot.git
cd autobot

# 2. Run setup script
./scripts/setup/setup_agent.sh

# 3. Start AutoBot
./run_agent.sh

# 4. Access AutoBot
# Frontend: http://localhost:5173
# Backend API: http://localhost:8001
# API Documentation: http://localhost:8001/docs
```

## Development Environment

### Local Development Setup

#### 1. Environment Setup
```bash
# Create development environment
git clone https://github.com/your-org/autobot.git
cd autobot

# Create Python virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

# Install Node.js dependencies
cd autobot-vue
npm install
cd ..
```

#### 2. Configuration
```bash
# Copy example configuration
cp config/config.example.yaml config/config.yaml

# Edit configuration for development
nano config/config.yaml
```

**Development Configuration (`config/config.yaml`)**:
```yaml
# Development Configuration
backend:
  server_host: "0.0.0.0"
  server_port: 8001
  debug: true
  reload: true
  cors_origins:
    - "http://localhost:5173"
    - "http://127.0.0.1:5173"

llm_config:
  orchestrator_llm: "ollama_llama3.2:3b"
  default_llm: "ollama_llama3.2:1b"

memory:
  redis:
    enabled: false  # Use in-memory for development
  database_path: "data/autobot_dev.db"

logging:
  log_level: "DEBUG"
  log_to_file: true
  log_file_path: "logs/autobot_dev.log"

developer:
  enabled: true
  debug_logging: true
  enhanced_errors: true
```

#### 3. Start Development Services
```bash
# Terminal 1: Start backend with auto-reload
source venv/bin/activate
python main.py --dev

# Terminal 2: Start frontend development server
cd autobot-vue
npm run dev

# Terminal 3: Start Ollama (if using local LLM)
ollama serve
```

#### 4. Development Tools
```bash
# Code formatting
black src/ backend/ --line-length=88
isort src/ backend/

# Linting
flake8 src/ backend/ --max-line-length=88

# Testing
python -m pytest tests/ -v

# Frontend testing
cd autobot-vue
npm run test:unit
npm run test:playwright
```

### Development Workflow

#### 1. Code Changes
```bash
# Backend changes - automatic reload enabled
echo "Backend will auto-reload on file changes"

# Frontend changes - automatic reload with HMR
echo "Frontend will hot-reload on file changes"

# Database changes - run migrations
python scripts/migrate_database.py
```

#### 2. Testing Changes
```bash
# Run specific tests
python -m pytest tests/test_specific_feature.py -v

# Run integration tests
python -m pytest tests/integration/ -v

# Run frontend tests
cd autobot-vue
npm run test:unit -- --watch
```

#### 3. Debugging
```bash
# Backend debugging with verbose logs
export AUTOBOT_LOG_LEVEL=DEBUG
python main.py --dev

# Frontend debugging
cd autobot-vue
npm run dev -- --debug

# Database debugging
sqlite3 data/autobot_dev.db ".schema"
```

## Production Environment

### Production Deployment

#### 1. Server Preparation
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install system dependencies
sudo apt install -y python3 python3-pip python3-venv nodejs npm nginx redis-server postgresql

# Create autobot user
sudo useradd -m -s /bin/bash autobot
sudo usermod -aG sudo autobot

# Switch to autobot user
sudo su - autobot
```

#### 2. Application Deployment
```bash
# Clone application
git clone https://github.com/your-org/autobot.git /opt/autobot
cd /opt/autobot

# Set up Python environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Build frontend
cd autobot-vue
npm ci --production
npm run build
cd ..

# Set up production configuration
cp config/config.production.yaml config/config.yaml
```

#### 3. Production Configuration
**Production Configuration (`config/config.yaml`)**:
```yaml
# Production Configuration
backend:
  server_host: "127.0.0.1"
  server_port: 8001
  debug: false
  reload: false
  workers: 4

database:
  # Use PostgreSQL for production
  type: "postgresql"
  host: "localhost"
  port: 5432
  database: "autobot_prod"
  username: "autobot_user"
  password: "${AUTOBOT_DB_PASSWORD}"

memory:
  redis:
    enabled: true
    host: "localhost"
    port: 6379
    db: 0

security:
  enable_auth: true
  enable_command_security: true
  use_docker_sandbox: true
  secret_key: "${AUTOBOT_SECRET_KEY}"

logging:
  log_level: "INFO"
  log_to_file: true
  log_file_path: "/var/log/autobot/autobot.log"
```

#### 4. Database Setup
```bash
# PostgreSQL setup
sudo -u postgres createuser autobot_user
sudo -u postgres createdb autobot_prod -O autobot_user
sudo -u postgres psql -c "ALTER USER autobot_user PASSWORD 'secure_password';"

# Run database migrations
export AUTOBOT_DB_PASSWORD="secure_password"
python scripts/migrate_database.py --production
```

#### 5. System Services
**Backend Service (`/etc/systemd/system/autobot-backend.service`)**:
```ini
[Unit]
Description=AutoBot Backend Service
After=network.target postgresql.service redis.service

[Service]
Type=exec
User=autobot
Group=autobot
WorkingDirectory=/opt/autobot
Environment=PATH=/opt/autobot/venv/bin
Environment=AUTOBOT_DB_PASSWORD=secure_password
Environment=AUTOBOT_SECRET_KEY=your_secret_key_here
ExecStart=/opt/autobot/venv/bin/python main.py --production
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Frontend Service (Nginx Configuration `/etc/nginx/sites-available/autobot`)**:
```nginx
server {
    listen 80;
    server_name your-domain.com;

    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";

    # Frontend static files
    location / {
        root /opt/autobot/autobot-vue/dist;
        try_files $uri $uri/ /index.html;

        # Caching for static assets
        location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }

    # Backend API proxy
    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # WebSocket endpoints
    location /api/chat/ws {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

#### 6. Start Production Services
```bash
# Enable and start services
sudo systemctl daemon-reload
sudo systemctl enable autobot-backend
sudo systemctl start autobot-backend

# Enable Nginx
sudo ln -s /etc/nginx/sites-available/autobot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# Check service status
sudo systemctl status autobot-backend
sudo systemctl status nginx
```

## Docker Deployment

### Docker Compose Deployment

#### 1. Docker Compose Configuration
**`docker-compose.prod.yml`**:
```yaml
version: '3.8'

services:
  autobot-backend:
    build:
      context: .
      dockerfile: docker/Dockerfile.backend
    container_name: autobot-backend
    restart: unless-stopped
    ports:
      - "8001:8001"
    environment:
      - AUTOBOT_ENV=production
      - AUTOBOT_DB_HOST=postgres
      - AUTOBOT_REDIS_HOST=redis
      - AUTOBOT_SECRET_KEY=${AUTOBOT_SECRET_KEY}
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./config:/app/config
    depends_on:
      - postgres
      - redis
    networks:
      - autobot-network

  autobot-frontend:
    build:
      context: ./autobot-vue
      dockerfile: Dockerfile
    container_name: autobot-frontend
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - autobot-backend
    networks:
      - autobot-network

  postgres:
    image: postgres:15
    container_name: autobot-postgres
    restart: unless-stopped
    environment:
      - POSTGRES_DB=autobot
      - POSTGRES_USER=autobot
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./scripts/db/init.sql:/docker-entrypoint-initdb.d/init.sql
    networks:
      - autobot-network

  redis:
    image: redis:7-alpine
    container_name: autobot-redis
    restart: unless-stopped
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    networks:
      - autobot-network

  ollama:
    image: ollama/ollama:latest
    container_name: autobot-ollama
    restart: unless-stopped
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    environment:
      - OLLAMA_HOST=0.0.0.0
    networks:
      - autobot-network

  # NPU Worker (optional, for Intel NPU support)
  npu-worker:
    build:
      context: ./docker/npu-worker
      dockerfile: Dockerfile
    container_name: autobot-npu-worker
    restart: unless-stopped
    environment:
      - AUTOBOT_BACKEND_URL=http://autobot-backend:8001
    devices:
      - /dev/dri:/dev/dri  # Intel GPU/NPU access
    volumes:
      - ./models:/app/models
    networks:
      - autobot-network
    profiles:
      - npu

volumes:
  postgres_data:
  redis_data:
  ollama_data:

networks:
  autobot-network:
    driver: bridge
```

#### 2. Environment Configuration
**`.env.production`**:
```bash
# Database
POSTGRES_PASSWORD=secure_database_password_here

# AutoBot
AUTOBOT_SECRET_KEY=your_very_secure_secret_key_here
AUTOBOT_ENV=production

# Optional: External services
OPENAI_API_KEY=your_openai_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
```

#### 3. Deploy with Docker Compose
```bash
# Set up environment
cp .env.example .env.production
nano .env.production  # Edit with your values

# Build and start services
docker-compose -f docker-compose.prod.yml --env-file .env.production up -d

# Check service status
docker-compose -f docker-compose.prod.yml ps

# View logs
docker-compose -f docker-compose.prod.yml logs -f autobot-backend

# Initialize database
docker-compose -f docker-compose.prod.yml exec autobot-backend python scripts/migrate_database.py

# Set up initial admin user
docker-compose -f docker-compose.prod.yml exec autobot-backend python scripts/create_admin_user.py
```

#### 4. Docker Health Checks
```bash
# Check container health
docker ps --filter "name=autobot" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# View detailed container info
docker inspect autobot-backend

# Check resource usage
docker stats autobot-backend autobot-frontend

# Test API connectivity
curl http://localhost:8001/api/system/health
```

### Docker Swarm Deployment

#### 1. Swarm Configuration
```bash
# Initialize Docker Swarm
docker swarm init

# Deploy AutoBot stack
docker stack deploy -c docker-compose.swarm.yml autobot

# Scale services
docker service scale autobot_autobot-backend=3
```

**`docker-compose.swarm.yml`**:
```yaml
version: '3.8'

services:
  autobot-backend:
    image: autobot/backend:latest
    deploy:
      replicas: 3
      update_config:
        parallelism: 1
        delay: 10s
      restart_policy:
        condition: on-failure
    # ... rest of configuration
```

## Cloud Deployments

### AWS Deployment

#### 1. AWS ECS Deployment
**Task Definition (`ecs-task-definition.json`)**:
```json
{
  "family": "autobot",
  "taskRoleArn": "arn:aws:iam::ACCOUNT:role/ecsTaskRole",
  "executionRoleArn": "arn:aws:iam::ACCOUNT:role/ecsTaskExecutionRole",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "2048",
  "memory": "4096",
  "containerDefinitions": [
    {
      "name": "autobot-backend",
      "image": "ACCOUNT.dkr.ecr.REGION.amazonaws.com/autobot:latest",
      "portMappings": [
        {
          "containerPort": 8001,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "AUTOBOT_ENV",
          "value": "production"
        }
      ],
      "secrets": [
        {
          "name": "AUTOBOT_SECRET_KEY",
          "valueFrom": "arn:aws:secretsmanager:REGION:ACCOUNT:secret:autobot/secret-key"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/autobot",
          "awslogs-region": "us-west-2",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

#### 2. AWS Infrastructure (Terraform)
**`infrastructure/aws/main.tf`**:
```hcl
provider "aws" {
  region = var.aws_region
}

# VPC and Networking
resource "aws_vpc" "autobot" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "autobot-vpc"
  }
}

# ECS Cluster
resource "aws_ecs_cluster" "autobot" {
  name = "autobot-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

# Application Load Balancer
resource "aws_lb" "autobot" {
  name               = "autobot-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets           = aws_subnet.public[*].id

  enable_deletion_protection = false
}

# RDS PostgreSQL
resource "aws_db_instance" "autobot" {
  identifier     = "autobot-db"
  engine         = "postgres"
  engine_version = "15.3"
  instance_class = "db.t3.micro"

  allocated_storage     = 20
  max_allocated_storage = 100

  db_name  = "autobot"
  username = "autobot"
  password = var.db_password

  vpc_security_group_ids = [aws_security_group.rds.id]
  db_subnet_group_name   = aws_db_subnet_group.autobot.name

  backup_retention_period = 7
  backup_window          = "03:00-04:00"
  maintenance_window     = "sun:04:00-sun:05:00"

  skip_final_snapshot = true
}

# ElastiCache Redis
resource "aws_elasticache_subnet_group" "autobot" {
  name       = "autobot-cache-subnet"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_elasticache_cluster" "autobot" {
  cluster_id           = "autobot-redis"
  engine               = "redis"
  node_type            = "cache.t3.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.autobot.name
  security_group_ids   = [aws_security_group.redis.id]
}
```

#### 3. Deploy to AWS
```bash
# Build and push Docker image
aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin ACCOUNT.dkr.ecr.us-west-2.amazonaws.com

docker build -t autobot .
docker tag autobot:latest ACCOUNT.dkr.ecr.us-west-2.amazonaws.com/autobot:latest
docker push ACCOUNT.dkr.ecr.us-west-2.amazonaws.com/autobot:latest

# Deploy infrastructure
cd infrastructure/aws
terraform init
terraform plan
terraform apply

# Deploy ECS service
aws ecs register-task-definition --cli-input-json file://ecs-task-definition.json
aws ecs create-service --cluster autobot-cluster --service-name autobot --task-definition autobot --desired-count 2
```

### Google Cloud Platform (GCP)

#### 1. GKE Deployment
**`k8s/autobot-deployment.yaml`**:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: autobot-backend
  labels:
    app: autobot-backend
spec:
  replicas: 3
  selector:
    matchLabels:
      app: autobot-backend
  template:
    metadata:
      labels:
        app: autobot-backend
    spec:
      containers:
      - name: autobot-backend
        image: gcr.io/PROJECT-ID/autobot:latest
        ports:
        - containerPort: 8001
        env:
        - name: AUTOBOT_ENV
          value: "production"
        - name: POSTGRES_HOST
          value: "postgres-service"
        - name: REDIS_HOST
          value: "redis-service"
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /api/system/health
            port: 8001
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /api/system/health
            port: 8001
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: autobot-backend-service
spec:
  selector:
    app: autobot-backend
  ports:
    - protocol: TCP
      port: 80
      targetPort: 8001
  type: LoadBalancer
```

#### 2. Deploy to GKE
```bash
# Set up GKE cluster
gcloud container clusters create autobot-cluster \
    --zone=us-central1-a \
    --num-nodes=3 \
    --machine-type=e2-standard-2

# Get credentials
gcloud container clusters get-credentials autobot-cluster --zone=us-central1-a

# Build and push image
docker build -t gcr.io/PROJECT-ID/autobot:latest .
docker push gcr.io/PROJECT-ID/autobot:latest

# Deploy to Kubernetes
kubectl apply -f k8s/
kubectl get services autobot-backend-service
```

### Azure Deployment

#### 1. Azure Container Instances
**`azure-deployment.yaml`**:
```yaml
apiVersion: 2019-12-01
location: eastus
name: autobot-container-group
properties:
  containers:
  - name: autobot-backend
    properties:
      image: autobotregistry.azurecr.io/autobot:latest
      resources:
        requests:
          cpu: 2
          memoryInGb: 4
      ports:
      - port: 8001
        protocol: TCP
  - name: postgres
    properties:
      image: postgres:15
      environmentVariables:
      - name: POSTGRES_DB
        value: autobot
      - name: POSTGRES_USER
        value: autobot
      - name: POSTGRES_PASSWORD
        secureValue: your-secure-password
      resources:
        requests:
          cpu: 1
          memoryInGb: 2
  ipAddress:
    type: Public
    ports:
    - protocol: tcp
      port: 8001
  osType: Linux
  restartPolicy: Always
```

#### 2. Deploy to Azure
```bash
# Create resource group
az group create --name autobot-rg --location eastus

# Create container registry
az acr create --resource-group autobot-rg --name autobotregistry --sku Basic

# Build and push image
az acr build --registry autobotregistry --image autobot:latest .

# Deploy container group
az container create --resource-group autobot-rg --file azure-deployment.yaml
```

## Enterprise Deployment

### High Availability Setup

#### 1. Multi-Region Architecture
```
Region 1 (Primary)          Region 2 (Secondary)
┌─────────────────┐         ┌─────────────────┐
│  Load Balancer  │◄────────┤  Load Balancer  │
└─────────────────┘         └─────────────────┘
         │                           │
┌─────────────────┐         ┌─────────────────┐
│  AutoBot Nodes  │         │  AutoBot Nodes  │
│  (3 instances)  │◄────────┤  (2 instances)  │
└─────────────────┘         └─────────────────┘
         │                           │
┌─────────────────┐         ┌─────────────────┐
│ Primary DB      │────────►│ Secondary DB    │
│ (Master)        │         │ (Read Replica)  │
└─────────────────┘         └─────────────────┘
```

#### 2. Kubernetes High Availability
**`k8s/ha-deployment.yaml`**:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: autobot-backend-ha
spec:
  replicas: 5
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 2
      maxUnavailable: 1
  selector:
    matchLabels:
      app: autobot-backend
  template:
    metadata:
      labels:
        app: autobot-backend
    spec:
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchExpressions:
                - key: app
                  operator: In
                  values:
                  - autobot-backend
              topologyKey: kubernetes.io/hostname
      containers:
      - name: autobot-backend
        image: autobot:latest
        resources:
          requests:
            memory: "2Gi"
            cpu: "1000m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
---
apiVersion: v1
kind: Service
metadata:
  name: autobot-backend-service
spec:
  selector:
    app: autobot-backend
  ports:
    - port: 80
      targetPort: 8001
  type: ClusterIP
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: autobot-ingress
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  tls:
  - hosts:
    - autobot.company.com
    secretName: autobot-tls
  rules:
  - host: autobot.company.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: autobot-backend-service
            port:
              number: 80
```

### Enterprise Security

#### 1. Network Security
```bash
# Firewall rules (iptables)
sudo iptables -A INPUT -p tcp --dport 443 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 22 -s MANAGEMENT_NETWORK -j ACCEPT
sudo iptables -A INPUT -j DROP

# Save firewall rules
sudo iptables-save > /etc/iptables/rules.v4
```

#### 2. SSL/TLS Configuration
```bash
# Generate SSL certificates with Let's Encrypt
sudo certbot --nginx -d autobot.company.com

# Or use corporate certificates
sudo cp /path/to/corporate.crt /etc/ssl/certs/autobot.crt
sudo cp /path/to/corporate.key /etc/ssl/private/autobot.key
```

#### 3. Authentication Integration
**LDAP/Active Directory Integration**:
```yaml
# config/auth.yaml
authentication:
  provider: "ldap"
  ldap:
    server: "ldap://ad.company.com:389"
    bind_dn: "CN=autobot-service,OU=Service Accounts,DC=company,DC=com"
    bind_password: "${LDAP_SERVICE_PASSWORD}"
    user_search_base: "OU=Users,DC=company,DC=com"
    user_search_filter: "(sAMAccountName={username})"
    group_search_base: "OU=Groups,DC=company,DC=com"
    group_search_filter: "(member={user_dn})"

  role_mapping:
    "CN=AutoBot-Admins,OU=Groups,DC=company,DC=com": "admin"
    "CN=Developers,OU=Groups,DC=company,DC=com": "developer"
    "CN=Users,OU=Groups,DC=company,DC=com": "user"
```

### Monitoring & Observability

#### 1. Prometheus Configuration
**`monitoring/prometheus.yml`**:
```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "autobot_rules.yml"

scrape_configs:
  - job_name: 'autobot-backend'
    static_configs:
      - targets: ['localhost:8001']
    metrics_path: '/api/metrics'
    scrape_interval: 10s

  - job_name: 'autobot-postgres'
    static_configs:
      - targets: ['localhost:9187']

  - job_name: 'autobot-redis'
    static_configs:
      - targets: ['localhost:9121']

alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - alertmanager:9093
```

#### 2. Grafana Dashboard
**`monitoring/autobot-dashboard.json`**:
```json
{
  "dashboard": {
    "title": "AutoBot Performance Dashboard",
    "panels": [
      {
        "title": "Request Rate",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(autobot_requests_total[5m])",
            "legendFormat": "Requests/sec"
          }
        ]
      },
      {
        "title": "Response Time",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(autobot_request_duration_seconds_bucket[5m]))",
            "legendFormat": "95th percentile"
          }
        ]
      }
    ]
  }
}
```

### Backup & Disaster Recovery

#### 1. Database Backup
```bash
#!/bin/bash
# scripts/backup_database.sh

BACKUP_DIR="/backups/autobot"
DATE=$(date +%Y%m%d_%H%M%S)

# PostgreSQL backup
pg_dump -h localhost -U autobot autobot > "$BACKUP_DIR/autobot_db_$DATE.sql"

# Compress backup
gzip "$BACKUP_DIR/autobot_db_$DATE.sql"

# Upload to S3 (optional)
aws s3 cp "$BACKUP_DIR/autobot_db_$DATE.sql.gz" s3://autobot-backups/database/

# Clean old backups (keep 30 days)
find "$BACKUP_DIR" -name "autobot_db_*.sql.gz" -mtime +30 -delete
```

#### 2. Application Backup
```bash
#!/bin/bash
# scripts/backup_application.sh

BACKUP_DIR="/backups/autobot"
DATE=$(date +%Y%m%d_%H%M%S)

# Backup configuration
tar -czf "$BACKUP_DIR/config_$DATE.tar.gz" config/

# Backup data directory
tar -czf "$BACKUP_DIR/data_$DATE.tar.gz" data/

# Backup logs (last 7 days)
find logs/ -name "*.log" -mtime -7 -exec tar -czf "$BACKUP_DIR/logs_$DATE.tar.gz" {} +

# Upload to remote storage
rsync -av "$BACKUP_DIR/" backup-server:/backups/autobot/
```

#### 3. Disaster Recovery Plan
```bash
#!/bin/bash
# scripts/disaster_recovery.sh

# 1. Restore database
gunzip -c /backups/autobot_db_latest.sql.gz | psql -h localhost -U autobot autobot

# 2. Restore configuration
tar -xzf /backups/config_latest.tar.gz -C /

# 3. Restore data
tar -xzf /backups/data_latest.tar.gz -C /opt/autobot/

# 4. Restart services
systemctl restart autobot-backend
systemctl restart nginx

# 5. Verify system health
curl -f http://localhost:8001/api/system/health || exit 1
```

## Security Configuration

### SSL/TLS Setup

#### 1. Certificate Generation
```bash
# Using Let's Encrypt
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com

# Using self-signed certificates (development)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/ssl/private/autobot.key \
    -out /etc/ssl/certs/autobot.crt
```

#### 2. Nginx SSL Configuration
```nginx
# Strong SSL configuration
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
ssl_prefer_server_ciphers off;

# HSTS
add_header Strict-Transport-Security "max-age=63072000" always;

# OCSP stapling
ssl_stapling on;
ssl_stapling_verify on;
```

### Firewall Configuration

#### 1. UFW (Ubuntu)
```bash
# Reset firewall
sudo ufw --force reset

# Default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH (adjust port as needed)
sudo ufw allow 22/tcp

# Allow HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Allow from specific networks only
sudo ufw allow from 10.0.0.0/8 to any port 8001

# Enable firewall
sudo ufw enable
```

#### 2. iptables (Advanced)
```bash
#!/bin/bash
# scripts/configure_firewall.sh

# Flush existing rules
iptables -F
iptables -X
iptables -t nat -F
iptables -t nat -X

# Default policies
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT ACCEPT

# Allow loopback
iptables -A INPUT -i lo -j ACCEPT

# Allow established connections
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# Allow SSH (limit connections)
iptables -A INPUT -p tcp --dport 22 -m limit --limit 5/min -j ACCEPT

# Allow HTTP/HTTPS
iptables -A INPUT -p tcp --dport 80 -j ACCEPT
iptables -A INPUT -p tcp --dport 443 -j ACCEPT

# Allow API access from internal networks only
iptables -A INPUT -p tcp -s 10.0.0.0/8 --dport 8001 -j ACCEPT
iptables -A INPUT -p tcp -s 172.16.0.0/12 --dport 8001 -j ACCEPT
iptables -A INPUT -p tcp -s 192.168.0.0/16 --dport 8001 -j ACCEPT

# Save rules
iptables-save > /etc/iptables/rules.v4
```

## Monitoring & Maintenance

### Health Monitoring

#### 1. System Health Script
```bash
#!/bin/bash
# scripts/health_check.sh

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "AutoBot Health Check Report"
echo "=========================="
echo "Timestamp: $(date)"
echo ""

# Check services
check_service() {
    local service_name=$1
    if systemctl is-active --quiet "$service_name"; then
        echo -e "${GREEN}✓${NC} $service_name is running"
    else
        echo -e "${RED}✗${NC} $service_name is not running"
        systemctl status "$service_name" --no-pager -l
    fi
}

echo "Service Status:"
check_service "autobot-backend"
check_service "nginx"
check_service "postgresql"
check_service "redis"
echo ""

# Check API health
echo "API Health:"
if curl -sf http://localhost:8001/api/system/health > /dev/null; then
    echo -e "${GREEN}✓${NC} API is responding"
    # Get detailed health info
    curl -s http://localhost:8001/api/system/health | jq -r '.data.status'
else
    echo -e "${RED}✗${NC} API is not responding"
fi
echo ""

# Check disk space
echo "Disk Space:"
df -h | grep -E "/$|/opt|/var" | awk '{
    if ($5+0 > 90)
        print "\033[0;31m✗\033[0m " $0
    else if ($5+0 > 80)
        print "\033[1;33m⚠\033[0m " $0
    else
        print "\033[0;32m✓\033[0m " $0
}'
echo ""

# Check memory usage
echo "Memory Usage:"
free -h | awk 'NR==2{
    used_percent = $3/$2 * 100
    if (used_percent > 90)
        print "\033[0;31m✗\033[0m Memory: " $3 "/" $2 " (" used_percent "%)"
    else if (used_percent > 80)
        print "\033[1;33m⚠\033[0m Memory: " $3 "/" $2 " (" used_percent "%)"
    else
        print "\033[0;32m✓\033[0m Memory: " $3 "/" $2 " (" used_percent "%)"
}'
echo ""

# Check recent errors in logs
echo "Recent Errors (last 1 hour):"
error_count=$(journalctl --since "1 hour ago" | grep -i error | wc -l)
if [ "$error_count" -gt 0 ]; then
    echo -e "${YELLOW}⚠${NC} Found $error_count errors in system logs"
    journalctl --since "1 hour ago" | grep -i error | tail -5
else
    echo -e "${GREEN}✓${NC} No errors found in recent logs"
fi
```

#### 2. Automated Monitoring with cron
```bash
# Add to crontab (crontab -e)

# Health check every 5 minutes
*/5 * * * * /opt/autobot/scripts/health_check.sh > /var/log/autobot/health_check.log 2>&1

# Database backup daily at 2 AM
0 2 * * * /opt/autobot/scripts/backup_database.sh

# Log rotation weekly
0 0 * * 0 /opt/autobot/scripts/rotate_logs.sh

# Check for updates monthly
0 0 1 * * /opt/autobot/scripts/check_updates.sh
```

### Log Management

#### 1. Log Rotation Configuration
**`/etc/logrotate.d/autobot`**:
```
/var/log/autobot/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 0644 autobot autobot
    postrotate
        systemctl reload autobot-backend
    endscript
}
```

#### 2. Centralized Logging (ELK Stack)
**`monitoring/filebeat.yml`**:
```yaml
filebeat.inputs:
- type: log
  enabled: true
  paths:
    - /var/log/autobot/*.log
  fields:
    service: autobot
  fields_under_root: true

output.elasticsearch:
  hosts: ["elasticsearch:9200"]
  index: "autobot-logs-%{+yyyy.MM.dd}"

setup.template.name: "autobot"
setup.template.pattern: "autobot-*"
```

### Update Management

#### 1. Update Script
```bash
#!/bin/bash
# scripts/update_autobot.sh

set -e

echo "AutoBot Update Script"
echo "===================="

# Backup current version
echo "Creating backup..."
tar -czf "/backups/autobot_backup_$(date +%Y%m%d_%H%M%S).tar.gz" /opt/autobot

# Pull latest changes
cd /opt/autobot
git fetch origin
git checkout main
git pull origin main

# Update Python dependencies
source venv/bin/activate
pip install -r requirements.txt

# Update frontend dependencies
cd autobot-vue
npm ci --production
npm run build
cd ..

# Run database migrations
python scripts/migrate_database.py

# Test configuration
python scripts/validate_config.py

# Restart services
sudo systemctl restart autobot-backend
sudo systemctl restart nginx

# Health check
sleep 10
if curl -sf http://localhost:8001/api/system/health; then
    echo "✓ Update completed successfully"
else
    echo "✗ Update failed - rolling back..."
    # Rollback logic here
    exit 1
fi
```

#### 2. Blue-Green Deployment
```bash
#!/bin/bash
# scripts/blue_green_deploy.sh

CURRENT_ENV=$(curl -s http://localhost/api/system/info | jq -r '.data.environment')
NEW_ENV=$([[ "$CURRENT_ENV" == "blue" ]] && echo "green" || echo "blue")

echo "Deploying to $NEW_ENV environment..."

# Deploy to new environment
docker-compose -f docker-compose.$NEW_ENV.yml up -d

# Wait for health check
for i in {1..30}; do
    if curl -sf http://$NEW_ENV.autobot.local/api/system/health; then
        echo "✓ $NEW_ENV environment is healthy"
        break
    fi
    sleep 10
done

# Switch traffic
echo "Switching traffic to $NEW_ENV..."
# Update load balancer configuration
# This depends on your load balancer setup

# Shutdown old environment
echo "Shutting down $CURRENT_ENV environment..."
docker-compose -f docker-compose.$CURRENT_ENV.yml down
```

## Troubleshooting

### Common Issues

#### 1. Service Won't Start
```bash
# Check service status
sudo systemctl status autobot-backend

# Check logs
sudo journalctl -u autobot-backend -f

# Check configuration
python scripts/validate_config.py

# Check ports
sudo netstat -tlnp | grep :8001

# Check dependencies
pip check
```

#### 2. Database Connection Issues
```bash
# Test database connection
psql -h localhost -U autobot -d autobot -c "SELECT version();"

# Check PostgreSQL status
sudo systemctl status postgresql

# Check PostgreSQL logs
sudo tail -f /var/log/postgresql/postgresql-*.log

# Reset database connection
sudo systemctl restart postgresql
sudo systemctl restart autobot-backend
```

#### 3. High Memory Usage
```bash
# Monitor memory usage
htop
# or
ps aux --sort=-%mem | head -10

# Check for memory leaks
valgrind --tool=memcheck --leak-check=full python main.py

# Adjust memory limits
# Edit /etc/systemd/system/autobot-backend.service
# Add: MemoryLimit=2G
sudo systemctl daemon-reload
sudo systemctl restart autobot-backend
```

#### 4. Performance Issues
```bash
# Monitor system resources
iostat -x 1
vmstat 1

# Check database performance
sudo -u postgres psql -d autobot -c "
SELECT query, calls, total_time, mean_time
FROM pg_stat_statements
ORDER BY total_time DESC
LIMIT 10;"

# Profile Python application
pip install py-spy
sudo py-spy top --pid $(pgrep -f "python main.py")
```

### Diagnostic Tools

#### 1. System Diagnostic Script
```bash
#!/bin/bash
# scripts/diagnose_system.sh

echo "AutoBot System Diagnostic"
echo "========================"

# System information
echo "System Information:"
uname -a
cat /etc/os-release
echo ""

# Hardware information
echo "Hardware Information:"
lscpu | grep -E "Model name|CPU\(s\)|Thread"
free -h
df -h
echo ""

# Network configuration
echo "Network Configuration:"
ip addr show
ss -tlnp | grep -E ":80|:443|:8001"
echo ""

# Docker information (if applicable)
if command -v docker &> /dev/null; then
    echo "Docker Information:"
    docker version
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    echo ""
fi

# Process information
echo "AutoBot Processes:"
ps aux | grep -E "python|nginx|postgres|redis" | grep -v grep
echo ""

# Recent system events
echo "Recent System Events:"
journalctl --since "1 hour ago" | grep -E "autobot|error|fail" | tail -10
```

#### 2. Performance Diagnostic
```bash
#!/bin/bash
# scripts/diagnose_performance.sh

echo "Performance Diagnostic Report"
echo "============================"

# CPU utilization
echo "CPU Utilization (last 5 minutes):"
sar -u 1 5

# Memory utilization
echo "Memory Utilization:"
free -h
echo ""

# Disk I/O
echo "Disk I/O Statistics:"
iostat -x 1 3

# Network statistics
echo "Network Statistics:"
ss -i

# Database performance
echo "Database Performance:"
sudo -u postgres psql -d autobot -c "
SELECT
    schemaname,
    tablename,
    seq_scan,
    seq_tup_read,
    idx_scan,
    idx_tup_fetch
FROM pg_stat_user_tables
ORDER BY seq_tup_read DESC;"

# Application metrics
echo "Application Metrics:"
curl -s http://localhost:8001/api/metrics | jq .
```

---

This completes the comprehensive deployment guide. Choose the deployment method that best fits your infrastructure and requirements. For additional support, refer to the [troubleshooting section](#troubleshooting) or [open an issue](https://github.com/your-org/autobot/issues).
