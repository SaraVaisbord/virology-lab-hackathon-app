# System Design

## 1. Project Overview

This project is a document-validation dashboard for clinical and medical form intake. The application supports:

- uploading source documents (PDF, PNG, JPEG)
- splitting/normalizing page images
- storing metadata in SQLite
- exposing API endpoints for listing, fetching, and previewing documents
- rendering a form table for review and validation
- providing a profile area and upload modal flow

The high-level architecture follows a simple layered pattern:

- Frontend: React + Vite app
- Backend: FastAPI application
- Data layer: SQLite via SQLAlchemy
- File storage: local filesystem under `backend/data`

## 2. Repository Structure

### Root

- `backend/` — server application, DB layer, business logic, tests
- `fronend/` — React UI application
- `docs/` — documentation files (if created later) 
- `system_design.md` — this architecture document

### Backend structure

- `backend/main.py` — FastAPI app bootstrap and CORS configuration
- `backend/api/` — endpoint definitions
  - `forms.py` — list/get form and image endpoints
  - `uploads.py` — upload endpoint
- `backend/services/` — domain logic
  - `forms_service.py` — list/get form logic and image path validation
  - `upload_service.py` — upload validation, hashing, file saving, PDF/image splitting, cleanup
- `backend/db/` — database definition and queries
  - `constants.py` — allowed field/status/type values
  - `models.py` — SQLAlchemy ORM models
  - `queries.py` — CRUD/query helpers for forms, fields, senders
  - `session.py` — DB session configuration
- `backend/schemas/` — Pydantic response models
  - `upload.py` — upload result schemas
- `backend/data/` — runtime files
  - `uploads/` — original uploaded files
  - `pages_img/` — page images created from PDFs or images
  - `app.db` — SQLite DB file
- `backend/tests/` — backend regression tests

### Frontend structure

- `fronend/src/App.jsx` — app shell, state orchestration, modal management
- `fronend/src/api.js` — API helper for backend calls
- `fronend/src/components/` — UI components
  - `Header.jsx` — top bar, logo and profile trigger
  - `Footer.jsx` — footer area
  - `DataTable.jsx` — main validation table with filtering/sorting/action cells
  - `UploadPanel.jsx` — upload modal content (drag/drop, file list, send action)
  - `FormDetailsModal.jsx` — details and document preview modal
  - `ProfilePage.jsx` — profile page/dropdown panel
  - `ui/` — reusable UI pieces such as modal shell, status badge, toggle
- `fronend/src/data/mockData.js` — mock or testing data layer used by earlier UI versions
- `fronend/src/theme.js` — theme or design tokens
- `fronend/index.html` and `fronend/src/main.jsx` — bootstrap and mount

## 3. Frontend Architecture

### Main UI flow

The root app (`App.jsx`) manages the global screen state:

- `forms`: current list of documents
- `loading`: table loading state
- `error`: fetch / API error state
- `selectedForm`: form selected for preview
- `uploadOpen`: upload modal visibility
- `profileOpen`: user profile panel visibility

The app fetches forms using the API helper and passes them into the main data table.

### Key components

#### `Header.jsx`

Responsible for:

- top navigation and branding
- dark mode toggle
- user profile button
- accessible open/close behavior for the profile menu

#### `DataTable.jsx`

Main table for all extracted documents. It is responsible for:

- rendering rows of form items
- searching by text
- filtering by status
- sorting by columns
- showing multi-value values in badges
- triggering preview via eye icon
- providing per-row edit action hook

This is the core review screen for the operator.

#### `UploadPanel.jsx`

Modal content for file upload. It supports:

- drag-and-drop upload area
- selecting multiple files
- repeated file protection by dedupe logic
- upload request to backend
- success/failure result display
- auto-close after successful upload

#### `FormDetailsModal.jsx`

Displays the selected record details and loads the corresponding page image.

It calls:

- `GET /forms/{id}` for row metadata
- `GET /forms/{id}/image` for image preview

#### `ProfilePage.jsx`

User profile and settings section. It is a modal/side panel for the authenticated lab user. It supports:

- personal info display/edit
- tabs for profile, activity, and settings
- a layout designed as a large floating panel over the dashboard

## 4. Backend Architecture

### API Layer

Defined under `backend/api`.

#### `GET /health`

Simple health check endpoint in `backend/main.py`.

#### `POST /uploads`

In `api/uploads.py`.

- Accepts one or more uploaded files
- Calls `process_upload()` for each file
- Returns per-file upload status/result

#### `GET /forms`

In `api/forms.py`.

- Lists extracted/uploaded form rows
- Accepts optional `status`, `limit`, and `offset` query params
- Returns form rows with their extracted fields

#### `GET /forms/{form_id}`

Fetches single form record by ID.

#### `GET /forms/{form_id}/image`

Returns the corresponding generated image file from disk as an image response.

### Service Layer

#### `services/upload_service.py`

This is the key processing service for document intake.

Responsibilities:

- sanitize uploaded filename
- detect file type by magic bytes / extension
- hash file contents via SHA-256
- save original upload to `backend/data/uploads`
- split PDF pages or normalize images
- generate per-page image files under `backend/data/pages_img`
- insert DB rows for each page
- avoid duplicates when file hash already exists
- clean up stale generated files when reprocessing a document

#### `services/forms_service.py`

Provides higher-level access to form retrieval and image path validation.

Responsibilities:

- list forms with optional filtering
- return a form record by ID
- validate image path security before returning file response

### DB Layer

The database layer is under `backend/db`.

#### Models

##### `Form`

Represents one extracted form/page row.

Fields:

- `id`
- `source_file`
- `file_hash`
- `page_number`
- `image_path`
- `form_type`
- `status`
- `raw_llm_json`
- `error`
- `uploaded_at`

Each form can have multiple `ExtractedField` rows.

##### `ExtractedField`

Stores extracted values from the form, for example:

- `first_name`
- `last_name`
- `id_number`
- `sender`
- `central_number`
- `commitment_number`

Contains:

- raw value
- normalized value
- validation status
- `bbox` metadata when available
- corrected value if the user modifies it

##### `Sender`

Stores sender metadata and categories, such as health fund / hospital / lab.

#### Constants

`db/constants.py` defines the accepted values for:

- `FIELDS`
- `MULTI_VALUE_FIELDS`
- `FORM_STATUSES`
- `FIELD_STATUSES`
- `FORM_TYPES`
- `SENDER_KINDS`

This prevents invalid values from entering the DB.

#### Query helpers

`db/queries.py` contains the main DB operations:

- `add_form()`
- `find_forms_by_hash()`
- `get_form()`
- `claim_next_form()`
- `set_form_status()`
- `save_extraction()`
- `get_fields()`
- `list_forms_with_fields()`
- `add_sender()`
- `list_senders()`
- `delete_forms_by_hash()`

## 5. Data Flow

### Flow 1: File upload

1. User selects files in the frontend upload modal.
2. `UploadPanel.jsx` calls `api.uploadFiles(files)`. 
3. The frontend sends a `POST /uploads` request with multipart form data.
4. `api/uploads.py` calls `process_upload(file)` for each file.
5. `upload_service.py`:
   - validates file type
   - computes SHA-256 hash
   - sanitizes filename
   - saves original file to `backend/data/uploads`
   - creates image(s) or page images
   - checks duplicate hash
   - inserts form rows into the DB
6. The backend returns a list of per-file statuses to the frontend.
7. The upload modal closes automatically after successful upload.
8. `App.jsx` calls `loadForms()` to refresh the table.

### Flow 2: Table display

1. `App.jsx` calls `api.listForms({ limit, offset })`.
2. `GET /forms` returns data from `list_forms_with_fields()`.
3. The table receives rows and renders them with ties to field metadata.
4. `DataTable.jsx` shows:
   - names
   - statuses
   - metadata fields
   - badges for multi-value fields
   - eye icon for preview
5. If the user clicks the eye button, the selected form opens the details modal.

### Flow 3: Preview / image retrieval

1. `FormDetailsModal.jsx` calls `api.getForm(form.id)`.
2. Then it loads `api.getFormImageUrl(form.id)` and fetches `GET /forms/{id}/image`.
3. The backend resolves the local file path using `forms_service.py`.
4. The image is returned to the browser and displayed in the modal.

### Flow 4: Extraction and field tracking

1. A form row is marked as `uploaded`.
2. Later it is claimed by worker logic and moved to `processing`.
3. After extraction, `save_extraction()` stores extracted field rows and sets the form to `extracted`.
4. `DataTable.jsx` reads from the joined form/fields data and renders the relevant fields.

## 6. Where to Edit Specific Logic

This section is meant to help developers locate code quickly.

### Change upload behavior

- `backend/services/upload_service.py`
- `backend/api/uploads.py`
- `fronend/src/components/UploadPanel.jsx`

### Change table rendering or review behavior

- `fronend/src/components/DataTable.jsx`
- `fronend/src/App.jsx`

### Change preview modal behavior

- `fronend/src/components/FormDetailsModal.jsx`
- `backend/api/forms.py`
- `backend/services/forms_service.py`

### Change DB schema or validation rules

- `backend/db/models.py`
- `backend/db/constants.py`
- `backend/db/queries.py`

### Change API contract or response shape

- `backend/api/`
- `backend/schemas/`

## 7. Operational Notes

- The backend uses SQLite as a local database, which is suitable for this prototype and rapid iteration.
- Generated images and uploaded files are stored on disk, not in the DB itself.
- The DB keeps metadata, while the filesystem keeps the heavy artifacts.
- Frontend and backend are intentionally separated to keep the UI independent of direct DB access.

## 8. Summary

The project follows a layered architecture:

- frontend for interaction and rendering
- backend API for orchestration
- services for business logic
- DB for persistence and metadata
- filesystem for uploaded document artifacts and generated page images

This separation keeps the system easy to understand, debug, and extend as the validation workflow grows.
