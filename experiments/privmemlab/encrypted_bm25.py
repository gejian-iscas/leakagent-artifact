from __future__ import annotations

import math
import time
from collections import Counter
from dataclasses import dataclass
from typing import Dict, Iterable, Sequence, Tuple

import numpy as np

from .fpdsse import ForwardPrivateKeywordIndex


@dataclass(frozen=True)
class EncryptedBM25Report:
    ids: Tuple[str, ...]
    scores: Tuple[float, ...]
    query_terms: int
    encrypted_term_searches: int
    token_bytes: int
    returned_ciphertexts: int
    returned_bytes: int
    latency_ms: float


class ForwardPrivateBM25:
    """Client-ranked BM25 over forward-private encrypted posting lists.

    The client retains document lengths and term frequencies, as is explicit in
    this prototype's leakage/state model.  The server receives one forward-
    private search token family per distinct non-empty query term and returns
    authenticated encrypted update events.  BM25 scoring happens locally.
    """

    def __init__(
        self,
        index: ForwardPrivateKeywordIndex,
        *,
        k1: float = 1.5,
        b: float = 0.75,
        epsilon: float = 0.25,
    ) -> None:
        self.index = index
        self.k1 = k1
        self.b = b
        self.epsilon = epsilon
        self._tokens: Dict[str, Counter] = {}
        self._lengths: Dict[str, int] = {}
        self._order: list[str] = []

    def upsert(self, document_id: str, tokens: Sequence[str]) -> None:
        if document_id in self._tokens:
            self.delete(document_id)
        counts = Counter(str(token) for token in tokens)
        self._tokens[document_id] = counts
        self._lengths[document_id] = len(tokens)
        self._order.append(document_id)
        # The encrypted index rejects an empty keyword.  Empty-string tokens
        # are retained in client statistics to match rank_bm25's literal
        # space-split IDF computation, but never generate a server token.
        self.index.insert(document_id, (token for token in counts if token.strip()))

    def delete(self, document_id: str) -> bool:
        if document_id not in self._tokens:
            return False
        self.index.delete(document_id)
        del self._tokens[document_id]
        del self._lengths[document_id]
        self._order.remove(document_id)
        return True

    def search(self, query_tokens: Sequence[str], *, top_k: int) -> EncryptedBM25Report:
        started = time.perf_counter_ns()
        if not self._order:
            return EncryptedBM25Report((), (), len(query_tokens), 0, 0, 0, 0, 0.0)
        posting_lists: Dict[str, set[str]] = {}
        token_bytes = ciphertexts = returned_bytes = searches = 0
        for token in dict.fromkeys(str(value) for value in query_tokens):
            if not token.strip():
                continue
            posting_lists[token] = self.index.search(token)
            searches += 1
            stats = self.index.last_search_stats
            if stats is not None:
                token_bytes += stats.token_bytes
                ciphertexts += stats.returned_ciphertexts
                returned_bytes += stats.returned_bytes

        idf = self._idf()
        average_length = sum(self._lengths.values()) / len(self._lengths)
        scores = np.zeros(len(self._order), dtype=np.float64)
        positions = {document_id: index for index, document_id in enumerate(self._order)}
        for token in query_tokens:
            token = str(token)
            if not token.strip():
                # Empty query tokens are intentionally ignored because they
                # cannot be represented by the encrypted keyword primitive.
                continue
            term_idf = idf.get(token, 0.0)
            for document_id in posting_lists.get(token, ()):
                term_frequency = self._tokens[document_id][token]
                length = self._lengths[document_id]
                denominator = term_frequency + self.k1 * (
                    1.0 - self.b + self.b * length / average_length
                )
                scores[positions[document_id]] += term_idf * (
                    term_frequency * (self.k1 + 1.0) / denominator
                )
        ranking = np.argsort(scores)[::-1][: min(top_k, len(self._order))]
        elapsed = (time.perf_counter_ns() - started) / 1_000_000.0
        return EncryptedBM25Report(
            ids=tuple(self._order[index] for index in ranking),
            scores=tuple(float(scores[index]) for index in ranking),
            query_terms=len(query_tokens),
            encrypted_term_searches=searches,
            token_bytes=token_bytes,
            returned_ciphertexts=ciphertexts,
            returned_bytes=returned_bytes,
            latency_ms=elapsed,
        )

    def _idf(self) -> Dict[str, float]:
        document_frequency: Counter = Counter()
        for tokens in self._tokens.values():
            document_frequency.update(tokens.keys())
        document_count = len(self._tokens)
        values = {
            token: math.log(document_count - frequency + 0.5)
            - math.log(frequency + 0.5)
            for token, frequency in document_frequency.items()
        }
        if not values:
            return values
        average_idf = sum(values.values()) / len(values)
        floor = self.epsilon * average_idf
        return {
            token: (floor if value < 0 else value)
            for token, value in values.items()
        }

    @property
    def document_count(self) -> int:
        return len(self._order)

    @property
    def server_storage_bytes(self) -> int:
        return self.index.server_storage_bytes

    @property
    def client_state_bytes(self) -> int:
        token_state = sum(
            len(document_id.encode("utf-8"))
            + sum(len(token.encode("utf-8")) + 8 for token in counts)
            for document_id, counts in self._tokens.items()
        )
        return self.index.client_state_bytes + token_state + 8 * len(self._lengths)
