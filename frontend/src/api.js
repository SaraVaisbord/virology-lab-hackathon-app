const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
const COLUMN_FILTER_PREFIX = 'filter_'

async function parseError(response) {
  const contentType = response.headers.get('content-type') || ''
  const payload = contentType.includes('application/json') ? await response.json() : await response.text()
  const detail = payload && typeof payload === 'object' ? payload.detail : payload
  return new Error(typeof detail === 'string' && detail ? detail : 'הבקשה לשרת נכשלה')
}

async function request(path, { json, ...options } = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: json !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: json !== undefined ? JSON.stringify(json) : options.body,
  })
  if (!response.ok) throw await parseError(response)
  return response.json()
}

/** Table filters → query string (shared by listing and export, mirroring the backend). */
function filtersToParams({ status, query, columnFilters = {}, sortBy, sortDir } = {}) {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  if (query?.trim()) params.set('query', query.trim())
  if (sortBy) params.set('sort_by', sortBy)
  if (sortDir) params.set('sort_dir', sortDir)
  Object.entries(columnFilters).forEach(([key, value]) => {
    if (value?.trim()) params.set(`${COLUMN_FILTER_PREFIX}${key}`, value.trim())
  })
  return params
}

function fileNameFromDisposition(disposition) {
  return disposition?.match(/filename\s*=\s*"?([^";]+)"?/)?.[1]
}

export const api = {
  getMeta: () => request('/meta'),

  listForms: (filters, { limit, offset = 0 }) => {
    const params = filtersToParams(filters)
    params.set('limit', String(limit))
    params.set('offset', String(offset))
    return request(`/forms?${params}`)
  },

  getSummary: () => request('/forms/summary'),

  getForm: (formId) => request(`/forms/${formId}`),

  getFormImageUrl: (formId) => `${API_BASE_URL}/forms/${formId}/image`,

  confirmField: (formId, fieldId, correctedValue) =>
    request(`/forms/${formId}/fields/${fieldId}/confirm`, { method: 'PATCH', json: { corrected_value: correctedValue } }),

  addField: (formId, fieldName, value) =>
    request(`/forms/${formId}/fields`, { method: 'POST', json: { field_name: fieldName, value } }),

  deleteField: (formId, fieldId) => request(`/forms/${formId}/fields/${fieldId}`, { method: 'DELETE' }),

  retryForm: (formId) => request(`/forms/${formId}/retry`, { method: 'POST' }),

  uploadFiles: (files) => {
    const body = new FormData()
    files.forEach((file) => body.append('files', file))
    return request('/uploads', { method: 'POST', body })
  },

  exportForms: async (mode, filters) => {
    const params = filtersToParams(filters)
    params.set('mode', mode)
    const response = await fetch(`${API_BASE_URL}/forms/export?${params}`)
    if (!response.ok) throw await parseError(response)
    return {
      blob: await response.blob(),
      fileName: fileNameFromDisposition(response.headers.get('content-disposition')),
    }
  },
}
