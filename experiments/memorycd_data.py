"""MemoryCD parsing and tokenization extracted unchanged from the collection code."""

from __future__ import annotations

import json, re

from typing import Any

DOMAINS = (
    "Beauty_and_Personal_Care",
    "Books",
    "Electronics",
    "Home_and_Kitchen",
)

def parse_interactions(row: dict[str, Any]) -> list[dict[str, Any]]:
    interactions: list[dict[str, Any]] = []
    source_ordinal = 0
    for domain in DOMAINS:
        for encoded in row["interactions"][domain]:
            item = json.loads(encoded)
            timestamp = item.get("timestamp")
            if isinstance(timestamp, int) and item.get("title") and item.get("text"):
                interactions.append(
                    {
                        "record_id": f"{row['user_id']}:{source_ordinal}",
                        "source_ordinal": source_ordinal,
                        "domain": domain,
                        "timestamp": timestamp,
                        "asin": str(item.get("asin", "")),
                        "parent_asin": str(item.get("parent_asin", "")),
                        "review_title": str(item["title"]),
                        "review_text": str(item["text"]),
                    }
                )
            source_ordinal += 1
    interactions.sort(
        key=lambda item: (
            item["timestamp"],
            item["domain"],
            item["parent_asin"],
            item["asin"],
            item["source_ordinal"],
        )
    )
    return interactions

TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{1,63}")

def terms(text: str) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for token in TOKEN.findall(text.casefold()):
        if token not in seen:
            output.append(token)
            seen.add(token)
    return output
