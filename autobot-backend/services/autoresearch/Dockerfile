# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
#
# Slim experiment runner image for AutoResearch Docker isolation.
# Built and pushed to ghcr.io/mrveiss/autobot-autoresearch by CI.
# No AutoBot backend code is included — experiment deps only.

FROM python:3.14-slim

WORKDIR /experiment

# Install minimal runtime dependencies for experiment scripts.
# numpy and torch-cpu cover the typical nanoGPT training baseline.
# #11039: retry torch install — download.pytorch.org intermittently drops the
# TLS handshake; assert the import so an exhausted retry loop still fails the build.
RUN for i in 1 2 3 4 5; do \
        pip install --no-cache-dir --retries 5 --timeout 120 \
            numpy torch --extra-index-url https://download.pytorch.org/whl/cpu \
        && break; \
        echo "torch install attempt $i failed (network/TLS); retrying in $((i*10))s..."; \
        sleep $((i*10)); \
    done \
    && python3 -c "import torch, numpy"

# Copy the experiment entrypoint.  The train script itself is provided at
# runtime via a read-only volume mount at /experiment.
COPY run_experiment.py /experiment/run_experiment.py

# Output directory must exist so the writable volume mount succeeds.
RUN mkdir -p /output

ENTRYPOINT ["python", "run_experiment.py"]
