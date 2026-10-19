# Backend – Document Intake API

FastAPI + SQLite. Uploaded PDFs/images are split into page images; every page is queued and processed
automatically in the background (local barcode scan + Gemini), and the results are stored as reviewable fields.

## Setup

```bash
pip install -r requirements.txt     # pyzbar also needs the zbar system library (see below)
cp .env.example .env                # set GEMINI_API_KEY
alembic upgrade head                # create / migrate the DB
python -m db.seed_senders           # load the known-senders catalog (idempotent)
uvicorn main:app --port 8000
```

zbar: Windows `winget install zbar` · macOS `brew install zbar` · Ubuntu `sudo apt-get install libzbar0`.

Tests: `pytest` (from `backend/`).

## Where things live

| What | Where |
|---|---|
| All settings (paths, limits, Gemini model/timeout, worker count…) | `config.py` (override via `.env`) |
| Field names, statuses, Hebrew labels, review reasons | `db/constants.py` – served to the UI by `GET /meta` |
| Gemini prompt | `prompts/extraction_prompt.md` (`{{known_senders}}` is filled from the DB) |
| Extraction pipeline & field rules | `services/extraction_service.py` |
| Background queue | `services/extraction_queue.py` |

## How extraction works

1. `POST /uploads` stores the file, renders one PNG per page and creates a `forms` row per page (`uploaded`).
2. Worker threads claim queued forms atomically (`uploaded → processing`), so the queue survives restarts.
3. For each page: zbar reads barcodes, Gemini returns field candidates (structured JSON + bounding boxes).
4. Every value gets a status and a reason: barcode match, Israeli-ID checksum, date format/plausibility,
   sender catalog match and model confidence. Coordinates are stored normalized (0..1) to the page image.
5. A form becomes `approved` once no field needs a human decision.

If Gemini returns 429 (quota), the form goes back to the queue and the queue pauses until the time Google
asks for; the UI shows this state. Note: the free tier allows only ~20 requests/day per model.

## API

| Method | Path | |
|---|---|---|
| GET | `/meta` | vocabulary & UI settings |
| POST | `/uploads` | upload files (multipart `files`) |
| GET | `/forms` | paged list – `limit`, `offset`, `status`, `query`, `sort_by`, `sort_dir`, `filter_<column>` |
| GET | `/forms/summary` | counts per status + queue state |
| GET | `/forms/export` | Excel – `mode=all|filtered|approved` + same filters |
| GET | `/forms/{id}` / `/forms/{id}/image` | one form / its page image |
| PATCH | `/forms/{id}/fields/{field_id}/confirm` | approve a value (`{"corrected_value": "..."}` optional) |
| POST | `/forms/{id}/retry` | re-queue a failed form |
