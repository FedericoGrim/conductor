"""List candidate models per privacy level from an OpenRouter-compatible /models endpoint.

Usage: python scripts/list-models.py --privacy low|medium|high [--limit 30]
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from typing import Any

ENDPOINTS = {
    "low": "https://openrouter.ai/api/v1/models",
    "medium": "https://openrouter.ai/api/v1/models",
    "high": "https://eu.openrouter.ai/api/v1/models",
}


def fetch(url: str) -> list[dict[str, Any]]:
    with urllib.request.urlopen(url, timeout=60) as response:
        data: list[dict[str, Any]] = json.loads(response.read())["data"]
        return data


def per_million(price: str | None) -> float:
    return float(price or 0) * 1_000_000


def candidates(models: list[dict[str, Any]], privacy: str) -> list[dict[str, Any]]:
    rows = []
    for model in models:
        if "tools" not in model.get("supported_parameters", []):
            continue
        prompt = per_million(model.get("pricing", {}).get("prompt"))
        completion = per_million(model.get("pricing", {}).get("completion"))
        free = prompt == 0 and completion == 0
        if (privacy == "low") != free:
            continue
        rows.append(
            {
                "id": model["id"],
                "prompt": prompt,
                "completion": completion,
                "context": model.get("context_length", 0),
            }
        )
    return sorted(rows, key=lambda r: (r["completion"], r["prompt"]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--privacy", choices=ENDPOINTS, required=True)
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    rows = candidates(fetch(ENDPOINTS[args.privacy]), args.privacy)[: args.limit]
    print(f"{'model':60} {'$/M in':>8} {'$/M out':>8} {'context':>9}")
    for row in rows:
        print(f"{row['id']:60} {row['prompt']:8.3f} {row['completion']:8.3f} {row['context']:9}")


if __name__ == "__main__":
    main()
