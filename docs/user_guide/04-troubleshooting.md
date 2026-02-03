# Troubleshooting Guide

## Common Issues and Solutions

### Installation Problems

#### Issue: Setup script fails with permission errors
**Symptoms**: "Permission denied" errors during setup
**Solution**:
```bash
# Make script executable
chmod +x setup_agent.sh

# Run with proper permissions
sudo ./setup_agent.sh
```

#### Issue: Python version conflicts
**Symptoms**: "Python 3.10 not found" or version mismatch errors
**Solution**:
```bash
# Check pyenv installation
pyenv versions

# Install correct Python version
pyenv install 3.10.13
pyenv global 3.10.13

# Recreate virtual environment
rm -rf venv
python -m venv venv
```

### Runtime Issues

#### Issue: Agent won't start
**Symptoms**: Startup fails with configuration errors
**Diagnosis**:
```bash
# Check logs
tail -f logs/agent.log

# Validate configuration
python -c "from src.config import config; config.validate()"
```

**Common Fixes**:
- Verify `config/config.yaml` syntax
- Check file permissions on data directories
- Ensure required ports are available

#### Issue: LLM connection failed
**Symptoms**: "Connection refused" or timeout errors
**Diagnosis**:
```bash
# For Ollama
curl http://localhost:11434/api/version

# For OpenAI API
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
     https://api.openai.com/v1/models
```

**Solutions**:
- **Ollama**: Install and start Ollama service
- **OpenAI**: Verify API key and quota
- **Local Models**: Check GPU/CPU resources

### Performance Issues

#### Issue: Slow response times
**Symptoms**: Long delays between commands and responses
**Diagnosis**:
- Check CPU/GPU usage: `htop`, `nvidia-smi`
- Review logs for bottlenecks
- Monitor memory usage

**Solutions**:
- Enable GPU acceleration for local models
- Increase hardware resources
- Optimize model settings (quantization, context length)
- Use faster models for simple tasks

#### Issue: High memory usage
**Symptoms**: System slowing down, OOM errors
**Solutions**:
```bash
# Monitor memory
watch -n 1 free -h

# Restart with memory limits
python -Xmx4g main.py
```

### Network and Connectivity

#### Issue: Web interface not accessible
**Symptoms**: Cannot reach `http://localhost:8001`
**Diagnosis**:
```bash
# Check if port is in use
netstat -tlnp | grep 8001

# Test local connection
curl http://localhost:8001/health
```

**Solutions**:
- Change port in configuration
- Check firewall settings
- Verify network bindings

#### Issue: Redis connection failed
**Symptoms**: Knowledge base and memory features unavailable
**Solutions**:
```bash
# Install Redis
sudo apt install redis-server  # Ubuntu/Debian
brew install redis             # macOS

# Start Redis service
sudo systemctl start redis-server

# Test connection
redis-cli ping
```

### GPU/Hardware Issues

#### Issue: GPU not detected
**Symptoms**: Falls back to CPU inference despite GPU availability
**Diagnosis**:
```bash
# Check NVIDIA GPU
nvidia-smi

# Check AMD GPU
rocm-smi

# Test PyTorch GPU access
python -c "import torch; print(torch.cuda.is_available())"
```

**Solutions**:
- Install/update GPU drivers
- Install CUDA toolkit or ROCm
- Reinstall PyTorch with GPU support:
```bash
# NVIDIA CUDA
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# AMD ROCm
pip install torch torchvision --index-url https://download.pytorch.org/whl/rocm5.4.2
```

### Knowledge Base Issues

#### Issue: Knowledge search returns no results
**Symptoms**: Search queries don't find expected content
**Diagnosis**:
- Check if knowledge base is populated
- Verify embedding model is working
- Test with simple queries

**Solutions**:
- Re-index knowledge base
- Check embedding model compatibility
- Verify search query format

#### Issue: File upload fails
**Symptoms**: Cannot add documents to knowledge base
**Solutions**:
- Check file format support (PDF, DOCX, TXT, etc.)
- Verify file size limits
- Check storage permissions

## Diagnostic Commands

### System Health Check
```bash
# Run comprehensive diagnostics
python scripts/health_check.py

# Check specific components
python -c "from src.diagnostics import check_llm; check_llm()"
python -c "from src.diagnostics import check_knowledge_base; check_knowledge_base()"
```

### Log Analysis
```bash
# View recent errors
grep ERROR logs/agent.log | tail -20

# Monitor real-time logs
tail -f logs/agent.log logs/llm_usage.log

# Search for specific issues
grep -i "memory\|gpu\|connection" logs/agent.log
```

### Configuration Debugging
```bash
# Dump current configuration
python -c "from src.config import config; import json; print(json.dumps(config.to_dict(), indent=2))"

# Test configuration sections
python -c "from src.config import config; print(config.get_llm_config())"
```

## Getting Help

### Check Documentation
1. Review relevant user guide sections
2. Check developer documentation for technical details
3. Search project issues on GitHub

### Collect Debug Information
Before reporting issues, gather:
- Operating system and version
- Python version (`python --version`)
- AutoBot version/commit hash
- Configuration file (remove sensitive data)
- Relevant log entries
- Hardware specifications

### Submit Issues
1. **GitHub Issues**: Primary support channel
2. **Include Debug Info**: Attach logs and system information
3. **Reproducible Steps**: Provide clear reproduction instructions
4. **Expected vs Actual**: Describe what should happen vs what does

### Community Resources
- Project documentation and wiki
- Community discussions and forums
- Example configurations and use cases

## Emergency Recovery

### Complete Reset
```bash
# Stop all processes
pkill -f autobot

# Backup data
cp -r data/ data.backup/
cp config/config.yaml config.backup.yaml

# Reset to defaults
./setup_agent.sh --reset

# Restore data if needed
cp -r data.backup/* data/
```

### Safe Mode
```bash
# Start with minimal configuration
python main.py --safe-mode --no-gpu --no-workers
