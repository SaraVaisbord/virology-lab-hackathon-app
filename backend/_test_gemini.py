import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from backend.ai_extractor import extract_from_pdf, MAX_PAGES

path = "fiels/\u05d4\u05ea\u05d7\u05d9\u05d9\u05d1\u05d5\u05d9\u05d5\u05ea - \u05d3\u05d5\u05d2\u05de\u05d0\u05d5\u05ea, \u05d7\u05dc\u05e7 1 (PDF).pdf"

try:
    print(f"Sending first {MAX_PAGES} pages to Gemini...")
    result = extract_from_pdf(path)
    print("Model:", result["_model"])
    print("Pages analyzed by AI:", result.get("pages_analyzed"))
    print("Barcodes found by AI:", len(result.get("barcodes", [])))
    print("Commitment numbers:", len(result.get("commitment_numbers", [])))
    print("First 5 barcodes:")
    for bc in result.get("barcodes", [])[:5]:
        print(f"  page={bc.get('page')}  value={bc.get('value')}  confidence={bc.get('confidence')}")
except Exception as e:
    print("ERROR:", type(e).__name__, str(e))
    sys.exit(1)
