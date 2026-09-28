from __future__ import annotations

import csv
import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Tuple


@dataclass(frozen=True)
class ServerTraceEvent:
    session_id: str
    step: int
    search_pattern: str
    access_pattern: Tuple[str, ...]
    response_size: int
    delta_ms: float
    update_visible: bool
    mode: str

    @classmethod
    def from_handles(
        cls,
        *,
        session_id: str,
        step: int,
        search_pattern: str,
        handles: Iterable[str],
        delta_ms: float,
        update_visible: bool = False,
        mode: str = "lexical",
    ) -> "ServerTraceEvent":
        access = tuple(
            sorted(hashlib.sha256(handle.encode("utf-8")).hexdigest()[:20] for handle in handles)
        )
        return cls(
            session_id=session_id,
            step=step,
            search_pattern=search_pattern,
            access_pattern=access,
            response_size=len(access),
            delta_ms=delta_ms,
            update_visible=update_visible,
            mode=mode,
        )


class TraceRecorder:
    def __init__(self):
        self._events: List[ServerTraceEvent] = []

    def append(self, event: ServerTraceEvent) -> None:
        if self._events and event.session_id == self._events[-1].session_id:
            if event.step != self._events[-1].step + 1:
                raise ValueError("trace steps must be contiguous within a session")
        self._events.append(event)

    @property
    def events(self) -> Tuple[ServerTraceEvent, ...]:
        return tuple(self._events)

    def write_csv(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "session_id",
                    "step",
                    "search_pattern",
                    "access_pattern",
                    "response_size",
                    "delta_ms",
                    "update_visible",
                    "mode",
                ],
            )
            writer.writeheader()
            for event in self._events:
                row = asdict(event)
                row["access_pattern"] = "|".join(event.access_pattern)
                writer.writerow(row)
