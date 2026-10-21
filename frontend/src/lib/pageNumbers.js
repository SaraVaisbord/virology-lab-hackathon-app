/**
 * Every number (and date) the sources found on a page, merged into one list (one entry per value), each with the
 * sources that read it and where it is — so the lab worker can see it on the document and pick it for a field.
 */

const MIN_DIGITS = 4
const GEMINI_BOX_SCALE = 1000 // Gemini box_2d is [ymin, xmin, ymax, xmax] on 0..1000
const MIN_BOX_SIDE = 0.005 // zbar sometimes reports a 1-pixel scan line instead of the barcode area
// Which source's location to show when several sources read the same number (most precise first).
const BOX_PRIORITY = ['barcode', 'ocr', 'llm']

export const digitsOf = (value) => String(value ?? '').replace(/\D/g, '')

/** How two readings of one value compare: a date by day/month/full year ("20.08.26" = "20/08/2026"), else its digits. */
export function valueKey(value, datePattern) {
  const match = datePattern?.exec(String(value ?? ''))
  if (!match) return digitsOf(value)
  const [day, month, year] = match.slice(1, 4)
  return `${day.padStart(2, '0')}${month.padStart(2, '0')}${year.length === 2 ? `20${year}` : year}`
}

function geminiBox(box) {
  if (!Array.isArray(box) || box.length !== 4) return null
  const [ymin, xmin, ymax, xmax] = box.map((v) => Math.min(Math.max(v / GEMINI_BOX_SCALE, 0), 1))
  return xmax > xmin && ymax > ymin ? { x: xmin, y: ymin, width: xmax - xmin, height: ymax - ymin } : null
}

function usableBox(box) {
  return box && box.width >= MIN_BOX_SIDE && box.height >= MIN_BOX_SIDE ? box : null
}

/**
 * fieldKeys: the LLM's per-field candidates are read too (e.g. the received dates it found);
 * datePattern: tells dates from numbers (meta.datePattern — the backend's pattern).
 */
export function pageNumbers(sources, { fieldKeys = [], datePattern } = {}) {
  const byKey = new Map()
  const add = (raw, source, box, note) => {
    if (digitsOf(raw).length < MIN_DIGITS) return
    const key = valueKey(raw, datePattern)
    const item = byKey.get(key) ?? { key, value: String(raw).trim(), sources: [], boxes: {}, notes: [] }
    if (!item.sources.includes(source)) item.sources.push(source)
    if (box && !item.boxes[source]) item.boxes[source] = box
    if (note && !item.notes.includes(note)) item.notes.push(note)
    byKey.set(key, item)
  }

  for (const barcode of sources?.barcode_result?.items ?? []) {
    add(barcode.data, 'barcode', usableBox({ x: barcode.x, y: barcode.y, width: barcode.width, height: barcode.height }), barcode.type)
  }
  const ocr = sources?.ocr_result
  for (const candidate of ocr?.candidates ?? []) add(candidate.raw, candidate.source === 'barcode' ? 'barcode' : 'ocr', usableBox(candidate.box), candidate.label)
  for (const number of ocr?.unassigned_numbers ?? []) add(number.raw, number.source === 'barcode' ? 'barcode' : 'ocr', usableBox(number.box))
  const llm = sources?.llm_result
  for (const number of llm?.all_numbers ?? []) add(number.value, 'llm', geminiBox(number.box_2d), number.label || null)
  for (const key of fieldKeys) {
    for (const candidate of Array.isArray(llm?.[key]) ? llm[key] : []) add(candidate.value, 'llm', geminiBox(candidate.box_2d), candidate.label || null)
  }

  return [...byKey.values()].map((item) => {
    const boxSource = BOX_PRIORITY.find((source) => item.boxes[source]) ?? null
    return { ...item, box: boxSource ? item.boxes[boxSource] : null, boxSource, isDate: Boolean(datePattern?.exec(item.value)) }
  })
}

/** Can this page number be a value of a field of this kind? Dates for date fields, other numbers for number / ID fields. */
export function fitsKind(item, kind) {
  if (kind === 'date') return item.isDate
  return (kind === 'number' || kind === 'id') && !item.isDate
}

/** Field rows (of a form) whose value is this page number. */
export function fieldsUsing(fields, key, datePattern) {
  return fields.filter((field) => [field.corrected_value, field.value, field.llm_value, field.ocr_value, field.barcode_value].some((v) => v && valueKey(v, datePattern) === key))
}
