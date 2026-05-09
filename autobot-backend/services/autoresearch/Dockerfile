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
RUN pip install --no-cache-dir numpy torch --extra-index-url https://download.pytorch.org/whl/cpu

# Copy the experiment entrypoint.  The train script itself is provided at
# runtime via a read-only volume mount at /experiment.
COPY run_experiment.py /experiment/run_experiment.py

# Output directory must exist so the writable volume mount succeeds.
RUN mkdir -p /output

ENTRYPOINT ["python", "run_experiment.py"]
