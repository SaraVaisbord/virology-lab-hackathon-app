export const EMPTY = '—'

const isPresent = (value) => value !== null && value !== undefined && value !== ''

/** The value to show for a field: a human correction wins, then the normalized value, then what the model read. */
export function fieldDisplayValue(field) {
  if (!field) return ''
  const value = [field.corrected_value, field.value, field.llm_value].find(isPresent)
  return value === undefined ? '' : String(value)
}

/** Group a form's field rows by field name (multi-value fields have several rows). */
export function groupFieldsByName(fields = []) {
  return fields.reduce((groups, field) => {
    ;(groups[field.field_name] ||= []).push(field)
    return groups
  }, {})
}

const dateTimeFormatter = new Intl.DateTimeFormat('he-IL', { dateStyle: 'short', timeStyle: 'short' })

const dateFormatter = new Intl.DateTimeFormat('he-IL', { dateStyle: 'short' })

/** A day from a server time — stored as UTC without a zone, so read as UTC (not as local time). */
export function formatDate(value) {
  if (!value) return EMPTY
  const date = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`)
  return Number.isNaN(date.getTime()) ? String(value) : dateFormatter.format(date)
}

export function formatDateTime(value) {
  if (!value) return EMPTY
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : dateTimeFormatter.format(date)
}
