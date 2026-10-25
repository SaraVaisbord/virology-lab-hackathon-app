"""Run the extraction outside the server (cwd = backend):

    python -m scripts.extract_forms                                → re-verify every form (no LLM calls)
    python -m scripts.extract_forms --form 2 [--provider claude]   → extract one form now
    python -m scripts.extract_forms --form 2 --local-only          → local OCR/barcodes only (no tokens)
"""

from __future__ import annotations

import argparse
import logging
import sys

from config import load_settings
from container import build_container
from db.repositories import FormFilters


def main() -> None:
    container = build_container(load_settings())
    pipeline, settings = container.pipeline, container.settings
    parser = argparse.ArgumentParser()
    parser.add_argument("--form", type=int)
    parser.add_argument("--provider", choices=pipeline.llm_providers, default=None,
                        help="one provider only (default: LLM_PROVIDERS, with failover)")
    parser.add_argument("--local-only", action="store_true")
    cli = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")

    if cli.form is not None:
        status = pipeline.extract_one(cli.form, cli.provider, use_llm=False if cli.local_only else None)
        source = "local only" if cli.local_only else cli.provider or ", ".join(settings.llm_providers)
        print(f"Form {cli.form} ({source}): {status}", file=sys.stderr)
    else:
        rows, _ = container.listing.list_forms(FormFilters(), limit=settings.export_max_rows)
        done = sum(pipeline.reverify(row["id"]) for row in rows)
        print(f"Re-verified {done} of {len(rows)} forms.", file=sys.stderr)


if __name__ == "__main__":
    main()
