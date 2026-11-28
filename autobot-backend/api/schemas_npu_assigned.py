# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Schemas for GET /npu/assigned-unpaired-workers (#19706)."""

from typing import List

from pydantic import BaseModel


class AssignedWorker(BaseModel):
    """A node the SLM assigned npu-worker with no paired worker."""

    url: str
    hostname: str


class AssignedWorkersResponse(BaseModel):
    workers: List[AssignedWorker]
