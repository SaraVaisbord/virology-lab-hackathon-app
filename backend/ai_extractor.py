"""
ai_extractor.py - Send a PDF to Gemini and extract structured fields.

WARNING: Documents are transmitted to Google's Gemini API servers.
Review https://ai.google.dev/gemini-api/terms before processing real medical records.
"""

import os
import json
from pathlib import Path

GEMINI_API_KEY_ENV = "GEMINI_API_KEY"
MODEL = "models/gemini-flash-latest"
MAX_PAGES = 3  # MVP: limit pages to save tokens

PROMPT = """You are analyzing a scanned medical commitment form (Hebrew: טופס התחייבות רפואית).

Extract every piece of structured information you can identify. Return ONLY a valid JSON object with this exact schema:

{
  "pages_analyzed": <integer>,
  "barcodes": [
    {
      "value": "<string>",
      "type_guess": "<e.g. CODE128, EAN13, unknown>",
      "confidence": "<high|medium|low>"
    }
  ],
  "commitment_numbers": [
    { "value": "<string>", "confidence": "<high|medium|low>"}
  ],
  "central_numbers": [
    { "value": "<string>", "confidence": "<high|medium|low>"}
  ],
  "patient_names": [
    { "value": "<string>", "confidence": "<high|medium|low>"}
  ],
  "id_numbers": [
    { "value": "<string>", "confidence": "<high|medium|low>"}
  ],
  "sender_organizations": [
    { "value": "<string>", "confidence": "<high|medium|low>"}
  ],
  "received_dates": [
    { "value": "<string>", "confidence": "<high|medium|low>"}
  ],
  "uncertain_fields": [
    { "field": "<string>", "raw_value": "<string>", "reason": "<string>"}
  ],
  "notes": "<any general observations about the document>"
}

Rules:
- Do NOT invent values. If a field is not visible, omit it from the list (empty array is fine).
- A barcode value is NOT necessarily the same as a commitment number unless the document explicitly labels it so.
- Include page numbers wherever you can identify them.
- Do not include full patient names or ID numbers in the notes field.
- Return ONLY the JSON object, no markdown, no explanation.
"""


def _load_key() -> str:
    key = os.environ.get(GEMINI_API_KEY_ENV, "").strip()
    if not key:
        env_file = Path(__file__).parent / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith(f"{GEMINI_API_KEY_ENV}="):
                    key = line.split("=", 1)[1].strip()
                    break
    if not key or key == "your-key-here":
        raise EnvironmentError(
            f"API key not found. Set {GEMINI_API_KEY_ENV} in your environment "
            "or copy .env.example to .env and fill in your key."
        )
    return key


def extract_from_pdf(pdf_path: str) -> dict:
    """
    Send the PDF to Gemini and return the parsed JSON result.
    Raises EnvironmentError if the key is missing.
    Raises RuntimeError on API or parse errors.
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise ImportError("Run: pip install google-genai")

    # Fix SSL on Windows by pointing to certifi's CA bundle
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

    # Workaround for CA cert key usage extension issue on Python 3.14 / Windows
    import ssl
    _orig_create = ssl.create_default_context
    def _patched_create(*args, **kwargs):
        ctx = _orig_create(*args, **kwargs)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    ssl.create_default_context = _patched_create

    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {pdf_path}")

    key = _load_key()
    client = genai.Client(api_key=key)

    # Convert first MAX_PAGES to images and send as PNG (faster than PDF)
    import pymupdf as fitz
    from PIL import Image
    import io
    doc = fitz.open(str(path))
    pages_to_send = min(MAX_PAGES, len(doc))
    image_parts = []
    for i in range(pages_to_send):
        pix = doc[i].get_pixmap(dpi=100)  # low DPI to keep size small
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        image_parts.append(
            types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")
        )
    doc.close()

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=image_parts + [types.Part.from_text(text=PROMPT)],
        )
    except Exception as e:
        raise RuntimeError(f"Gemini API error: {e}") from e

    raw_text = response.text.strip()

    # Strip markdown code fences if the model added them
    if raw_text.startswith("```"):
        lines = raw_text.splitlines()
        raw_text = "\n".join(
            line for line in lines if not line.startswith("```")
        ).strip()

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Model returned non-JSON response (parse error: {e}). "
            f"First 300 chars: {raw_text[:300]}"
        ) from e

    result["_model"] = MODEL
    result["_source_file"] = str(path)
    return result
