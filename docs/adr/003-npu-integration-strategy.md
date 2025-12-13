# ADR-003: NPU Hardware Acceleration Integration

## Status

**Status**: Accepted

## Date

**Date**: 2025-01-01

## Context

AutoBot performs various AI workloads:
- LLM inference (chat completions)
- Embedding generation (knowledge base)
- Image analysis (multi-modal features)
- Speech processing (voice features)

CPU-based inference is slow and expensive. GPU acceleration is common but:
1. **Power consumption**: GPUs draw significant power
2. **Cost**: High-end GPUs are expensive
3. **Availability**: Often shared/contended resources

Intel NPUs (Neural Processing Units) offer an alternative:
- Lower power consumption
- Dedicated AI acceleration
- Available in modern Intel CPUs
- No GPU memory limitations

## Decision

We create a dedicated NPU Worker VM (VM2: 172.16.168.22) that:
1. Has direct hardware passthrough to the Intel NPU
2. Runs OpenVINO for model optimization
3. Exposes an HTTP API for AI inference requests
4. Handles embedding generation and local model inference

The main backend routes appropriate workloads to the NPU worker.

### Alternatives Considered

1. **GPU Acceleration Only**
   - Pros: Well-supported, high throughput
   - Cons: Power hungry, expensive, memory limited

2. **CPU Only**
   - Pros: No special hardware needed
   - Cons: Slow, high latency for real-time features

3. **Cloud AI Services (OpenAI, etc.)**
   - Pros: No hardware management, scalable
   - Cons: Latency, cost, privacy concerns, requires internet

4. **NPU + Fallback to Cloud (Chosen)**
   - Pros: Fast local inference, privacy-preserving, cost-effective
   - Cons: Limited model support, requires OpenVINO optimization

## Consequences

### Positive

- **Low Latency**: Local inference without network round-trip
- **Privacy**: Sensitive data stays on-premises
- **Cost Effective**: No per-request API costs
- **Power Efficient**: NPU uses less power than GPU
- **Dedicated Resource**: No contention with other workloads

### Negative

- **Model Compatibility**: Not all models support OpenVINO
- **Setup Complexity**: Requires driver installation and OpenVINO
- **Hardware Specific**: Tied to Intel NPU availability
- **Limited Throughput**: NPU has lower peak throughput than high-end GPU

### Neutral

- Requires fallback to cloud for unsupported models
- Model optimization step needed for best performance

## Implementation Notes

### Key Files

- `scripts/utilities/npu_worker_design.py` - NPU worker architecture design
- `backend/services/npu_client.py` - Client for NPU worker API
- VM2 runs the NPU worker service on port 8081

### Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Backend API    │────▶│   NPU Worker     │────▶│  Intel NPU      │
│  (172.16.168.20)│     │  (172.16.168.22) │     │  Hardware       │
└─────────────────┘     └──────────────────┘     └─────────────────┘
         │
         ▼ (fallback)
┌─────────────────┐
│  Cloud API      │
│  (OpenAI, etc.) │
└─────────────────┘
```

### NPU Worker API

```python
# Health check
GET http://172.16.168.22:8081/health

# Embedding generation
POST http://172.16.168.22:8081/embeddings
{
    "texts": ["text to embed"],
    "model": "bge-small-en"
}

# Inference
POST http://172.16.168.22:8081/inference
{
    "prompt": "...",
    "model": "llama-7b-openvino"
}
```

### Fallback Strategy

```python
async def generate_embedding(text: str) -> List[float]:
    try:
        # Try NPU first
        return await npu_client.embed(text)
    except NPUUnavailableError:
        # Fallback to cloud
        return await openai_client.embed(text)
```

### OpenVINO Model Optimization

```bash
# Convert model to OpenVINO format
optimum-cli export openvino \
    --model BAAI/bge-small-en-v1.5 \
    --task feature-extraction \
    bge-small-openvino/
```

## Related ADRs

- [ADR-001](001-distributed-vm-architecture.md) - NPU worker is VM2 in distributed architecture

---

**Author**: mrveiss
**Copyright**: © 2025 mrveiss
