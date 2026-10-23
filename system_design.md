# System Design

## 1. Overview

A validation dashboard for medical commitment forms (טפסי התחייבות) at the Central Virology Laboratory.

- Users upload PDF / PNG / JPEG files; each page becomes one **form**.
- Every page is processed **automatically in a background queue**: local barcode scan (zbar) + Gemini extraction.
- Each extracted value gets a status and a human-readable reason; the lab worker reviews uncertain values
  next to the page image (with the value highlighted) and approves them.
- A form is **approved** once no field needs a human decision. Data can be exported to Excel.

Stack: React 18 + Vite + Tailwind (frontend) · FastAPI + SQLAlchemy + SQLite + Alembic (backend) ·
files on local disk under `backend/data`.

## 2. Single sources of truth

| Concern | Lives in | Consumed by |
|---|---|---|
| Settings (paths, limits, Gemini model/timeout, worker count, page size, poll interval) | `backend/config.py` (+ `.env`) | backend; UI-relevant ones via `GET /meta` |
| Field names, statuses, Hebrew labels, review reasons, export modes, upload types | `backend/domain/vocabulary.py` | backend, DB constraints, Excel export, UI via `GET /meta` |
| Extraction prompt | `backend/prompts/extraction_prompt.md` | every LLM provider (`integrations/llm/prompt.py`) |
| LLM response schema | generated from `FIELDS` in `integrations/llm/schema.py` | structured output of every provider |

The frontend has no copies of labels: `MetaProvider` loads `/meta` once and components use `useMeta()`; the few status and source keys the UI acts on are in `frontend/src/lib/domainKeys.js`.

## 3. Repository structure

### Backend (`backend/`)

Dependencies point inwards — `api → services → domain`; `db` and `integrations` depend on `domain` only. Only the
composition root (`container.py`) creates components; everything else receives what it needs.

- `main.py` — entry point (`uvicorn main:app`); `api/app.py` — `create_app()`: CORS, routers, login check, queue lifetime
- `config.py` — `Settings` (immutable) read once by `load_settings()` from the environment / `.env`
- `container.py` — composition root: builds the database, repositories, integrations and services from the settings
- `api/` — `forms.py` (list/summary/export/get/image/confirm/retry/delete), `uploads.py`, `meta.py`, `auth.py`,
  `insights.py`; `dependencies.py` hands the container's components to the routes
- `services/`
  - `upload_service.py` — validate (magic bytes), hash/dedupe, store, split into upright page PNGs, create forms
  - `extraction_pipeline.py` — per-page pipeline: preprocess → barcodes → OCR → LLM → merge; user-facing error messages
  - `extraction_queue.py` — worker threads, atomic claim, quota pause/resume
  - `review_service.py` — the lab worker's actions (confirm / correct / add / delete a value, delete a form, retry)
  - `export_service.py` — Excel workbook (same filters as the table) · `insights_service.py` · `auth_service.py`
- `domain/` — `vocabulary.py` (fields, statuses, Hebrew labels), `validators.py` (ID checksum, dates, change
  classification), `verification.py` (field rules, `build_fields`), `review_rules.py`
- `db/` — `models.py`, `session.py` (`Database`), `serialization.py`, `repositories/` (forms, review, listing,
  correction history, senders), `seed_senders.py`
- `integrations/` — `llm/` (Gemini, Claude, OpenAI behind one `LlmProvider` protocol, `LlmRouter` failover),
  `ocr/` (`OcrEngine` protocol, Tesseract, label → value extraction), `imaging/` (preprocessing, zbar), `storage.py`
  (local / S3), `mailer.py` (SMTP)
- `experimental/` — handwritten digits (measured, not wired in) · `scripts/` — command-line tools
- `alembic/` — migrations · `tests/` — pytest suite (`conftest.py` gives isolated settings, database and components per test)

### Frontend (`frontend/src/`)

- `main.jsx` — mounts `<MetaProvider><App/></MetaProvider>`
- `App.jsx` — layout, filters state, modals, export, toasts
- `api.js` — all backend calls
- `meta/MetaContext.jsx` — vocabulary from `/meta` + helpers (`fieldLabel`, `needsReview`, …)
- `hooks/useForms.js` — server-side paging ("load more" / infinite scroll) and polling while forms are processing
- `lib/format.js` — display value / grouping / date formatting helpers
- `components/`
  - `Header.jsx`, `Footer.jsx`
  - `ProcessingBanner.jsx` — live processing progress, quota-pause notice, failed count
  - `TableToolbar.jsx` — upload, export menu, search, status filter, active column filters
  - `DataTable.jsx` — columns from meta, multi-value chips, per-column sort/filter, row actions (view / retry)
  - `UploadPanel.jsx` — drag & drop upload modal
  - `form-details/` — `FormDetailsModal`, `FieldEditor` (single "approve field" action), `FieldList`, `DocumentViewer` (highlight + zoom)
  - `ui/` — `ModalShell`, `StatusBadge`

## 4. Data model

**Form** — one page: `source_file`, `file_hash`, `page_number`, `image_path`, `status`
(`uploaded` → `processing` → `extracted` / `failed` → `approved`), `raw_llm_json`, `error`, `uploaded_at`.

**ExtractedField** — one value (multi-value fields such as `commitment_number` / `central_number` have one row per value):
`field_name`, `value` (normalized / approved), `llm_value` (Gemini), `ocr_value` (barcode),
`corrected_value` (human edit), `status` (`verified` / `unverified` / `uncertain` / `not_found` / `confirmed`),
`confidence`, `reason`, `page`, and `x/y/width/height` **normalized to the page image (0..1)**.

**Sender** — known referring institutions (seeded); used to normalize the sender field and injected into the prompt.

## 5. Flows

### Upload → queue → extraction
1. `POST /uploads` → `process_upload()` per file → page PNGs + `forms` rows (`uploaded`) → queue notified.
2. A worker claims the oldest queued form (`processing`), runs `extract_for_form()`:
   barcodes (zbar) + Gemini (prompt file + known senders) → `build_fields()` → `save_extraction()`.
3. Field rules: barcode match ⇒ verified; ID checksum; date format and plausibility; sender catalog; low model
   confidence ⇒ uncertain; free-text fields (names) ⇒ unverified; missing ⇒ not_found.
4. Errors: Gemini 429 ⇒ form returns to the queue and the whole queue pauses until Google's retry time;
   other failures ⇒ `failed` with a Hebrew message (retry from the UI).

### Table
`GET /forms` is paged (default from `DEFAULT_PAGE_SIZE`), newest first; search, status, per-column filters and
sorting run in SQL. The UI polls `/forms` + `/forms/summary` only while forms are pending.

### Review
Clicking a value opens `FormDetailsModal` on that field: reason, barcode vs. AI values, editable approved value,
page image with the value highlighted. "Approve field" → `PATCH /forms/{id}/fields/{field_id}/confirm` →
the form status is recalculated and the modal moves to the next field needing review.

### Export
`GET /forms/export?mode=all|filtered|approved` — same filter parameters as the table; multi-value fields are joined.

## 6. Operational notes

- Gemini free tier: ~20 requests/day per model — the queue pauses and resumes automatically when exhausted.
- `GEMINI_INSECURE_SSL` (default on) works around a local CA-certificate issue; turn it off in production.
- Migrations: `alembic upgrade head`. SQLite batch migrations run with foreign keys disabled to avoid cascade deletes.
