import { useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, Loader2, Save, ZoomIn, ZoomOut } from 'lucide-react'
import ModalShell from './ui/ModalShell'
import { api } from '../api'

const formatDate = (value) => {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('he-IL', { dateStyle: 'short', timeStyle: 'short' }).format(date)
}

const fieldLabelMap = {
  first_name: 'שם פרטי',
  last_name: 'שם משפחה',
  id_number: 'מספר ת.ז.',
  central_number: 'מספר מרכזי',
  received_date: 'תאריך קבלה',
  sender: 'גורם שולח',
  commitment_number: 'מספר התחייבות',
}

const getFieldStatusLabel = (status) => {
  if (status === 'not_found') return 'לא נמצא'
  if (status === 'uncertain') return 'לא ודאי'
  if (status === 'unverified') return 'לא מאומת'
  if (status === 'verified') return 'מאומת'
  if (status === 'confirmed') return 'אושר'
  return status || 'לא ידוע'
}

const getFieldDisplayValue = (field) => {
  if (!field) return ''
  if (field.corrected_value !== null && field.corrected_value !== undefined && field.corrected_value !== '') return String(field.corrected_value)
  if (field.value !== null && field.value !== undefined && field.value !== '') return String(field.value)
  if (field.raw_value !== null && field.raw_value !== undefined && field.raw_value !== '') return String(field.raw_value)
  if (field.ocr_value !== null && field.ocr_value !== undefined && field.ocr_value !== '') return String(field.ocr_value)
  if (field.llm_value !== null && field.llm_value !== undefined && field.llm_value !== '') return String(field.llm_value)
  return ''
}

const getReasonText = (field) => {
  if (!field) return 'אין סיבת ספק זמינה'
  if (field.reason) return field.reason
  if (field.status === 'not_found') return 'שדה לא נמצא בטופס'
  if (field.status === 'uncertain') return 'ערך לא ודאי – יש לבדוק שוב'
  if (field.status === 'unverified') return 'שדה עדיין לא אומת'
  return 'אין סיבת ספק זמינה'
}

export default function FormDetailsModal({ form, onClose }) {
  const [detail, setDetail] = useState(form)
  const [imageUrl, setImageUrl] = useState('')
  const [imageFailed, setImageFailed] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedFieldKey, setSelectedFieldKey] = useState(null)
  const [draftValue, setDraftValue] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [zoom, setZoom] = useState(1)
  const inputRef = useRef(null)

  useEffect(() => {
    if (!form?.id) return
    let cancelled = false

    const load = async () => {
      setLoading(true)
      setError('')

      try {
        const data = await api.getForm(form.id)
        if (!cancelled) {
          setDetail(data)
          setImageUrl(api.getFormImageUrl(form.id))
          setImageFailed(false)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message || 'לא ניתן לטעון את פרטי הטופס.')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => { cancelled = true }
  }, [form])

  const extractedFields = Array.isArray(detail?.fields)
    ? detail.fields
    : Array.isArray(detail?.extracted_fields)
      ? detail.extracted_fields
      : []

  const activeField = extractedFields.find((field) => field.field_name === selectedFieldKey) || extractedFields[0] || null

  useEffect(() => {
    if (!selectedFieldKey && activeField) {
      setSelectedFieldKey(activeField.field_name)
    }
  }, [activeField, selectedFieldKey])

  useEffect(() => {
    if (!activeField) return
    const nextValue = getFieldDisplayValue(activeField)
    setDraftValue(nextValue)
    setSaveError('')
    const timer = setTimeout(() => inputRef.current?.focus(), 80)
    return () => clearTimeout(timer)
  }, [activeField])

  const uncertainFields = extractedFields.filter((field) => ['unverified', 'uncertain', 'not_found'].includes(field.status))

  const bboxData = useMemo(() => {
    if (!activeField?.bbox) return null
    try {
      return typeof activeField.bbox === 'string' ? JSON.parse(activeField.bbox) : activeField.bbox
    } catch {
      return null
    }
  }, [activeField])

  const highlightStyle = useMemo(() => {
    if (!activeField) return null

    const x = activeField.x ?? bboxData?.x
    const y = activeField.y ?? bboxData?.y
    const width = activeField.width ?? bboxData?.width
    const height = activeField.height ?? bboxData?.height

    if (x != null && y != null && width != null && height != null) {
      return {
        left: `${Math.max(0, x / 12)}%`,
        top: `${Math.max(0, y / 16)}%`,
        width: `${Math.max(30, (width || 120) / 12)}%`,
        height: `${Math.max(24, (height || 60) / 16)}%`,
      }
    }

    return null
  }, [activeField, bboxData])

  const refreshDetail = async () => {
    if (!detail?.id) return
    const refreshed = await api.getForm(detail.id)
    setDetail(refreshed)
    setImageUrl(api.getFormImageUrl(refreshed.id))
    setImageFailed(false)
    return refreshed
  }

  const handleSave = async (approve = true) => {
    if (!activeField || !detail?.id) return
    const nextValue = draftValue.trim()

    if (!nextValue) {
      setSaveError('הערך שהוזן ריק. יש להזין ערך תקין או לבטל את הפעולה.')
      return
    }

    setSaving(true)
    setSaveError('')

    try {
      await api.updateField(detail.id, activeField.field_name, {
        corrected_value: nextValue,
        status: approve ? 'confirmed' : 'confirmed',
      })

      const refreshed = await refreshDetail()
      if (refreshed) {
        const nextActive = refreshed.fields?.find((field) => field.field_name === activeField.field_name) || refreshed.fields?.[0] || null
        if (nextActive) setSelectedFieldKey(nextActive.field_name)
      }
    } catch (err) {
      setSaveError(err.message || 'שמירה נכשלה. אנא נסה שוב.')
    } finally {
      setSaving(false)
    }
  }

  const useSuggestedValue = (valueToUse) => {
    if (valueToUse == null || valueToUse === '') return
    setDraftValue(String(valueToUse))
    setSaveError('')
    inputRef.current?.focus()
  }

  const documentPosition = activeField?.x != null && activeField?.y != null ? `${activeField.x}, ${activeField.y}` : '—'
  const currentValue = getFieldDisplayValue(activeField)
  const ocrValue = activeField?.ocr_value ?? activeField?.raw_value ?? activeField?.value ?? null
  const llmValue = activeField?.llm_value ?? activeField?.value ?? activeField?.raw_value ?? null

  if (!form) return null

  return (
    <ModalShell title={`טופס #${detail?.id ?? form.id}`} icon={AlertTriangle} onClose={onClose} maxWidth="max-w-[1200px]">
      <div className="space-y-4" dir="rtl">
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
            <Loader2 size={16} className="animate-spin" /> טוען פרטים ותמונה...
          </div>
        ) : error ? (
          <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">
            {error}
          </div>
        ) : (
          <div className="grid gap-5 xl:grid-cols-[1.3fr_1fr]">
            <div className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800">
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <p className="text-xs text-gray-500 dark:text-gray-400">שם קובץ</p>
                      <p className="mt-1 font-medium text-gray-800 dark:text-gray-200">{detail?.source_file || '—'}</p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500 dark:text-gray-400">עמוד</p>
                      <p className="mt-1 font-medium text-gray-800 dark:text-gray-200">{detail?.page_number ?? '—'}</p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500 dark:text-gray-400">סטטוס</p>
                      <p className="mt-1 font-medium text-gray-800 dark:text-gray-200">{detail?.status || '—'}</p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500 dark:text-gray-400">תאריך העלאה</p>
                      <p className="mt-1 font-medium text-gray-800 dark:text-gray-200">{formatDate(detail?.uploaded_at)}</p>
                    </div>
                    <div className="col-span-2">
                      <p className="text-xs text-gray-500 dark:text-gray-400">file_hash</p>
                      <p className="mt-1 font-mono text-[11px] break-all text-gray-800 dark:text-gray-200">{detail?.file_hash || '—'}</p>
                    </div>
                  </div>
                </div>

                <div className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900">
                  {imageUrl && !imageFailed ? (
                    <img
                      src={imageUrl}
                      alt={`טופס ${detail?.id ?? form.id}`}
                      onError={() => setImageFailed(true)}
                      className="w-full h-auto max-h-[360px] object-contain rounded-lg bg-slate-100 dark:bg-slate-800"
                    />
                  ) : (
                    <div className="flex min-h-[220px] items-center justify-center rounded-lg border border-dashed border-slate-300 bg-slate-100 text-sm text-gray-500 dark:border-slate-700 dark:bg-slate-800 dark:text-gray-400">
                      אין תמונה זמינה
                    </div>
                  )}
                </div>
              </div>

              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">שדות שהתקבלו</p>
                  <span className="rounded-full bg-slate-200 px-2 py-0.5 text-[10px] font-bold text-slate-700 dark:bg-slate-700 dark:text-slate-100">
                    {extractedFields.length}
                  </span>
                </div>

                {extractedFields.length === 0 ? (
                  <p className="text-sm text-gray-500 dark:text-gray-400">אין שדות עדיין.</p>
                ) : (
                  <div className="space-y-2">
                    {extractedFields.map((field) => {
                      const isActive = activeField?.field_name === field.field_name
                      return (
                        <button
                          key={field.id || `${field.field_name}-${field.form_id}`}
                          type="button"
                          onClick={() => setSelectedFieldKey(field.field_name)}
                          className={`flex w-full items-center justify-between rounded-lg border px-3 py-2 text-right transition ${
                            isActive
                              ? 'border-teal-500 bg-teal-50 dark:border-teal-400 dark:bg-teal-950/30'
                              : 'border-slate-300 bg-white hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800'
                          }`}
                        >
                          <span className="text-sm font-medium text-gray-800 dark:text-gray-100">
                            {fieldLabelMap[field.field_name] || field.field_name}
                          </span>
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-gray-500 dark:text-gray-400">
                              {field.corrected_value ?? field.value ?? field.ocr_value ?? field.llm_value ?? field.raw_value ?? '—'}
                            </span>
                            <span className="rounded-full bg-pink-100 px-2 py-0.5 text-[10px] font-bold text-pink-700 dark:bg-pink-950/60 dark:text-pink-200">
                              {getFieldStatusLabel(field.status)}
                            </span>
                          </div>
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>
            </div>

            <div className="space-y-4">
              {activeField && (
                <>
                  <div className="rounded-xl border border-pink-200 bg-pink-50 px-4 py-3 text-right text-[15px] leading-6 text-pink-700 dark:border-pink-900 dark:bg-pink-950/20 dark:text-pink-200">
                    <span className="font-bold">סיבת הספק:</span> {getReasonText(activeField)}
                  </div>

                  <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
                    <div className="mb-3 flex items-center justify-between">
                      <span className="text-sm font-semibold text-gray-800 dark:text-gray-100">
                        {fieldLabelMap[activeField.field_name] || activeField.field_name}
                      </span>
                      <span className="rounded-full bg-slate-100 px-2 py-1 text-[10px] font-bold text-slate-700 dark:bg-slate-700 dark:text-slate-200">
                        {getFieldStatusLabel(activeField.status)}
                      </span>
                    </div>

                    <div className="grid gap-3">
                      <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-slate-700 dark:bg-slate-800">
                        <div className="mb-2 flex items-center justify-between gap-3">
                          <span className="text-sm font-medium text-gray-700 dark:text-gray-200">ערך OCR</span>
                          <button
                            type="button"
                            onClick={() => useSuggestedValue(ocrValue)}
                            className="text-sm font-medium text-teal-700 hover:text-teal-900 dark:text-teal-300"
                            disabled={ocrValue == null || ocrValue === ''}
                          >
                            השתמש בערך הזה
                          </button>
                        </div>
                        <div className="rounded-lg bg-white px-2.5 py-3 text-right text-base tracking-wide text-gray-800 break-all dark:bg-slate-900 dark:text-gray-100">
                          {ocrValue ?? '—'}
                        </div>
                      </div>

                      <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-slate-700 dark:bg-slate-800">
                        <div className="mb-2 flex items-center justify-between gap-3">
                          <span className="text-sm font-medium text-gray-700 dark:text-gray-200">ערך LLM</span>
                          <button
                            type="button"
                            onClick={() => useSuggestedValue(llmValue)}
                            className="text-sm font-medium text-teal-700 hover:text-teal-900 dark:text-teal-300"
                            disabled={llmValue == null || llmValue === ''}
                          >
                            השתמש בערך הזה
                          </button>
                        </div>
                        <div className="rounded-lg bg-white px-2.5 py-3 text-right text-base tracking-wide text-gray-800 break-all dark:bg-slate-900 dark:text-gray-100">
                          {llmValue ?? '—'}
                        </div>
                      </div>
                    </div>

                    <div className="mt-5 space-y-3">
                      <label className="block text-[15px] font-semibold text-gray-900 dark:text-gray-100">ערך מתוקן</label>
                      <input
                        ref={inputRef}
                        type="text"
                        value={draftValue}
                        onChange={(e) => {
                          setDraftValue(e.target.value)
                          setSaveError('')
                        }}
                        onKeyDown={(e) => { if (e.key === 'Enter') handleSave(true) }}
                        placeholder="הזן ערך מתוקן..."
                        className="h-[54px] w-full rounded-xl border-2 border-teal-400 bg-white px-4 text-sm text-gray-900 shadow-sm focus:outline-none focus:ring-4 focus:ring-teal-400/20 dark:bg-slate-800 dark:text-gray-100"
                        dir="ltr"
                        aria-label="ערך מתוקן"
                      />

                      <div className="flex items-center justify-between gap-3 text-xs text-gray-500 dark:text-gray-400">
                        <span>ערך נוכחי: {currentValue || '—'}</span>
                        <span>מיקום: {documentPosition}</span>
                      </div>

                      {saveError && (
                        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">
                          {saveError}
                        </div>
                      )}

                      <div className="flex flex-wrap justify-end gap-3 pt-2">
                        <button
                          type="button"
                          onClick={() => setDraftValue(getFieldDisplayValue(activeField))}
                          className="px-3 py-2 text-[15px] text-gray-600 hover:text-gray-900 dark:text-gray-300"
                          disabled={saving}
                        >
                          ביטול
                        </button>
                        <button
                          type="button"
                          onClick={() => handleSave(true)}
                          className="inline-flex h-[45px] items-center gap-2 rounded-lg bg-[#0A2540] px-[22px] text-[15px] font-semibold text-white shadow-sm transition-colors duration-150 hover:bg-[#081d2f] disabled:opacity-60"
                          disabled={saving}
                        >
                          <CheckCircle2 size={17} /> {saving ? 'ממתין...' : 'אשר שדה'}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleSave(false)}
                          className="inline-flex h-[45px] items-center gap-2 rounded-lg bg-teal-700 px-[22px] text-[15px] font-semibold text-white shadow-sm transition-colors duration-150 hover:bg-teal-800 disabled:opacity-60"
                          disabled={saving}
                        >
                          <Save size={17} /> {saving ? 'שומר...' : 'שמור ערך'}
                        </button>
                      </div>
                    </div>
                  </div>
                </>
              )}

              {activeField && highlightStyle && (
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">תצוגת מסמך</span>
                    <div className="flex items-center gap-2 text-xs text-gray-500">
                      <button
                        type="button"
                        aria-label="הקטנת זום"
                        onClick={() => setZoom((value) => Math.max(1, Number((value - 0.25).toFixed(2))))}
                        className="rounded-lg border border-gray-300 bg-white p-2 text-gray-600 hover:bg-gray-50 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                      >
                        <ZoomOut size={16} />
                      </button>
                      <button
                        type="button"
                        aria-label="הגדלת זום"
                        onClick={() => setZoom((value) => Math.min(2, Number((value + 0.25).toFixed(2))))}
                        className="rounded-lg border border-gray-300 bg-white p-2 text-gray-600 hover:bg-gray-50 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                      >
                        <ZoomIn size={16} />
                      </button>
                    </div>
                  </div>

                  <div className="overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-slate-700 dark:bg-slate-900">
                    <div className="overflow-auto max-h-[260px]">
                      <div
                        className="relative transition-transform duration-200 ease-out"
                        style={{ transform: `scale(${zoom})`, transformOrigin: 'top center', width: `${100 / zoom}%` }}
                      >
                        {imageUrl && !imageFailed ? (
                          <img
                            src={imageUrl}
                            alt="תמונה של הטופס"
                            onError={() => setImageFailed(true)}
                            className="block h-auto w-full"
                          />
                        ) : (
                          <div className="flex min-h-[200px] items-center justify-center rounded-lg border border-dashed border-slate-300 bg-slate-100 text-sm text-gray-500 dark:border-slate-700 dark:bg-slate-800 dark:text-gray-400">
                            אין תמונה זמינה
                          </div>
                        )}

                        {highlightStyle && (
                          <div
                            className="absolute border-2 border-pink-500 bg-pink-500/10 shadow-[0_0_0_9999px_rgba(15,23,42,0.25)]"
                            style={{
                              left: highlightStyle.left,
                              top: highlightStyle.top,
                              width: highlightStyle.width,
                              height: highlightStyle.height,
                              borderRadius: '10px',
                            }}
                          />
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {detail?.error && (
                <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">
                  {detail.error}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </ModalShell>
  )
}