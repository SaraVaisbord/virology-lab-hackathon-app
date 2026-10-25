/**
 * Numbers (and dates) found on the page come from the server with the form (`page_numbers`, see
 * backend/domain/page_numbers.py): { key, value, sources, boxes, notes, box, box_source, is_date }.
 * These helpers match them to the form's fields.
 */

export const digitsOf = (value) => String(value ?? '').replace(/\D/g, '')

/** How two readings of one value compare: a date by day/month/full year ("20.08.26" = "20/08/2026"), else its digits.
 * The same rule as page_numbers.value_key on the server, so field values match the page numbers' keys. */
export function valueKey(value, datePattern) {
  const match = datePattern?.exec(String(value ?? ''))
  if (!match) return digitsOf(value)
  const [day, month, year] = match.slice(1, 4)
  return `${day.padStart(2, '0')}${month.padStart(2, '0')}${year.length === 2 ? `20${year}` : year}`
}

/** Can this page number be a value of a field of this kind? Dates for date fields, other numbers for number / ID fields. */
export function fitsKind(item, kind) {
  if (kind === 'date') return item.is_date
  return (kind === 'number' || kind === 'id') && !item.is_date
}

/** Field rows (of a form) whose value is this page number. */
export function fieldsUsing(fields, key, datePattern) {
  return fields.filter((field) => [field.corrected_value, field.value, field.llm_value, field.ocr_value, field.barcode_value].some((v) => v && valueKey(v, datePattern) === key))
}
