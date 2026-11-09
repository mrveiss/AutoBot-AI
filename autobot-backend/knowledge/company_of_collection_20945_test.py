# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""company_of_collection parses exactly the names llc.kb.collections produces, logical and stored (#20945)."""

import uuid

import pytest

from knowledge.backends.async_chromadb_adapter import _chroma_safe_name
from knowledge.graph_bucket_visibility import Viewer, collection_in_scope, company_of_collection
from knowledge.graph_buckets_fakes_20945 import ALICE
from llc.kb.collections import KbCollectionManager, company_collection

CID = str(uuid.uuid4())
SUFFIXES = (None, KbCollectionManager.AGENTS_SUFFIX, KbCollectionManager.DECISIONS_SUFFIX)


@pytest.mark.parametrize("suffix", SUFFIXES)
@pytest.mark.parametrize("company_id", [CID, "tenant-a"])
def test_every_name_the_llc_layer_produces_resolves_in_both_forms(company_id, suffix):
    logical = company_collection(company_id, suffix)
    assert company_of_collection(logical) == company_id
    assert company_of_collection(_chroma_safe_name(logical)) == company_id


def test_an_admins_own_suffixed_collection_is_in_scope_and_anothers_is_not():
    viewer = Viewer(ALICE, CID, (), False, ledger=True)
    own = _chroma_safe_name(company_collection(CID, "agents"))
    other = _chroma_safe_name(company_collection(str(uuid.uuid4()), "agents"))
    assert collection_in_scope("tenant_admin", own, viewer)
    assert not collection_in_scope("tenant_admin", other, viewer)


def test_a_prefix_of_the_viewers_id_is_not_the_viewers_company():
    viewer = Viewer(ALICE, "tenant-a", (), False, ledger=True)
    assert not collection_in_scope("tenant_admin", "company:tenant-ab", viewer)
    assert not collection_in_scope("tenant_admin", "company_tenant-ab_agents", viewer)


@pytest.mark.parametrize(
    "name",
    [
        "xcompany_1",  # prefix is not at the start
        "xcompany:1",
        "company_",  # no id
        "company:",
        "company__agents",  # empty id
        "company::agents",
        "Company:1",  # case-sensitive
        "company:a_b",  # '_' cannot be in an id: ambiguous once stored
        "company:a.b",
        "company_a.b",
        "company:a b",
        f"company:{CID}\n",  # trailing newline must not match
        f"company_{CID}\n",
        f"company:{CID}:agents\n",
        "companyx_1",
        "company-1",
        "project_x",
        "",
    ],
)
def test_control_lookalikes_do_not_parse(name):
    assert company_of_collection(name) is None


def test_control_first_underscore_parse_gives_the_wrong_id():
    stored = _chroma_safe_name(company_collection(CID, "agents"))
    naive = stored.partition("_")[2]
    assert naive == f"{CID}_agents" != CID
    assert company_of_collection(stored) == CID
