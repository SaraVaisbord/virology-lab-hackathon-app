"""
local_eval.py - Field-level evaluation of the local extractor (no LLM calls, no tokens).

    python local_eval.py <folder with PDFs> --reference-db path/to/app.db

The reference is what an earlier LLM run extracted (NOT ground truth). For every value the local extractor
assigned to a field it reports whether the LLM put the same value in the same field, in a different field
(an assignment disagreement), or didn't read it; and for every LLM value whether the local extractor found it
in the same field, only saw it unassigned, or missed it. Barcode support is shown too. Only counts are
printed per page (never values, unless --show-values is given for debugging).
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

from PIL import Image

import barcode_reader
import local_extractor
from preprocessing import preprocess
from preprocessing_eval import load_native_page

EVAL_FIELDS = ("central_number", "commitment_number", "id_number", "received_date")


def _norm(field: str, value: str) -> str:
    if field == "received_date":
        return local_extractor.normalize_date(value) or value
    return re.sub(r"\D", "", value)


def load_reference(db_path: Path) -> dict[str, set[tuple[str, str]]]:
    connection = sqlite3.connect(db_path)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(forms)")}
    column = "llm_result" if "llm_result" in columns else "raw_llm_json"
    reference = {}
    for name, raw in connection.execute(f"SELECT source_file, {column} FROM forms WHERE {column} IS NOT NULL"):
        data = json.loads(raw)
        llm = data.get("llm", data)
        reference[name] = {(f, _norm(f, c["value"])) for f in EVAL_FIELDS for c in llm.get(f, []) if c.get("value")}
    return reference


def scan_barcodes(views) -> list[dict]:
    found = {}
    for view in views.barcode_views:
        for barcode in barcode_reader.scan_pil_image(Image.fromarray(view).convert("RGB")):
            found.setdefault(barcode["data"], barcode)
    return list(found.values())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--reference-db", type=Path, required=True)
    parser.add_argument("--show-values", action="store_true")
    args = parser.parse_args()
    reference = load_reference(args.reference_db)

    local_tally, ref_tally, per_field = Counter(), Counter(), Counter()
    total_seconds = 0.0
    for pdf in sorted(args.folder.glob("*.pdf")):
        started = time.time()
        image, dpi = load_native_page(pdf)
        views = preprocess(image, source_dpi=dpi)
        barcodes = scan_barcodes(views)
        result = local_extractor.extract(views, barcodes)
        seconds = time.time() - started
        total_seconds += seconds

        refs = reference.get(pdf.name)
        local_pairs = {(c.field, c.value) for c in result.candidates if c.field in EVAL_FIELDS and c.rank == 0}
        barcode_values = {re.sub(r"\D", "", b["data"]) for b in barcodes}
        seen_values = {u["value"] for u in result.unassigned_numbers} | {v for _, v in local_pairs}

        row = Counter()
        for field, value in local_pairs:
            row["assigned"] += 1
            row["barcode_backed"] += value in barcode_values
            if refs is not None:
                if (field, value) in refs:
                    row["agree"] += 1
                    per_field[f"{field}:agree"] += 1
                elif any(v == value for _, v in refs):
                    row["other_field"] += 1
                    per_field[f"{field}:other_field"] += 1
                else:
                    row["not_in_llm"] += 1
        if refs is not None:
            for field, value in refs:
                ref_tally["llm_values"] += 1
                if (field, value) in local_pairs:
                    ref_tally["found_same_field"] += 1
                elif value in seen_values:
                    ref_tally["seen_unassigned"] += 1
                else:
                    ref_tally["missed"] += 1
        local_tally.update(row)

        ref_note = "no reference" if refs is None else f"agree {row['agree']}, other field {row['other_field']}, not in LLM {row['not_in_llm']}"
        values = f"  {sorted(local_pairs)}" if args.show_values else ""
        print(f"{pdf.name:7s} labels {len(result.labels):2d} | assigned {row['assigned']:2d} (barcode-backed {row['barcode_backed']}) | {ref_note} | {seconds:4.1f}s{values}", flush=True)

    print("-" * 100)
    print(f"LOCAL ASSIGNMENTS: {dict(local_tally)}")
    print(f"LLM VALUES ({ref_tally['llm_values']}): found in same field {ref_tally['found_same_field']}, "
          f"seen but unassigned {ref_tally['seen_unassigned']}, missed {ref_tally['missed']}")
    print(f"per field: {dict(per_field)}")
    print(f"time: {total_seconds:.0f}s total")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
