# AutoBot NPU Worker - Intel NPU Accelerated Inference
# High-performance AI inference using Intel NPU hardware

FROM python:3.10.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies for NPU support
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    cmake \
    pkg-config \
    # Intel Graphics dependencies for NPU driver support
    intel-gpu-tools \
    vainfo \
    # OpenVINO dependencies
    libtbb-dev \
    libtbb12 \
    # OpenCL for NPU acceleration
    ocl-icd-libopencl1 \
    opencl-headers \
    clinfo \
    # Intel NPU driver dependencies
    git-lfs \
    && rm -rf /var/lib/apt/lists/*

# Install Intel NPU driver in container
RUN git clone https://github.com/intel/linux-npu-driver.git /tmp/npu-driver && \
    cd /tmp/npu-driver && \
    git submodule update --init --recursive && \
    cmake -B build -S . && \
    cmake --build build --parallel $(nproc) && \
    cmake --install build && \
    ldconfig && \
    rm -rf /tmp/npu-driver

# Create app directories
RUN mkdir -p /app/src /app/data /app/models /app/logs

# Copy NPU worker requirements
COPY docker/npu-worker/requirements-npu.txt /app/
RUN pip install --no-cache-dir -r requirements-npu.txt

# Copy NPU worker source code
COPY docker/npu-worker/npu_worker_main.py /app/
COPY docker/npu-worker/npu_inference_server.py /app/
COPY docker/npu-worker/npu_model_manager.py /app/
COPY src/agents/base_agent.py /app/src/agents/
COPY src/autobot_types.py /app/src/

# Copy shared source code (read-only)
COPY src/config.py /app/src/
COPY src/llm_providers/ /app/src/llm_providers/

# Set environment variables
ENV NPU_WORKER_HOST=0.0.0.0
ENV NPU_WORKER_PORT=8081
ENV NPU_WORKER_WORKERS=1
ENV OPENVINO_DEVICE=NPU
ENV OV_LOG_LEVEL=ERROR
ENV PYTHONPATH=/app:/app/src

# Expose NPU worker port
EXPOSE 8081

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8081/health || exit 1

# Start NPU worker
CMD ["python", "npu_worker_main.py"]
