"""Epoch-rotating forward-private dynamic encrypted keyword index.

Updates issued after a search use a fresh per-keyword epoch key. A server that
has observed earlier search tokens can enumerate the corresponding historical
epochs, but cannot derive the address key for a future epoch. Search downloads
encrypted add/delete events and reconstructs the live posting set locally.

This module is a research prototype for the PrivateMem method. Its leakage is
explicit: search pattern, number of searched epochs, per-epoch update counts,
ciphertext lengths, and returned encrypted-event count.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Set, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


@dataclass(frozen=True)
class EpochSearchToken:
    epoch: int
    address_key: bytes
    update_count: int


@dataclass(frozen=True)
class EncryptedSearchStats:
    pattern: str
    epochs: int
    token_bytes: int
    returned_ciphertexts: int
    returned_bytes: int


@dataclass(frozen=True)
class CompactionStats:
    entries_before: int
    entries_after: int
    storage_bytes_before: int
    storage_bytes_after: int
    live_handles: int
    live_postings: int


class InjectedCompactionCrash(RuntimeError):
    """Raised after a registered durable compaction prefix."""


@dataclass
class _EpochState:
    epoch: int
    address_key: bytes
    update_count: int = 0


class EncryptedUpdateServer:
    """Untrusted storage surface used by the local protocol simulation."""

    def __init__(self) -> None:
        self._entries: Dict[bytes, bytes] = {}

    def put(self, address: bytes, ciphertext: bytes) -> None:
        if address in self._entries:
            raise RuntimeError("encrypted update address collision")
        self._entries[address] = ciphertext

    def lookup(self, tokens: Iterable[EpochSearchToken]) -> list[tuple[bytes, bytes]]:
        result: list[tuple[bytes, bytes]] = []
        for token in tokens:
            for counter in range(1, token.update_count + 1):
                address = ForwardPrivateKeywordIndex.address_for(
                    token.address_key, counter
                )
                ciphertext = self._entries.get(address)
                if ciphertext is not None:
                    result.append((address, ciphertext))
        return result

    def replace(
        self,
        old_addresses: Iterable[bytes],
        new_entries: Iterable[tuple[bytes, bytes]],
    ) -> None:
        """Atomically replace a complete encrypted-event generation."""

        replacement = dict(self._entries)
        for address in old_addresses:
            replacement.pop(address, None)
        for address, ciphertext in new_entries:
            if address in replacement:
                raise RuntimeError("encrypted compaction address collision")
            replacement[address] = ciphertext
        self._entries = replacement

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    @property
    def storage_bytes(self) -> int:
        return sum(len(address) + len(ciphertext) for address, ciphertext in self._entries.items())

    @property
    def addresses(self) -> Tuple[bytes, ...]:
        return tuple(self._entries)

    @property
    def entries(self) -> Tuple[tuple[bytes, bytes], ...]:
        return tuple(self._entries.items())


class ForwardPrivateKeywordIndex:
    """Dynamic encrypted index with search-triggered per-keyword key rotation."""

    def __init__(
        self,
        epoch_master_key: bytes,
        payload_key: bytes,
        pattern_key: bytes,
        *,
        server: EncryptedUpdateServer | None = None,
    ) -> None:
        for name, key in (
            ("epoch_master_key", epoch_master_key),
            ("payload_key", payload_key),
            ("pattern_key", pattern_key),
        ):
            if len(key) < 16:
                raise ValueError(f"{name} must be at least 16 bytes")
        self._epoch_master_key = epoch_master_key
        self._payload_key = payload_key[:32]
        self._payload_cipher = AESGCM(self._payload_key)
        self._pattern_key = pattern_key
        self._server = server or EncryptedUpdateServer()
        self._epochs: Dict[str, list[_EpochState]] = {}
        self._generations: Dict[str, int] = {}
        self._handle_terms: Dict[str, Set[str]] = {}
        self._sequence = 0
        self._last_tokens: Tuple[EpochSearchToken, ...] = ()
        self._last_stats: EncryptedSearchStats | None = None

    @staticmethod
    def normalize(keyword: str) -> str:
        normalized = keyword.strip().casefold()
        if not normalized:
            raise ValueError("keywords must be non-empty")
        return normalized

    @staticmethod
    def address_for(address_key: bytes, counter: int) -> bytes:
        if counter <= 0:
            raise ValueError("counter must be positive")
        return hmac.new(address_key, counter.to_bytes(8, "big"), hashlib.sha256).digest()

    def insert(self, handle: str, keywords: Iterable[str]) -> None:
        if handle in self._handle_terms:
            raise ValueError(f"duplicate index handle: {handle}")
        terms = {self.normalize(keyword) for keyword in keywords}
        self._handle_terms[handle] = terms
        for term in terms:
            self._append_event(term, "add", handle)

    def delete(self, handle: str) -> None:
        for term in self._handle_terms.pop(handle, set()):
            self._append_event(term, "del", handle)

    def search(self, keyword: str) -> Set[str]:
        term = self.normalize(keyword)
        epochs = self._epochs.get(term, [])
        tokens = tuple(
            EpochSearchToken(state.epoch, state.address_key, state.update_count)
            for state in epochs
            if state.update_count > 0
        )
        encrypted = self._server.lookup(tokens)
        events: list[tuple[int, str, str]] = []
        for address, ciphertext in encrypted:
            plaintext = self._payload_cipher.decrypt(
                self._nonce(address), ciphertext, address
            )
            event = json.loads(plaintext.decode("utf-8"))
            events.append((int(event["seq"]), str(event["op"]), str(event["handle"])))
        live: Set[str] = set()
        for _, operation, handle in sorted(events):
            if operation == "add":
                live.add(handle)
            elif operation == "del":
                live.discard(handle)
            else:  # pragma: no cover - authenticated payload invariant
                raise RuntimeError(f"unknown encrypted update operation: {operation}")

        self._last_tokens = tokens
        self._last_stats = EncryptedSearchStats(
            pattern=self.search_pattern(term),
            epochs=len(tokens),
            token_bytes=len(tokens) * (8 + 32 + 8),
            returned_ciphertexts=len(encrypted),
            returned_bytes=sum(len(address) + len(ciphertext) for address, ciphertext in encrypted),
        )
        self._rotate_after_search(term)
        return live

    def compact(self) -> CompactionStats:
        """Replace historical add/delete events with the current live postings.

        The client already retains the handle-to-term map in this prototype's
        explicit state model. New ciphertexts are prepared under fresh
        per-term generations before the server swaps the complete event set.
        """

        entries_before = self._server.entry_count
        bytes_before = self._server.storage_bytes
        old_addresses = tuple(self._server.addresses)
        live_by_term: Dict[str, list[str]] = {}
        for handle, terms in self._handle_terms.items():
            for term in terms:
                live_by_term.setdefault(term, []).append(handle)
        all_terms = set(self._epochs) | set(live_by_term)
        new_epochs: Dict[str, list[_EpochState]] = {}
        new_generations = dict(self._generations)
        new_entries: list[tuple[bytes, bytes]] = []
        for term in sorted(all_terms):
            generation = self._generations.get(term, 0) + 1
            new_generations[term] = generation
            state = self._epoch_for_generation(term, generation, 0)
            handles = sorted(live_by_term.get(term, ()))
            for handle in handles:
                state.update_count += 1
                self._sequence += 1
                address = self.address_for(state.address_key, state.update_count)
                payload = self._event_payload("add", handle)
                ciphertext = self._payload_cipher.encrypt(
                    self._nonce(address), payload, address
                )
                new_entries.append((address, ciphertext))
            new_epochs[term] = [state] if handles else []
        self._server.replace(old_addresses, new_entries)
        self._generations = new_generations
        self._epochs = new_epochs
        self._last_tokens = ()
        self._last_stats = None
        return CompactionStats(
            entries_before=entries_before,
            entries_after=self._server.entry_count,
            storage_bytes_before=bytes_before,
            storage_bytes_after=self._server.storage_bytes,
            live_handles=len(self._handle_terms),
            live_postings=sum(len(terms) for terms in self._handle_terms.values()),
        )

    def export_trusted_state(self) -> dict:
        """Serialize controller and encrypted-server state for a trusted journal.

        Key bytes appear in this trusted state image and must not be placed in
        experiment results or exposed to the untrusted storage service.
        """

        return {
            "schema_version": 1,
            "epoch_master_key": self._epoch_master_key.hex(),
            "payload_key": self._payload_key.hex(),
            "pattern_key": self._pattern_key.hex(),
            "sequence": self._sequence,
            "generations": dict(sorted(self._generations.items())),
            "epochs": {
                term: [
                    {"epoch": state.epoch, "update_count": state.update_count}
                    for state in states
                ]
                for term, states in sorted(self._epochs.items())
            },
            "handle_terms": {
                handle: sorted(terms)
                for handle, terms in sorted(self._handle_terms.items())
            },
            "server_entries": [
                {"address": address.hex(), "ciphertext": ciphertext.hex()}
                for address, ciphertext in sorted(self._server.entries)
            ],
        }

    @classmethod
    def from_trusted_state(cls, state: dict) -> "ForwardPrivateKeywordIndex":
        if int(state.get("schema_version", 0)) != 1:
            raise ValueError("unsupported FP-DSSE state schema")
        server = EncryptedUpdateServer()
        for row in state.get("server_entries", []):
            server.put(bytes.fromhex(row["address"]), bytes.fromhex(row["ciphertext"]))
        index = cls(
            bytes.fromhex(state["epoch_master_key"]),
            bytes.fromhex(state["payload_key"]),
            bytes.fromhex(state["pattern_key"]),
            server=server,
        )
        index._sequence = int(state["sequence"])
        index._generations = {
            str(term): int(generation)
            for term, generation in state.get("generations", {}).items()
        }
        index._handle_terms = {
            str(handle): {str(term) for term in terms}
            for handle, terms in state.get("handle_terms", {}).items()
        }
        index._epochs = {}
        for term, rows in state.get("epochs", {}).items():
            generation = index._generations.get(str(term), 0)
            index._epochs[str(term)] = [
                _EpochState(
                    epoch=int(row["epoch"]),
                    address_key=index._epoch_for_generation(
                        str(term), generation, int(row["epoch"])
                    ).address_key,
                    update_count=int(row["update_count"]),
                )
                for row in rows
            ]
        return index

    def search_pattern(self, keyword: str) -> str:
        term = self.normalize(keyword)
        return hmac.new(
            self._pattern_key, term.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def _append_event(self, term: str, operation: str, handle: str) -> None:
        state = self._current_epoch(term)
        state.update_count += 1
        self._sequence += 1
        address = self.address_for(state.address_key, state.update_count)
        payload = self._event_payload(operation, handle)
        ciphertext = self._payload_cipher.encrypt(
            self._nonce(address), payload, address
        )
        self._server.put(address, ciphertext)

    def _event_payload(self, operation: str, handle: str) -> bytes:
        return json.dumps(
            {"handle": handle, "op": operation, "seq": self._sequence},
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

    def _current_epoch(self, term: str) -> _EpochState:
        epochs = self._epochs.setdefault(term, [])
        if not epochs:
            epochs.append(self._new_epoch(term, 0))
        return epochs[-1]

    def _rotate_after_search(self, term: str) -> None:
        epochs = self._epochs.setdefault(term, [])
        next_epoch = epochs[-1].epoch + 1 if epochs else 0
        if not epochs or epochs[-1].update_count > 0:
            epochs.append(self._new_epoch(term, next_epoch))

    def _new_epoch(self, term: str, epoch: int) -> _EpochState:
        generation = self._generations.get(term, 0)
        return self._epoch_for_generation(term, generation, epoch)

    def _epoch_for_generation(self, term: str, generation: int, epoch: int) -> _EpochState:
        material = (
            term.encode("utf-8")
            + b"\0"
            + generation.to_bytes(8, "big")
            + epoch.to_bytes(8, "big")
        )
        key = hmac.new(self._epoch_master_key, material, hashlib.sha256).digest()
        return _EpochState(epoch=epoch, address_key=key)

    @staticmethod
    def _nonce(address: bytes) -> bytes:
        return hashlib.sha256(b"nonce" + address).digest()[:12]

    @property
    def last_search_tokens(self) -> Tuple[EpochSearchToken, ...]:
        return self._last_tokens

    @property
    def last_search_stats(self) -> EncryptedSearchStats | None:
        return self._last_stats

    @property
    def posting_count(self) -> int:
        return self._server.entry_count

    @property
    def server_storage_bytes(self) -> int:
        return self._server.storage_bytes

    @property
    def client_state_bytes(self) -> int:
        epoch_state = sum(len(states) * (32 + 16) for states in self._epochs.values())
        handle_state = sum(
            len(handle.encode("utf-8")) + sum(len(term.encode("utf-8")) for term in terms)
            for handle, terms in self._handle_terms.items()
        )
        return epoch_state + handle_state

    @property
    def server_addresses(self) -> Tuple[bytes, ...]:
        return self._server.addresses


class DurableCompactionCoordinator:
    """Copy-on-write trusted-state cutover for FP-DSSE compaction.

    A prepared candidate is fsynced separately.  The commit point is one atomic
    rename of that candidate over the active state image.  Recovery discards an
    uncommitted candidate and loads whichever complete active image survived.
    """

    CRASH_POINTS = ("after_prepare", "after_commit")

    def __init__(self, directory: Path | str) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.active_path = self.directory / "active-state.json"
        self.pending_path = self.directory / "pending-compaction.json"

    def initialize(self, index: ForwardPrivateKeywordIndex) -> None:
        if self.active_path.exists():
            raise FileExistsError(self.active_path)
        self._write_fsynced(self.active_path, index.export_trusted_state())
        self._fsync_directory()

    def recover(self) -> ForwardPrivateKeywordIndex:
        if not self.active_path.exists():
            raise FileNotFoundError(self.active_path)
        if self.pending_path.exists():
            self.pending_path.unlink()
            self._fsync_directory()
        return ForwardPrivateKeywordIndex.from_trusted_state(
            json.loads(self.active_path.read_text(encoding="utf-8"))
        )

    def compact(
        self, *, crash_at: str | None = None
    ) -> tuple[ForwardPrivateKeywordIndex, CompactionStats]:
        if crash_at is not None and crash_at not in self.CRASH_POINTS:
            raise ValueError(f"unknown compaction crash point: {crash_at}")
        candidate = self.recover()
        report = candidate.compact()
        self._write_fsynced(self.pending_path, candidate.export_trusted_state())
        self._fsync_directory()
        if crash_at == "after_prepare":
            raise InjectedCompactionCrash(crash_at)
        os.replace(self.pending_path, self.active_path)
        self._fsync_directory()
        if crash_at == "after_commit":
            raise InjectedCompactionCrash(crash_at)
        return candidate, report

    @staticmethod
    def _write_fsynced(path: Path, body: dict) -> None:
        with path.open("w", encoding="utf-8") as stream:
            json.dump(body, stream, separators=(",", ":"), sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())

    def _fsync_directory(self) -> None:
        descriptor = os.open(self.directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
