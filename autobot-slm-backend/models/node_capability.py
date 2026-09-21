# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-node LLM hardware capability profile (#15495).

SQLAlchemy Core, not an ORM class on ``models.database.Base``, for two
independent reasons:

* ``models/database.py`` sits at its file-size ratchet ceiling
  (``repo_tests/python_file_size_ratchet_baseline.py``), so a new concept
  cannot become a new column there -- the same move ``service_status.py``
  made for the same reason (#16019).
* The SLM test suite's ``conftest.py`` stubs ``models.database`` globally
  (#13084's ``models``/``services``/``api`` name collision with
  ``autobot-backend``), so a ``class X(Base):`` statement here would try to
  subclass a mock instance at collection time. A Core ``Table`` needs no such
  inheritance; ``conftest.py`` loads this module by path into ``sys.modules``
  the same way it already does for ``models/gpu_schemas.py``.

Rows are upserted by ``services/node_capability.py`` from the same heartbeat
``extra_data`` GPU telemetry already flows through (``services/node_gpu.py``,
#16280) -- no new side-channel. Every column is nullable and NULL means "no
updated agent has reported yet", never a fabricated 0 (#15495 AC7).
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, MetaData, String, Table

metadata = MetaData()

node_capability_profiles = Table(
    "node_capability_profiles",
    metadata,
    Column("node_id", String(64), ForeignKey("nodes.node_id", ondelete="CASCADE"), primary_key=True),
    Column("total_ram_mb", Integer, nullable=True),
    Column("total_vram_mb", Integer, nullable=True),
    Column("gpu_present", Boolean, nullable=True),
    Column("gpu_model", String(255), nullable=True),
    Column("npu_present", Boolean, nullable=True),
    Column("free_disk_model_dir_mb", Integer, nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
)
