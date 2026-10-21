import { createContext, useContext, useEffect, useState } from 'react'
import { api } from '../api'

/**
 * Domain vocabulary (field names, statuses, Hebrew labels) and UI settings come from the backend (GET /meta),
 * so the frontend never keeps its own copy of them.
 */
const MetaContext = createContext(null)

function buildMeta(raw) {
  return {
    ...raw,
    fieldLabel: (key) => raw.fields.find((field) => field.key === key)?.label ?? raw.form_columns[key] ?? key,
    isMultiValue: (key) => raw.fields.some((field) => field.key === key && field.multi_value),
    fieldKind: (key) => raw.fields.find((field) => field.key === key)?.kind ?? 'text',
    datePattern: new RegExp(raw.date_pattern),
    isPendingForm: (status) => raw.pending_form_statuses.includes(status),
    needsReview: (field) => raw.review_field_statuses.includes(field?.status),
  }
}

export function MetaProvider({ children }) {
  const [meta, setMeta] = useState(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    setError('')
    api.getMeta()
      .then((raw) => { if (!cancelled) setMeta(buildMeta(raw)) })
      .catch((err) => { if (!cancelled) setError(err.message) })
    return () => { cancelled = true }
  }, [attempt])

  if (error) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-3 p-6 text-center" dir="rtl">
        <p className="text-base font-semibold text-red-700 dark:text-red-300">לא ניתן להתחבר לשרת</p>
        <p className="text-sm text-gray-500">{error}</p>
        <button type="button" className="btn-primary" onClick={() => setAttempt((value) => value + 1)}>נסה שוב</button>
      </div>
    )
  }

  if (!meta) {
    return <div className="flex h-screen items-center justify-center text-sm text-gray-500" dir="rtl">טוען...</div>
  }

  return <MetaContext.Provider value={meta}>{children}</MetaContext.Provider>
}

export function useMeta() {
  const meta = useContext(MetaContext)
  if (!meta) throw new Error('useMeta must be used inside <MetaProvider>')
  return meta
}
