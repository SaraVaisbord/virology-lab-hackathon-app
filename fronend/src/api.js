const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

async function request(path, options = {}) {
  const isFormData = options.body instanceof FormData
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...(options.headers || {}),
    },
  })

  const contentType = response.headers.get('content-type') || ''
  const payload = contentType.includes('application/json') ? await response.json() : await response.text()

  if (!response.ok) {
    const detail = typeof payload === 'object' && payload && 'detail' in payload ? payload.detail : payload
    throw new Error(typeof detail === 'string' ? detail : 'Request failed')
  }

  return payload
}

async function downloadFile(path, params = {}) {
  const query = new URLSearchParams(params)
  const response = await fetch(`${API_BASE_URL}${path}?${query.toString()}`)

  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || 'Export failed')
  }

  const contentType = response.headers.get('content-type') || 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  const blob = await response.blob()
  const disposition = response.headers.get('content-disposition') || ''
  const match = disposition.match(/filename\s*=\s*"?([^";]+)"?/) || []

  return {
    data: blob,
    contentType,
    fileName: match[1] || 'forms_export.xlsx',
  }
}

export const api = {
  getBaseUrl: () => API_BASE_URL,
  getFormImageUrl: (formId) => `${API_BASE_URL}/forms/${formId}/image`,

  listForms: async ({ limit = 100, offset = 0, status } = {}) => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    if (status) params.set('status', status)
    return request(`/forms?${params.toString()}`)
  },

  getForm: async (formId) => request(`/forms/${formId}`),

  updateField: async (formId, fieldName, { corrected_value, status = 'confirmed' } = {}) => request(`/forms/${formId}/fields/${encodeURIComponent(fieldName)}`, {
    method: 'PATCH',
    body: JSON.stringify({ corrected_value, status }),
  }),

  uploadFiles: async (files) => {
    const formData = new FormData()
    files.forEach((file) => formData.append('files', file))
    return request('/uploads', { method: 'POST', body: formData })
  },

  exportForms: async ({ mode = 'all', status, query, filters = {} } = {}) => {
    const params = new URLSearchParams({ mode, limit: '500', offset: '0' })
    if (status && status !== 'all') params.set('status', status)
    if (query) params.set('query', query)
    Object.entries(filters).forEach(([key, value]) => {
      if (value) params.set(`filter_${key}`, value)
    })
    return downloadFile('/forms/export', Object.fromEntries(params.entries()))
  },
}
