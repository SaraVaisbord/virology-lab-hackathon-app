/**
 * @typedef {{
 *   id: number,
 *   source_file: string,
 *   page_number: number | null,
 *   status: string,
 *   uploaded_at: string | null,
 *   file_hash: string,
 *   image_path: string,
 *   error: string | null,
 *   form_type: string | null,
 *   raw_llm_json: string | null,
 *   fields: Array<{
 *     id: number,
 *     form_id: number,
 *     field_name: string,
 *     value: string | number | null,
 *     raw_value: string | number | null,
 *     status: string | null,
 *     corrected_value: string | number | null,
 *     bbox: string | null,
 *     created_at: string | null,
 *   }>
 * }} FormRecord
 */

/**
 * @typedef {{
 *   value: string,
 *   status: string | null,
 * }} ValueBadgeItem
 */
