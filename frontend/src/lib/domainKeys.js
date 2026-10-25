// The status and source keys the UI acts on (their Hebrew labels come from GET /meta). One place in the frontend;
// they must match backend/domain/vocabulary.py.
export const FORM_STATUS = { FAILED: 'failed', PROCESSING: 'processing' }
export const FIELD_STATUS = { NOT_FOUND: 'not_found' }
export const SOURCE = { LLM: 'llm', OCR: 'ocr', BARCODE: 'barcode' }
