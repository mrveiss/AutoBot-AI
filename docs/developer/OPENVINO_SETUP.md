# OpenVINO Setup and Validation Guide

**Status:** Validated
**Version:** 1.0.0
**Date:** 2025-11-16
**Issue:** #53 - OpenVINO Validation & Production Deployment
**Author:** mrveiss

## Overview

OpenVINO (Open Visual Inference and Neural Network Optimization) provides CPU and GPU optimization for AI inference workloads in AutoBot. This guide covers setup, validation, and production deployment.

## Current Implementation Status

### Installed Components

| Component | Status | Location |
|-----------|--------|----------|
| OpenVINO Runtime | ✅ Installed | `venv/lib/python3.10/site-packages/openvino/` |
| CPU Plugin | ✅ Available | `libopenvino_intel_cpu_plugin.so` |
| GPU Plugin | ✅ Installed | `libopenvino_intel_gpu_plugin.so` |
| NPU Plugin | ✅ Installed | `libopenvino_intel_npu_plugin.so` |
| Setup Script | ✅ Created | `scripts/setup/setup_openvino.sh` |
| LangChain Integration | ✅ Available | Embeddings and Reranking support |

### Detected Hardware

```
Available Devices: ['CPU']
CPU: Intel(R) Core(TM) Ultra 9 185H
```

**Note:** GPU and NPU plugins installed but not detected in WSL2 environment. Native Linux or Windows deployment will have full accelerator access.

## Installation

### Method 1: Main Virtual Environment (Recommended)

OpenVINO is already installed in the main AutoBot venv:

```bash
# Activate main venv
source venv/bin/activate

# Verify installation
python3 -c "from openvino.runtime import Core; print(Core().available_devices)"
```

### Method 2: Separate OpenVINO Environment

For isolated testing or development:

```bash
# Run setup script
bash scripts/setup/setup_openvino.sh

# Activate OpenVINO environment
source venvs/openvino_env/bin/activate
```

## Usage Examples

### Basic Device Detection

```python
from openvino.runtime import Core

core = Core()
devices = core.available_devices
print(f"Available devices: {devices}")

for device in devices:
    name = core.get_property(device, "FULL_DEVICE_NAME")
    print(f"  {device}: {name}")
```

### Model Compilation

```python
from openvino.runtime import Core, CompiledModel

core = Core()

# Load ONNX model
model = core.read_model("model.onnx")

# Compile for CPU
compiled_cpu = core.compile_model(model, "CPU")

# Compile for GPU (if available)
if "GPU" in core.available_devices:
    compiled_gpu = core.compile_model(model, "GPU")

# Auto device selection (best available)
compiled_auto = core.compile_model(model, "AUTO")
```

### Performance Hints

```python
from openvino.runtime import Core
from openvino.properties import hint

core = Core()

# Latency-optimized inference
config_latency = {hint.performance_mode: hint.PerformanceMode.LATENCY}
compiled = core.compile_model(model, "CPU", config_latency)

# Throughput-optimized inference
config_throughput = {hint.performance_mode: hint.PerformanceMode.THROUGHPUT}
compiled = core.compile_model(model, "CPU", config_throughput)
```

### LangChain Integration

```python
# OpenVINO Embeddings
from langchain_community.embeddings.openvino import OpenVINOEmbeddings

embeddings = OpenVINOEmbeddings(
    model_name_or_path="sentence-transformers/all-MiniLM-L6-v2",
    model_kwargs={"device": "CPU"},
    encode_kwargs={"normalize_embeddings": True}
)

# OpenVINO Reranking
from langchain_community.document_compressors.openvino_rerank import OpenVINOReranker

reranker = OpenVINOReranker(
    model_name_or_path="cross-encoder/ms-marco-MiniLM-L-6-v2",
    device="CPU"
)
```

## AutoBot Integration Points

### 1. Knowledge Base Embeddings

Located in: `backend/services/knowledge_service.py`

Potential optimization: Use OpenVINO-optimized embeddings for faster vector generation.

```python
# Current (standard embeddings)
from langchain_huggingface import HuggingFaceEmbeddings
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

# OpenVINO-optimized
from langchain_community.embeddings.openvino import OpenVINOEmbeddings
embeddings = OpenVINOEmbeddings(model_name_or_path="all-MiniLM-L6-v2")
```

### 2. RAG Query Processing

Located in: `backend/api/knowledge.py`

Use OpenVINO for reranking retrieved documents.

### 3. Voice Processing

Located in: `src/voice_processing_system.py`

Potential for OpenVINO-optimized speech recognition models.

## Performance Benchmarking

### Test Script: `tests/openvino/test_openvino_benchmark.py`

Compares inference performance:
- Native PyTorch/TensorFlow
- OpenVINO CPU
- OpenVINO GPU (when available)

### Expected Performance Gains

| Workload | Native | OpenVINO CPU | Improvement |
|----------|--------|--------------|-------------|
| Text Embeddings | 100ms | 60-80ms | 20-40% |
| Document Reranking | 150ms | 90-120ms | 20-40% |
| Image Classification | 200ms | 100-140ms | 30-50% |

*Note: Actual performance depends on model architecture, batch size, and hardware.*

## Production Deployment

### Environment Configuration

Add to `.env`:

```bash
# OpenVINO Configuration
OPENVINO_ENABLED=true
OPENVINO_DEVICE=AUTO  # AUTO, CPU, GPU, NPU
OPENVINO_NUM_THREADS=4
OPENVINO_CACHE_DIR=/tmp/openvino_cache
```

### Docker Deployment

```dockerfile
# Dockerfile additions for OpenVINO
FROM python:3.10-slim

# Install OpenVINO dependencies
RUN apt-get update && apt-get install -y \
    libgomp1 \
    ocl-icd-libopencl1 \
    && rm -rf /var/lib/apt/lists/*

# Install OpenVINO
RUN pip install openvino openvino-dev[pytorch,onnx]

# Set OpenVINO environment
ENV OPENVINO_CACHE_DIR=/app/openvino_cache
```

### Monitoring

Track OpenVINO performance via Prometheus metrics:

```python
from prometheus_client import Histogram

openvino_inference_time = Histogram(
    "openvino_inference_seconds",
    "OpenVINO inference time",
    ["model", "device"]
)

with openvino_inference_time.labels(model="embeddings", device="CPU").time():
    result = compiled_model(input_tensor)
```

## Troubleshooting

### Issue: No GPU Detected

**Symptoms:**
- Only CPU appears in `available_devices`
- GPU plugin installed but not functional

**Solutions:**

1. **WSL2 Environment:**
   - GPU passthrough limited in WSL2
   - Use native Linux/Windows for GPU acceleration

2. **Driver Installation:**
   ```bash
   # Check Intel GPU driver
   lspci | grep -i vga

   # Install Intel compute runtime (native Linux)
   sudo apt install intel-opencl-icd
   ```

3. **OpenCL Configuration:**
   ```bash
   # Verify OpenCL
   clinfo
   ```

### Issue: Model Compilation Fails

**Symptoms:**
- `RuntimeError: Cannot compile model`
- Unsupported operations

**Solutions:**

1. **Convert model to IR format:**
   ```bash
   mo --input_model model.onnx --output_dir ./ir_model
   ```

2. **Check supported operations:**
   ```python
   from openvino.runtime import Core
   core = Core()
   # List supported ops for device
   ```

### Issue: Performance Not Improved

**Symptoms:**
- OpenVINO slower than native inference
- High CPU usage

**Solutions:**

1. **Enable model caching:**
   ```python
   config = {"CACHE_DIR": "/tmp/openvino_cache"}
   compiled = core.compile_model(model, "CPU", config)
   ```

2. **Adjust thread count:**
   ```python
   from openvino.properties import inference_num_threads
   config = {inference_num_threads: 4}
   ```

3. **Use appropriate performance hints:**
   ```python
   # Latency for single requests
   # Throughput for batch processing
   ```

## Validation Tests

Run OpenVINO validation suite:

```bash
# All OpenVINO tests
python -m pytest tests/openvino/ -v

# Specific test categories
python -m pytest tests/openvino/ -k "device_detection"
python -m pytest tests/openvino/ -k "model_compilation"
python -m pytest tests/openvino/ -k "benchmark"
```

## Security Considerations

1. **Model Caching:** Ensure cache directory has appropriate permissions
2. **Resource Limits:** Set thread limits to prevent CPU exhaustion
3. **Input Validation:** Validate model inputs to prevent inference attacks
4. **Model Integrity:** Verify model checksums before loading

## Future Enhancements

1. **NPU Integration:** Full Intel NPU support for Core Ultra processors
2. **Dynamic Quantization:** INT8/INT4 quantization for faster inference
3. **Model Optimization Tool:** Automated model conversion and optimization
4. **GPU Memory Management:** Efficient GPU memory allocation

## References

- [OpenVINO Documentation](https://docs.openvino.ai/)
- [LangChain OpenVINO Integration](https://python.langchain.com/docs/integrations/text_embedding/openvino)
- [Intel OpenVINO GitHub](https://github.com/openvinotoolkit/openvino)
- [AutoBot Issue #53](https://github.com/mrveiss/AutoBot-AI/issues/53)

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-11-16 | Initial documentation (Issue #53) |
