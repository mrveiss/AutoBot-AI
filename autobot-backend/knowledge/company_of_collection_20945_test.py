# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""company_of_collection parses the id strictly from logical and stored names (#20945)."""

import uuid

from knowledge.backends.async_chromadb_adapter import _chroma_safe_name
from knowledge.graph_bucket_visibility import Viewer, collection_in_scope, company_of_collection
from knowledge.graph_buckets_fakes_20945 import ALICE

CID = str(uuid.uuid4())


def test_plain_stored_and_logical_names_resolve():
    assert company_of_collection(f"company:{CID}") == CID
    assert company_of_collection(_chroma_safe_name(f"company:{CID}")) == CID


def test_a_suffixed_stored_collection_resolves_to_the_company():
    stored = _chroma_safe_name(f"company:{CID}:decisions")
    assert company_of_collection(stored) == CID
    assert company_of_collection(f"company:{CID}:decisions") == CID


def test_an_admins_own_suffixed_collection_is_in_scope():
    viewer = Viewer(ALICE, CID, (), False, ledger=True)
    assert collection_in_scope("tenant_admin", _chroma_safe_name(f"company:{CID}:agents"), viewer)


def test_control_first_underscore_parse_gives_the_wrong_id():
    stored = _chroma_safe_name(f"company:{CID}:agents")
    first_underscore_only = stored.replace("company_", "company:", 1).partition(":")[2].split(":", 1)[0]
    assert first_underscore_only == f"{CID}_agents" != CID


def test_a_non_company_name_is_none():
    assert company_of_collection("project_x") is None
