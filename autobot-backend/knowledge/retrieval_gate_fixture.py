# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Deterministic fixture retriever for the retrieval gate (#20949).

Ranks ``benchmarks/gold/fixture_corpus.jsonl`` with a lexical (token overlap,
"bm25" toggle) and a character-trigram (stands in for "dense") score, summed
when both are on ("fusion"). It exists so CI can run the gate with no index,
model or network. It produces no answer text, so grounding is unmeasured here.
"""

from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Mapping, Set

from knowledge.retrieval_gate import RETRIEVAL_GATE_GOLD_DIR, GoldQuery, RetrievalOutput

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> Set[str]:
    return set(_TOKEN.findall(text.lower()))


def _trigrams(text: str) -> Set[str]:
    t = re.sub(r"\s+", " ", text.lower())
    return {t[i : i + 3] for i in range(len(t) - 2)}


def _jaccard(a: Set[str], b: Set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def load_corpus(directory: str = RETRIEVAL_GATE_GOLD_DIR) -> Dict[str, str]:
    """Return {doc_id: text} from the shipped fixture corpus."""
    with open(os.path.join(directory, "fixture_corpus.jsonl"), encoding="utf-8") as fh:
        return {r["id"]: r["text"] for r in map(json.loads, filter(str.strip, fh))}


def factory():
    """Retriever factory for ``--retriever knowledge.retrieval_gate_fixture:factory``."""
    corpus = load_corpus()

    def retrieve(query: GoldQuery, toggles: Mapping[str, bool], k: int) -> RetrievalOutput:
        q_tok, q_tri = _tokens(query.query), _trigrams(query.query)
        scored = []
        for doc_id, text in corpus.items():
            score = 0.0
            if toggles.get("bm25"):
                score += _jaccard(q_tok, _tokens(text))
            if toggles.get("dense"):
                score += _jaccard(q_tri, _trigrams(text))
            scored.append((-score, doc_id))
        scored.sort()
        ranked: List[str] = [d for s, d in scored if s != 0][:k]
        return RetrievalOutput(ranked, [corpus[d] for d in ranked], None)

    return retrieve
