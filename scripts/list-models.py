"""List candidate models per privacy level from an OpenRouter-compatible /models endpoint.

Usage: python scripts/list-models.py --privacy low|medium|high [--limit 30]
"""

from __future__ import annotations

import argparse

from conductor.catalog import CatalogError, fetch_models, select_models

BASE_URLS = {
    "low": "https://openrouter.ai/api/v1",
    "medium": "https://openrouter.ai/api/v1",
    "high": "https://eu.openrouter.ai/api/v1",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--privacy", choices=BASE_URLS, required=True)
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    try:
        models = fetch_models(BASE_URLS[args.privacy])
    except CatalogError as error:
        raise SystemExit(f"error: {error}") from error
    rows = select_models(models, free=args.privacy == "low")[: args.limit]
    print(f"{'model':60} {'$/M in':>8} {'$/M out':>8} {'context':>9}")
    for row in rows:
        print(f"{row.id:60} {row.prompt_price:8.3f} {row.completion_price:8.3f} {row.context:9}")


if __name__ == "__main__":
    main()
