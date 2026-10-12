# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""MinHash-LSH candidate search for the duplicate detector (#659, #665, #18067).

Moved out of ``duplicate_detector.py`` (grandfathered at its size ceiling) and
corrected there, because the version that lived in it could not finish on a
tree the size of AutoBot's own:

* **The threshold ignored the caller.** LSH was built at a hardcoded 0.5 whatever
  ``min_similarity`` was, so the advice every timeout response gave -- "try a
  higher min_similarity" -- changed the answer but not the work.
* **Tiny blocks matched everything.** Half of the 130,000 blocks extracted from
  this repository have 17 distinct tokens or fewer. Token-set Jaccard on sets
  that small reaches 0.5 by coincidence, so 3.9 million candidate pairs came
  back and 2.5 million were reported as "duplicates" -- a result no panel can
  show, produced after 9 minutes. Blocks under ``MIN_TOKENS_FOR_SIMILARITY``
  distinct tokens still match by EXACT hash; they are only left out of the
  fuzzy pass. That is a stated boundary of the detector, not a silent one.
* **MinHash was built token by token** (one numpy call per token). It is one
  ``update_batch`` call per block now.

Blocks are duck-typed (``token_set``, ``normalized_content``) and the exact
similarity is injected, so this module does not import the detector it serves.
"""

from typing import Any, Callable, Dict, List, Sequence, Set, Tuple

from autobot_shared.logging_manager import get_logger

try:
    from datasketch import MinHash, MinHashLSH

    LSH_AVAILABLE = True
except ImportError:
    LSH_AVAILABLE = False
    MinHash = Any  # type: ignore[misc, assignment]
    MinHashLSH = Any  # type: ignore[misc, assignment]

logger = get_logger(__name__)

LSH_NUM_PERMUTATIONS = 128  # Higher = more precision, slower. 128=~95% recall, 256=~98%

#: Distinct tokens a block needs to take part in the FUZZY pass. Measured on this
#: repository: 20 keeps 55k of 130k blocks and turns 668k candidate pairs into
#: 26.6k real ones at 0.5 (3.9M / 2.5M without it). Exact-hash matching is not
#: affected.
MIN_TOKENS_FOR_SIMILARITY = 20

#: How often the long phases consult the cancel token (#13602).
CANCEL_CHECK_INTERVAL = 500

_THRESHOLD_FLOOR = 0.05  # MinHashLSH rejects 0, and 0 would make every pair a candidate

#: MinHash-LSH retrieves a pair at Jaccard == threshold only ~50% of the time
#: (measured with datasketch's own banding at 128 permutations: 0.55 at 0.5/0.5,
#: 0.44 at 0.7/0.7). Building the index AT ``min_similarity`` therefore misses
#: half of the pairs the caller asked for at the edge. Indexing ``MARGIN`` lower
#: lifts recall to ~87% at the edge and ~99% from 0.1 above it, and the exact
#: similarity check afterwards removes the extra candidates. Measured cost on this
#: repository at 0.5: 8.4M candidates, ~57s -- the price of recall, not of the bug.
LSH_RECALL_MARGIN = 0.1

Similarity = Callable[[Any, Any], float]


def eligible_indices(blocks: Sequence[Any]) -> List[int]:
    """Indices of the blocks large enough for the fuzzy pass."""
    return [i for i, b in enumerate(blocks) if len(_tokens(b)) >= MIN_TOKENS_FOR_SIMILARITY]


def _tokens(block: Any) -> Set[str]:
    return block.token_set if block.token_set else set(block.normalized_content.split())


def build_minhash(token_set: Set[str], num_perm: int = LSH_NUM_PERMUTATIONS) -> "MinHash":
    """MinHash signature for a token set, in one vectorised call."""
    m = MinHash(num_perm=num_perm)
    m.update_batch([token.encode("utf-8") for token in token_set])
    return m


def build_signatures(
    blocks: Sequence[Any],
    indices: Sequence[int],
    num_perm: int,
    cancelled: "Callable[[], bool] | None" = None,
) -> Dict[int, "MinHash"]:
    """Signatures for ``indices``; stops early when ``cancelled`` (#13602)."""
    minhashes: Dict[int, MinHash] = {}
    for n, idx in enumerate(indices):
        if cancelled is not None and n % CANCEL_CHECK_INTERVAL == 0 and cancelled():
            logger.info("MinHash signature build cancelled at %d/%d blocks", n, len(indices))
            return minhashes
        minhashes[idx] = build_minhash(_tokens(blocks[idx]), num_perm)
    return minhashes


def build_index(minhashes: Dict[int, "MinHash"], threshold: float, num_perm: int) -> "MinHashLSH":
    """LSH index over ``minhashes`` at ``threshold``."""
    lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
    for idx, mh in minhashes.items():
        try:
            lsh.insert(str(idx), mh)
        except ValueError:
            pass  # duplicate key: identical blocks, already represented
    return lsh


def query_candidates(
    blocks: Sequence[Any],
    minhashes: Dict[int, "MinHash"],
    lsh: "MinHashLSH",
    similarity: Similarity,
    min_similarity: float,
    cancelled: "Callable[[], bool] | None" = None,
) -> List[Tuple[int, int, float]]:
    """(idx1, idx2, exact_similarity) for LSH candidates that really clear ``min_similarity``."""
    candidates: List[Tuple[int, int, float]] = []
    seen: Set[Tuple[int, int]] = set()
    for n, (idx, mh) in enumerate(minhashes.items()):
        if cancelled is not None and n % CANCEL_CHECK_INTERVAL == 0 and cancelled():
            logger.info("LSH query cancelled at %d/%d blocks", n, len(minhashes))
            return candidates
        for key in lsh.query(mh):
            other = int(key)
            pair = (min(idx, other), max(idx, other))
            if other == idx or pair in seen:
                continue
            seen.add(pair)
            exact = similarity(blocks[idx], blocks[other])
            if exact >= min_similarity:
                candidates.append((idx, other, exact))
    return candidates


def find_lsh_candidates(
    blocks: Sequence[Any],
    similarity: Similarity,
    min_similarity: float,
    num_perm: int = LSH_NUM_PERMUTATIONS,
    cancelled: "Callable[[], bool] | None" = None,
) -> List[Tuple[int, int, float]]:
    """Cross-checked near-duplicate pairs among the blocks eligible for the fuzzy pass.

    The index is built ``LSH_RECALL_MARGIN`` below ``min_similarity`` (clamped), so a
    higher threshold does less work, which is what every timeout message tells the
    caller to try.
    """
    if not LSH_AVAILABLE:
        logger.warning("datasketch not available, falling back to O(n²) comparison")
        return []
    eligible = eligible_indices(blocks)
    if len(eligible) < 2:
        return []
    threshold = round(min(1.0, max(_THRESHOLD_FLOOR, min_similarity - LSH_RECALL_MARGIN)), 2)
    logger.info(
        "Building LSH index for %d of %d blocks (>= %d tokens; num_perm=%d, threshold=%.2f)",
        len(eligible),
        len(blocks),
        MIN_TOKENS_FOR_SIMILARITY,
        num_perm,
        threshold,
    )
    minhashes = build_signatures(blocks, eligible, num_perm, cancelled=cancelled)
    if cancelled is not None and cancelled():
        return []
    lsh = build_index(minhashes, threshold, num_perm)
    found = query_candidates(blocks, minhashes, lsh, similarity, min_similarity, cancelled=cancelled)
    logger.info("LSH found %d near-duplicate pairs from %d eligible blocks", len(found), len(eligible))
    return found
