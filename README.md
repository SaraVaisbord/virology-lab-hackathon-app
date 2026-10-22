# Commitment Form Validation — Central Virology Laboratory

An intake system for scanned **funding-commitment forms** (טפסי התחייבות), built at the Central Virology Laboratory
(Sheba Medical Center) hackathon. It reads each page, extracts the fields the lab needs, cross-checks every value
against independent sources, and puts only the uncertain ones in front of the lab technician. Approved data is
exported to Excel as **one row per commitment number**.

---



Uploading דמו_האקתון_שרה_וייסבורד_דקה.mp4…



## Highlights

- **Three independent readings per page** — barcodes, local OCR, and a vision LLM. A value is marked *verified* only
  when a printed label proves the field **and** two sources read the same value; everything else goes to review.
- **Claude first, Gemini as fallback** — providers are tried in a configurable order, each with several API keys.
  A key that hits its quota or is rejected rests and the next one is used; an overloaded model rests on every key,
  so a page is never resent to it.
- **Review screen built for speed** — the document is shown with the selected value highlighted, next to what each
  source read and every number found on the page. The technician confirms, corrects, picks, adds or deletes.
- **Human decisions are final** — a confirmed value survives re-extraction, and a deleted value never comes back.
- **Correction Intelligence** — every review action is recorded (without storing the values themselves). A dashboard
  surfaces recurring mistakes — fields that are often corrected, digit confusions, values assigned to the wrong field,
  day/month swaps — with a recommendation for each.
- **Duplicate detection** — a commitment number that appears on two forms is flagged with a side-by-side comparison.
- **Login with a one-time code** sent to the lab's mailbox; every API call except the health check requires a session.

## How it works

```
 Login (one-time code by e-mail)
        │
 Upload PDF / images ──► each page stored as an image, straightened, queued
        │
 Preprocessing (local) — deskew, even lighting, highlighter removal, print / pen / stamp layers
        │
        ├── Barcodes        zbar                       (local)
        ├── Printed text    Tesseract OCR: labels → values   (local)
        └── Vision LLM      Claude ─► Gemini fallback   (Anthropic / Google APIs)
        │
 Cross-validation — verified · conflict · uncertain · not found
        │
 Review screen ──► every action recorded in the correction history ──► insights dashboard
        │
 Excel export — one row per commitment number
```

### Extracted fields

| Field | Notes |
|---|---|
| First name, last name, ID number | Israeli ID numbers are validated by check digit |
| Commitment number | **The export row key.** Also labelled "דרישה", and "דגימה" on Leumit forms and on forms stating that the sample number is the commitment |
| Central number | The lab's internal accession number (the "מרכזי" sticker); a form may carry several |
| Received date | The date under the central number or in the "התקבל" stamp |
| Sender | Matched against the list of known senders |

Irrelevant numbers — phone, fax, address, postal code, department, physician licence — are filtered out at every
stage (the LLM prompt, OCR, and the server).

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite, Tailwind CSS |
| Backend | Python 3.11+, FastAPI, SQLAlchemy, Alembic |
| Document processing | OpenCV, Tesseract OCR, zbar, PyMuPDF |
| AI | Claude (Anthropic SDK) with Google Gemini as fallback; structured JSON output from one shared schema |
| Data | SQLite locally, PostgreSQL (AWS RDS) in the cloud; files on local disk or a private S3 bucket — never in the database |
| Cloud | AWS — EKS, RDS, S3, ECR, Secrets Manager, ALB (see the related repositories) |

## Getting started

**Prerequisites:** Python 3.11+, Node.js 18+, Tesseract with the `heb`, `eng` and `osd` language data, and zbar.

```bash
# Backend
cd backend
pip install -r requirements.txt
cp .env.example .env            # add your API keys (see Configuration)
alembic upgrade head            # create / migrate the database
python -m db.seed_senders       # load the list of known senders
uvicorn main:app --port 8000

# Frontend (second terminal)
cd frontend
npm install
npm run dev                     # http://localhost:5173 — /api is proxied to the backend
```

### Configuration

All settings live in `backend/.env` (never committed); defaults are in `backend/config.py`.

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY`, `ANTHROPIC_API_KEY_2`, … | Claude API keys, tried in turn |
| `GEMINI_API_KEY`, `GEMINI_API_KEY_2`, … | Gemini API keys, tried in turn |
| `LLM_PROVIDERS` | Provider order, default `claude,gemini` |
| `CLAUDE_MODEL`, `CLAUDE_EFFORT` | Claude model and reasoning effort |
| `LLM_ENABLED` | `false` runs only the local stages (no tokens) |
| `AUTH_ENABLED` | Login screen on/off (default on) |
| `AUTH_EMAIL`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` | Where login codes are sent, and how |
| `AUTH_SECRET` | Signs session cookies, so sessions survive a restart |
| `AUTH_DEMO_CODE` | **Demo only:** no e-mail is sent and this fixed code logs in. Remove before real data |
| `DATABASE_URL`, `STORAGE_BACKEND`, `S3_BUCKET`, `API_PREFIX` | Cloud settings (PostgreSQL, S3, `/api` behind the load balancer) |

### Tests

```bash
cd backend
pytest                                                      # SQLite
TEST_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db pytest   # PostgreSQL, as on AWS RDS
```

The suite covers the extraction pipeline, cross-validation rules, provider failover, the correction history,
insights, login and the API. No test ever calls a real AI provider or reads real API keys.

## API overview

All routes are served under `API_PREFIX` (`/api` in the cloud).

| Method | Route | Description |
|---|---|---|
| `GET` | `/auth/status` · `POST` `/auth/request-code` · `/auth/verify` · `/auth/logout` | Login with a one-time code |
| `POST` | `/uploads` | Upload PDF or image files |
| `GET` | `/forms` · `/forms/{id}` · `/forms/{id}/image` | List (paged, filtered, sorted), one form, its page image |
| `PATCH` | `/forms/{id}/fields/{field_id}/confirm` | Confirm a value, optionally corrected |
| `POST` / `DELETE` | `/forms/{id}/fields` · `/forms/{id}/fields/{field_id}` | Add or delete a value |
| `GET` | `/forms/export` | Excel export |
| `GET` | `/insights/corrections` | Recurring correction patterns, with a recommendation each |
| `GET` | `/meta` | Field names, statuses and Hebrew labels — the UI keeps no copy of its own |

More detail on the backend: [`backend/README.md`](backend/README.md) · System design: [`system_design.md`](system_design.md).

## Project structure

```
backend/
  api/                  HTTP endpoints (auth, uploads, forms, insights, meta)
  db/                   models, queries, and constants.py — the single source of truth for fields, labels, statuses
  services/             extraction queue, cross-validation, provider failover, insights, export, login
  preprocessing.py      page preprocessing
  local_extractor.py    local OCR: labels → values
  claude_extractor.py   Claude provider
  ai_extractor.py       Gemini provider (key and model rotation)
  prompts/              the extraction prompt shared by all providers
  alembic/              database migrations (SQLite and PostgreSQL)
  tests/
frontend/src/           the lab technician's interface (forms table, review screen, insights dashboard, login)
```

## Data and security

- The repository contains **no patient data**. The database, uploaded files and `.env` are excluded from Git.
- **Page images are sent to the configured AI providers** (Anthropic, Google). Review their data-processing terms
  before processing real medical records.
- Before real data: remove `AUTH_DEMO_CODE` and configure SMTP, serve the site over HTTPS only and set
  `AUTH_COOKIE_SECURE=true`.

## Built with

Designed, implemented, tested and deployed with **Claude Code**.

## Related repositories

- [virology-lab-hackathon-infra](https://github.com/SaraVaisbord/virology-lab-hackathon-infra) — AWS infrastructure (Terraform)
- [virology-lab-hackathon-k8s](https://github.com/SaraVaisbord/virology-lab-hackathon-k8s) — Kubernetes manifests and deployment script
