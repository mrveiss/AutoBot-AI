# AutoBot Comprehensive Troubleshooting Guide

Complete troubleshooting guide for AutoBot covering common issues, diagnostic procedures, and resolution steps for all components and deployment scenarios.

## Table of Contents

- [Quick Diagnostic Tools](#quick-diagnostic-tools)
- [Common Issues](#common-issues)
- [Component-Specific Troubleshooting](#component-specific-troubleshooting)
- [Performance Issues](#performance-issues)
- [Network & Connectivity](#network--connectivity)
- [Security & Authentication](#security--authentication)
- [Database Issues](#database-issues)
- [Docker & Containerization](#docker--containerization)
- [Cloud Deployment Issues](#cloud-deployment-issues)
- [Advanced Debugging](#advanced-debugging)
- [Recovery Procedures](#recovery-procedures)

## Quick Diagnostic Tools

### System Health Check Script

```bash
#!/bin/bash
# Quick health check for AutoBot
echo "=== AutoBot Quick Health Check ==="

# Check if services are running
services=("autobot-backend" "nginx" "postgresql" "redis-server")
for service in "${services[@]}"; do
    if systemctl is-active --quiet "$service" 2>/dev/null; then
        echo "✅ $service: Running"
    else
        echo "❌ $service: Not running"
    fi
done

# Check API health
if curl -sf http://localhost:8001/api/system/health >/dev/null 2>&1; then
    echo "✅ API: Responding"
else
    echo "❌ API: Not responding"
fi

# Check frontend
if curl -sf http://localhost:5173 >/dev/null 2>&1; then
    echo "✅ Frontend: Available"
else
    echo "❌ Frontend: Not available"
fi

# Check LLM service
if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "✅ Ollama: Running"
else
    echo "❌ Ollama: Not running"
fi

# Check disk space
disk_usage=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
if [ "$disk_usage" -lt 90 ]; then
    echo "✅ Disk space: $disk_usage% used"
else
    echo "⚠️ Disk space: $disk_usage% used (LOW SPACE)"
fi

# Check memory
mem_usage=$(free | awk 'NR==2{printf "%.0f", $3*100/$2}')
if [ "$mem_usage" -lt 90 ]; then
    echo "✅ Memory: $mem_usage% used"
else
    echo "⚠️ Memory: $mem_usage% used (HIGH USAGE)"
fi
```

### Log Analysis Tool

```bash
#!/bin/bash
# Analyze AutoBot logs for issues
echo "=== AutoBot Log Analysis ==="

# Check for recent errors in system logs
echo "Recent errors in system logs:"
journalctl --since "1 hour ago" | grep -i "error\|fail\|exception" | tail -5

# Check AutoBot specific logs
if [ -f "logs/autobot.log" ]; then
    echo -e "\nRecent AutoBot errors:"
    tail -100 logs/autobot.log | grep -i "error\|exception\|fail" | tail -5
fi

# Check for port conflicts
echo -e "\nPort usage check:"
ss -tlnp | grep -E ":5173|:8001|:11434|:6379|:5432"

# Check process memory usage
echo -e "\nTop memory consumers:"
ps aux --sort=-%mem | head -6
```

## Common Issues

### 1. AutoBot Won't Start

#### Symptoms
- Service fails to start
- Import errors in logs
- Port binding errors

#### Diagnostic Steps
```bash
# Check service status
sudo systemctl status autobot-backend

# Check logs for errors
sudo journalctl -u autobot-backend -n 50

# Verify Python environment
source venv/bin/activate
python -c "import sys; print(sys.executable)"
pip check

# Check configuration syntax
python -c "
import yaml
with open('config/config.yaml') as f:
    yaml.safe_load(f)
print('Configuration syntax OK')
"

# Check port availability
sudo netstat -tlnp | grep :8001
```

#### Common Solutions

**Missing Dependencies:**
```bash
# Reinstall requirements
source venv/bin/activate
pip install -r requirements.txt --force-reinstall

# Install system dependencies
sudo apt update
sudo apt install -y python3-dev build-essential
```

**Configuration Issues:**
```bash
# Reset configuration
cp config/config.example.yaml config/config.yaml
# Edit with correct values
nano config/config.yaml
```

**Permission Issues:**
```bash
# Fix file permissions
sudo chown -R $USER:$USER /opt/autobot
chmod +x run_agent.sh
chmod +x scripts/setup/setup_agent.sh
```

**Port Conflicts:**
```bash
# Find process using port 8001
sudo lsof -i :8001
# Kill conflicting process
sudo kill -9 <PID>
# Or change port in config
```

### 2. LLM/Ollama Connection Issues

#### Symptoms
- "Connection refused" errors
- LLM timeout errors
- Model loading failures

#### Diagnostic Steps
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Check Ollama process
ps aux | grep ollama

# Check Ollama logs
journalctl -u ollama -n 50

# Test model availability
ollama list
```

#### Solutions

**Ollama Not Running:**
```bash
# Start Ollama service
sudo systemctl start ollama
sudo systemctl enable ollama

# Or start manually
ollama serve &
```

**Model Not Available:**
```bash
# Pull required models
ollama pull llama3.2:1b-instruct
ollama pull llama3.2:3b-instruct

# List available models
ollama list

# Update config with available model
nano config/config.yaml
```

**Connection Issues:**
```bash
# Check Ollama host configuration
export OLLAMA_HOST=0.0.0.0:11434
ollama serve

# Verify in AutoBot config
# llm_config:
#   providers:
#     ollama:
#       host: "http://localhost:11434"
```

### 3. Frontend Build/Connection Issues

#### Symptoms
- White screen in browser
- API connection errors
- Build failures

#### Diagnostic Steps
```bash
cd autobot-vue

# Check Node.js version
node --version  # Should be 18+
npm --version

# Check for build errors
npm run build

# Check development server
npm run dev

# Check API connectivity from frontend
curl http://localhost:8001/api/system/health
```

#### Solutions

**Node.js Version Issues:**
```bash
# Install correct Node.js version
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Or use nvm
nvm install 18
nvm use 18
```

**Build Dependencies:**
```bash
cd autobot-vue
rm -rf node_modules package-lock.json
npm install
npm run build
```

**CORS Issues:**
```bash
# Update backend CORS settings in config.yaml
backend:
  cors_origins:
    - "http://localhost:5173"
    - "http://127.0.0.1:5173"
    - "https://your-domain.com"
```

### 4. Database Connection Issues

#### Symptoms
- Database connection refused
- Migration errors
- Data persistence issues

#### Diagnostic Steps
```bash
# Test database connection
python -c "
import sqlite3
try:
    conn = sqlite3.connect('data/autobot.db')
    print('SQLite connection OK')
    conn.close()
except Exception as e:
    print(f'Database error: {e}')
"

# For PostgreSQL
psql -h localhost -U autobot -d autobot -c "SELECT version();"

# Check database files
ls -la data/
```

#### Solutions

**SQLite Issues:**
```bash
# Create data directory
mkdir -p data

# Check permissions
chmod 755 data
chmod 644 data/*.db

# Reset database
rm data/autobot.db
python scripts/setup_database.py
```

**PostgreSQL Issues:**
```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Reset user password
sudo -u postgres psql -c "ALTER USER autobot PASSWORD 'new_password';"

# Update configuration
nano config/config.yaml
# Update database password
```

### 5. Memory/Performance Issues

#### Symptoms
- Slow response times
- High memory usage
- System becoming unresponsive

#### Diagnostic Steps
```bash
# Monitor memory usage
free -h
ps aux --sort=-%mem | head -10

# Monitor CPU usage
top -p $(pgrep -f "python main.py")

# Check for memory leaks
python -m tracemalloc main.py

# Check disk I/O
iostat -x 1 5
```

#### Solutions

**High Memory Usage:**
```bash
# Reduce worker processes
# In config.yaml:
backend:
  workers: 2  # Reduce from 4

# Limit model cache
llm_config:
  cache_size: 100  # Reduce cache size

# Enable garbage collection
export PYTHONOPTIMIZE=1
```

**Slow Performance:**
```bash
# Enable Redis caching
# In config.yaml:
memory:
  redis:
    enabled: true

# Optimize database
sqlite3 data/autobot.db "VACUUM; ANALYZE;"

# Use faster models
# Replace heavy models with lighter ones:
# llama3.2:3b → llama3.2:1b
```

## Component-Specific Troubleshooting

### Backend API Issues

#### Error: "FastAPI server won't start"
```bash
# Check Python version
python --version  # Should be 3.10+

# Check FastAPI installation
pip show fastapi uvicorn

# Test minimal FastAPI app
python -c "
from fastapi import FastAPI
app = FastAPI()
print('FastAPI import OK')
"

# Start with verbose logging
python main.py --log-level DEBUG
```

#### Error: "Module not found"
```bash
# Check Python path
python -c "import sys; print('\n'.join(sys.path))"

# Add current directory to path
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Check for missing __init__.py files
find src -name "*.py" -path "*/test*" -prune -o -type d -exec ls {}/__init__.py \; 2>/dev/null
```

### Frontend Issues

#### Error: "Vite build failed"
```bash
# Clear cache
rm -rf node_modules/.vite
rm -rf dist

# Reinstall dependencies
npm ci

# Check for syntax errors
npm run lint

# Build with verbose output
npm run build -- --debug
```

#### Error: "API calls failing"
```bash
# Check network requests in browser dev tools
# F12 → Network tab

# Test API directly
curl -X POST http://localhost:8001/api/chat/message \
  -H "Content-Type: application/json" \
  -d '{"message": "test"}'

# Check proxy configuration in vite.config.js
```

### LLM Provider Issues

#### Error: "Model not found"
```bash
# List available models
ollama list

# Pull missing model
ollama pull llama3.2:1b-instruct

# Check model names in config
grep -r "model" config/config.yaml
```

#### Error: "Context length exceeded"
```bash
# Reduce context window in config
llm_config:
  context_window: 2048  # Reduce from 4096

# Clear conversation history
curl -X DELETE http://localhost:8001/api/chat/history
```

### Knowledge Base Issues

#### Error: "Vector index failed"
```bash
# Check vector database
ls -la data/vector_db/

# Reset vector index
rm -rf data/vector_db
python scripts/rebuild_index.py

# Check embedding model
ollama list | grep embed
ollama pull nomic-embed-text
```

#### Error: "Search returns no results"
```bash
# Check indexed documents
curl http://localhost:8001/api/knowledge/stats

# Add test document
curl -X POST http://localhost:8001/api/knowledge/documents \
  -H "Content-Type: application/json" \
  -d '{"content": "test document", "metadata": {"title": "test"}}'

# Test search
curl -X POST http://localhost:8001/api/knowledge/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test"}'
```

## Performance Issues

### Slow API Response Times

#### Diagnostic Steps
```bash
# Measure response times
time curl http://localhost:8001/api/system/health

# Profile API endpoints
curl -w "@curl-format.txt" http://localhost:8001/api/chat/message \
  -H "Content-Type: application/json" \
  -d '{"message": "test"}'

# Create curl-format.txt:
cat > curl-format.txt << 'EOF'
     time_namelookup:  %{time_namelookup}\n
        time_connect:  %{time_connect}\n
     time_appconnect:  %{time_appconnect}\n
    time_pretransfer:  %{time_pretransfer}\n
       time_redirect:  %{time_redirect}\n
  time_starttransfer:  %{time_starttransfer}\n
                     ----------\n
          time_total:  %{time_total}\n
EOF
```

#### Solutions
```bash
# Enable caching
# In config.yaml:
cache:
  enabled: true
  ttl: 3600

# Use connection pooling
backend:
  max_connections: 100
  keepalive_timeout: 65

# Optimize database queries
# Enable query logging and analyze slow queries
```

### High CPU Usage

#### Diagnostic Steps
```bash
# Identify CPU-intensive processes
top -o %CPU

# Profile Python application
pip install py-spy
sudo py-spy top --pid $(pgrep -f "python main.py")

# Check for infinite loops
strace -p $(pgrep -f "python main.py") -e trace=all
```

#### Solutions
```bash
# Reduce model size
# Use quantized models: llama3.2:1b-q4_0

# Limit concurrent requests
backend:
  max_workers: 2
  request_timeout: 30

# Enable NPU acceleration (if available)
llm_config:
  use_npu: true
  optimization_level: "O2"
```

## Network & Connectivity

### Port Binding Issues

#### Error: "Address already in use"
```bash
# Find process using port
sudo lsof -i :8001
sudo netstat -tlnp | grep :8001

# Kill conflicting process
sudo kill -9 <PID>

# Change port in configuration
# config.yaml:
backend:
  server_port: 8002
```

### Firewall Issues

#### Error: "Connection refused from external hosts"
```bash
# Check firewall status
sudo ufw status

# Allow AutoBot ports
sudo ufw allow 8001/tcp
sudo ufw allow 5173/tcp

# Check iptables rules
sudo iptables -L -n

# Test connectivity
telnet localhost 8001
nc -zv localhost 8001
```

### DNS Resolution Issues

#### Error: "Name resolution failed"
```bash
# Test DNS resolution
nslookup your-domain.com
dig your-domain.com

# Check /etc/hosts
cat /etc/hosts

# Test with IP address instead of hostname
curl http://192.168.1.100:8001/api/system/health
```

## Security & Authentication

### Authentication Failures

#### Error: "Login failed"
```bash
# Check user database
sqlite3 data/autobot.db "SELECT * FROM users;"

# Reset admin password
python scripts/reset_admin_password.py

# Check authentication settings
grep -A 10 "authentication" config/config.yaml
```

### Permission Denied Errors

#### Error: "Insufficient permissions"
```bash
# Check user roles
curl http://localhost:8001/api/auth/user-info

# Check security configuration
grep -A 20 "security" config/config.yaml

# Disable security for debugging
# config.yaml:
security:
  enable_auth: false
  enable_command_security: false
```

### SSL/TLS Issues

#### Error: "Certificate verification failed"
```bash
# Check certificate validity
openssl x509 -in /etc/ssl/certs/autobot.crt -text -noout

# Test SSL connection
openssl s_client -connect your-domain.com:443

# Regenerate self-signed certificate
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/private/autobot.key \
  -out /etc/ssl/certs/autobot.crt
```

## Database Issues

### SQLite Corruption

#### Symptoms
- Database locked errors
- Corrupt database messages
- Data loss

#### Recovery Steps
```bash
# Check database integrity
sqlite3 data/autobot.db "PRAGMA integrity_check;"

# Backup current database
cp data/autobot.db data/autobot.db.backup

# Attempt repair
sqlite3 data/autobot.db ".recover" | sqlite3 data/autobot_recovered.db

# If corruption is severe, rebuild
rm data/autobot.db
python scripts/setup_database.py
```

### PostgreSQL Issues

#### Error: "Connection limit exceeded"
```bash
# Check current connections
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity;"

# Kill idle connections
sudo -u postgres psql -c "
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'idle' AND state_change < now() - interval '1 hour';"

# Increase connection limit
# In postgresql.conf:
# max_connections = 200
sudo systemctl restart postgresql
```

#### Error: "Disk full"
```bash
# Check database size
sudo -u postgres psql -c "
SELECT pg_size_pretty(pg_database_size('autobot'));"

# Clean old WAL files
sudo -u postgres psql -c "SELECT pg_switch_wal();"

# Vacuum database
sudo -u postgres psql -d autobot -c "VACUUM FULL;"
```

## Docker & Containerization

### Docker Build Failures

#### Error: "Build failed"
```bash
# Build with verbose output
docker build . --no-cache --progress=plain

# Check Dockerfile syntax
docker run --rm -i hadolint/hadolint < Dockerfile

# Check for large files
docker run --rm -v $(pwd):/app alpine find /app -size +100M
```

### Container Won't Start

#### Error: "Container exits immediately"
```bash
# Check container logs
docker logs autobot-backend

# Run container interactively
docker run -it --entrypoint /bin/bash autobot:latest

# Check container health
docker inspect autobot-backend | jq '.[0].State'
```

### Docker Compose Issues

#### Error: "Service dependencies failed"
```bash
# Check service status
docker-compose ps

# Restart specific service
docker-compose restart autobot-backend

# View service logs
docker-compose logs -f autobot-backend

# Recreate containers
docker-compose down
docker-compose up -d --force-recreate
```

## Cloud Deployment Issues

### AWS ECS Issues

#### Error: "Task failed to start"
```bash
# Check ECS task logs
aws logs get-log-events \
  --log-group-name /ecs/autobot \
  --log-stream-name ecs/autobot-backend/task-id

# Check task definition
aws ecs describe-task-definition --task-definition autobot

# Check service events
aws ecs describe-services \
  --cluster autobot-cluster \
  --services autobot
```

### Kubernetes Issues

#### Error: "Pod CrashLoopBackOff"
```bash
# Check pod status
kubectl get pods -l app=autobot-backend

# View pod logs
kubectl logs -l app=autobot-backend --previous

# Describe pod for events
kubectl describe pod <pod-name>

# Check resource limits
kubectl top pods
```

#### Error: "Service not accessible"
```bash
# Check service status
kubectl get services

# Test service connectivity
kubectl port-forward service/autobot-backend 8001:80

# Check ingress
kubectl get ingress
kubectl describe ingress autobot-ingress
```

## Advanced Debugging

### Debug Mode Activation

```bash
# Enable debug mode in config
# config.yaml:
backend:
  debug: true
  log_level: "DEBUG"

# Start with debug flags
python main.py --debug --verbose

# Enable SQL query logging
export AUTOBOT_SQL_DEBUG=1
```

### Memory Leak Detection

```bash
# Install memory profiling tools
pip install memory-profiler py-spy

# Profile memory usage
python -m memory_profiler main.py

# Monitor memory over time
py-spy top --pid $(pgrep -f "python main.py") --duration 60
```

### Performance Profiling

```bash
# Install profiling tools
pip install cProfile py-spy line_profiler

# Profile CPU usage
python -m cProfile -o profile.stats main.py

# Analyze profile
python -c "
import pstats
p = pstats.Stats('profile.stats')
p.sort_stats('cumulative').print_stats(10)
"

# Real-time profiling
py-spy record -o profile.svg --pid $(pgrep -f "python main.py")
```

### Network Traffic Analysis

```bash
# Monitor network traffic
sudo tcpdump -i any port 8001

# Check connection states
ss -tupln | grep :8001

# Monitor HTTP requests
tail -f /var/log/nginx/access.log | grep autobot
```

## Recovery Procedures

### Complete System Recovery

```bash
#!/bin/bash
# Complete AutoBot recovery procedure

echo "Starting AutoBot recovery..."

# 1. Stop all services
sudo systemctl stop autobot-backend nginx

# 2. Backup current state
mkdir -p /tmp/autobot-recovery-$(date +%Y%m%d_%H%M%S)
cp -r data/ config/ logs/ /tmp/autobot-recovery-*/

# 3. Reset to known good state
git fetch origin
git reset --hard origin/main

# 4. Reinstall dependencies
source venv/bin/activate
pip install -r requirements.txt --force-reinstall

# 5. Rebuild frontend
cd autobot-vue
npm ci
npm run build
cd ..

# 6. Reset database (WARNING: DATA LOSS)
rm -f data/autobot.db
python scripts/setup_database.py

# 7. Restore configuration
cp config/config.example.yaml config/config.yaml
# Edit config.yaml with your settings

# 8. Start services
sudo systemctl start autobot-backend nginx

# 9. Verify health
sleep 10
curl -f http://localhost:8001/api/system/health || echo "Health check failed"

echo "Recovery completed. Check logs for any issues."
```

### Data Recovery

```bash
#!/bin/bash
# Recover data from backups

BACKUP_DIR="/backups/autobot"
RECOVERY_DATE=${1:-$(date +%Y%m%d)}

echo "Recovering AutoBot data from $RECOVERY_DATE..."

# Find latest backup
BACKUP_FILE=$(find "$BACKUP_DIR" -name "*$RECOVERY_DATE*.tar.gz" | sort | tail -1)

if [ -z "$BACKUP_FILE" ]; then
    echo "No backup found for $RECOVERY_DATE"
    exit 1
fi

# Stop services
sudo systemctl stop autobot-backend

# Backup current state
cp -r data/ data.backup.$(date +%H%M%S)

# Restore from backup
tar -xzf "$BACKUP_FILE" -C /

# Start services
sudo systemctl start autobot-backend

# Verify restoration
python scripts/validate_data.py

echo "Data recovery completed from $BACKUP_FILE"
```

### Configuration Recovery

```bash
#!/bin/bash
# Recover from configuration issues

echo "Recovering AutoBot configuration..."

# 1. Backup current config
cp config/config.yaml config/config.yaml.backup.$(date +%H%M%S)

# 2. Reset to default
cp config/config.example.yaml config/config.yaml

# 3. Validate syntax
python -c "
import yaml
try:
    with open('config/config.yaml') as f:
        yaml.safe_load(f)
    print('✅ Configuration syntax valid')
except Exception as e:
    print(f'❌ Configuration error: {e}')
    exit(1)
"

# 4. Test configuration
python scripts/validate_config.py

echo "Configuration recovery completed"
```

---

## Getting Help

If you've tried the solutions in this guide and still have issues:

### 1. Gather Information
Run the diagnostic script and collect:
- System information (`uname -a`)
- AutoBot version (`git describe --tags`)
- Error logs (last 50 lines)
- Configuration (sanitized)

### 2. Check Known Issues
- [GitHub Issues](https://github.com/your-org/autobot/issues)
- [Documentation](../README.md)
- [FAQ](../FAQ.md)

### 3. Report New Issues
Include:
- Complete error message
- Steps to reproduce
- System environment
- Diagnostic output

### 4. Community Support
- [Discord Server](https://discord.gg/autobot)
- [Reddit Community](https://reddit.com/r/autobot)
- [Stack Overflow](https://stackoverflow.com/questions/tagged/autobot)

---

**Last Updated**: 2025-01-16
**Version**: 2.0
