"""
run_experiment.py - Run the full barcode comparison experiment.

Usage:
    python run_experiment.py fiels/doc1.pdf fiels/doc2.pdf
    python run_experiment.py fiels/          # all PDFs in a folder

Output:
    results/  - raw JSON results per document
    results/comparison_report.html
"""

import sys
import json
import os
from pathlib import Path
from datetime import datetime

from backend.barcode_reader import scan_file
from backend.ai_extractor import extract_from_pdf
from backend.compare import compare_documents
from backend.report_html import generate_html

RESULTS_DIR = Path("results")


def resolve_inputs(args: list[str]) -> list[Path]:
    paths = []
    for arg in args:
        p = Path(arg)
        if p.is_dir():
            paths.extend(sorted(p for p in p.glob("*.pdf") if "_report" not in p.name))
        elif p.suffix.lower() == ".pdf" and p.exists() and "_report" not in p.name:
            paths.append(p)
        else:
            print(f"  [skip] {arg} – not a PDF or does not exist")
    return paths


def run_one(pdf_path: Path) -> dict | None:
    stem = pdf_path.stem
    print(f"\n{'='*60}")
    print(f"Document: {pdf_path.name}")

    # 1. Barcode library
    print("  [1/2] Running barcode library...")
    try:
        library_result = scan_file(str(pdf_path))
        print(f"        → {library_result['found']} barcode(s) on {library_result['pages']} page(s)")
    except Exception as e:
        print(f"        ✗ Library error: {e}")
        library_result = {"file": str(pdf_path), "pages": 0, "found": 0,
                          "barcodes": [], "error": str(e)}

    # 2. AI extraction
    print("  [2/2] Running AI extraction (sending to Anthropic API)...")
    try:
        ai_result = extract_from_pdf(str(pdf_path))
        print(f"        → {len(ai_result.get('barcodes', []))} barcode(s) identified by AI")
    except EnvironmentError as e:
        print(f"        ✗ API key error: {e}")
        ai_result = {"barcodes": [], "error": str(e), "_model": "n/a", "_source_file": str(pdf_path)}
    except Exception as e:
        print(f"        ✗ AI error: {e}")
        ai_result = {"barcodes": [], "error": str(e), "_model": "n/a", "_source_file": str(pdf_path)}

    # 3. Compare
    comparison = compare_documents(library_result, ai_result)
    s = comparison["summary"]
    print(f"        → Comparisons: {s['total']} total | "
          f"{s['counts'].get('agreement',0)} agree | "
          f"{s['counts'].get('library_only',0)} lib-only | "
          f"{s['counts'].get('ai_only',0)} ai-only")

    # 4. Save raw JSON
    RESULTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_json = RESULTS_DIR / f"{stem}_{ts}.json"
    out_json.write_text(
        json.dumps({"library": library_result, "ai": ai_result, "comparison": comparison},
                   ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"        → Raw JSON saved: {out_json}")

    return comparison


def main():
    if len(sys.argv) < 2:
        print("Usage: python run_experiment.py path/to/file.pdf [file2.pdf ...]")
        print("       python run_experiment.py fiels/")
        sys.exit(1)

    pdf_paths = resolve_inputs(sys.argv[1:])
    if not pdf_paths:
        print("No valid PDF files found.")
        sys.exit(1)

    print(f"Found {len(pdf_paths)} PDF(s) to process.")

    all_comparisons = []
    for pdf_path in pdf_paths:
        result = run_one(pdf_path)
        if result:
            all_comparisons.append(result)

    if not all_comparisons:
        print("\nNo results to report.")
        sys.exit(1)

    # Generate HTML report
    RESULTS_DIR.mkdir(exist_ok=True)
    report_path = RESULTS_DIR / "comparison_report.html"
    generate_html(all_comparisons, str(report_path))
    print(f"\n{'='*60}")
    print(f"✓ Report generated: {report_path.resolve()}")
    print("  Open it in any browser to view the full comparison.")


if __name__ == "__main__":
    main()
