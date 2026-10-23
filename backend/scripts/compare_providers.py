"""
compare_providers.py - Compare Gemini and OpenAI on the SAME page, through the SAME verification rules.

    python -m scripts.compare_providers <form_id> [--openai-model gpt-5.4-mini]

Read-only: uses the Gemini answer and barcodes already stored for the form (no new Gemini call) and asks
OpenAI once. Nothing is written to the database, so it can run next to the live server/queue.
"""

from __future__ import annotations

import argparse
import sys

from db import queries
from domain.vocabulary import FIELD_LABELS, FIELD_STATUS_LABELS
from openai_extractor import extract_from_image as openai_extract
from services.extraction_service import build_fields, verification_rules
from storage import get_storage

_EMPTY = "—"


def _summarise(fields: list[dict], name: str) -> tuple[str, str]:
    rows = [f for f in fields if f["field_name"] == name]
    values = " | ".join(f.get("llm_value") or _EMPTY for f in rows)
    statuses = " | ".join(FIELD_STATUS_LABELS[f["status"]] for f in rows)
    return values, statuses


def _score(fields: list[dict]) -> dict[str, int]:
    found = [f for f in fields if f["status"] != "not_found"]
    return {
        "values found": len(found),
        "confirmed by barcode": sum(1 for f in found if f.get("barcode_value")),
        "conflicts": sum(1 for f in found if f["status"] == "conflict"),
        "low confidence": sum(1 for f in found if f.get("confidence") in ("low", "medium")),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("form_id", type=int)
    parser.add_argument("--openai-model")
    args = parser.parse_args()

    form = queries.get_form(args.form_id, with_sources=True)
    if form is None:
        sys.exit(f"Form {args.form_id} not found")
    sources = form["sources"]
    gemini_result = sources.get("llm_result")
    if not gemini_result:
        sys.exit(f"Form {args.form_id} has no Gemini result yet (status: {form['status']})")
    barcodes = (sources.get("barcode_result") or {}).get("items", [])
    senders = [name for name, _ in queries.list_senders()]

    print(f"Form {form['id']} · {form['source_file']} · page {form['page_number']} · barcodes on page: {len(barcodes)}")
    print("Asking OpenAI…", flush=True)
    with get_storage().local_path(form["image_path"]) as image_path:
        openai_result = openai_extract(image_path, senders, model=args.openai_model)

    gemini_fields = build_fields(gemini_result, barcodes, senders, verification_rules(), page=form["page_number"])
    openai_fields = build_fields(openai_result, barcodes, senders, verification_rules(), page=form["page_number"])
    usage = openai_result.get("_usage", {})
    print(f"Gemini: {gemini_result.get('_model')} (stored answer)")
    print(f"OpenAI: {openai_result['_model']} · {openai_result['_seconds']}s · tokens in/out: {usage.get('prompt_tokens')}/{usage.get('completion_tokens')}")
    print()

    header = f"{'שדה':14s} │ {'Gemini':32s} │ {'OpenAI':32s} │ זהים?"
    print(header)
    print("─" * len(header))
    for name, label in FIELD_LABELS.items():
        g_values, g_status = _summarise(gemini_fields, name)
        o_values, o_status = _summarise(openai_fields, name)
        same = "✓" if g_values == o_values else "✗"
        print(f"{label:14s} │ {g_values:32s} │ {o_values:32s} │ {same}")
        print(f"{'':14s} │ {g_status:32s} │ {o_status:32s} │")
    print()

    g_score, o_score = _score(gemini_fields), _score(openai_fields)
    for metric in g_score:
        print(f"{metric:22s} Gemini {g_score[metric]:3d}   OpenAI {o_score[metric]:3d}")
    print("\nNote: this compares the two readings with each other and with the barcodes — it is not ground truth.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
