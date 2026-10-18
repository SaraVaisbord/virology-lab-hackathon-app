import { useRef, useState, useEffect, useMemo } from 'react'
import { AlertTriangle, CheckCircle2, Save, ZoomIn, ZoomOut, Undo2 } from 'lucide-react'
import ModalShell from './ui/ModalShell'

const FIELD_LABELS = {
  first_name: 'שם פרטי',
  last_name: 'שם משפחה',
  id_number: 'מספר ת.ז.',
  central_number: 'מספר מרכזי',
  received_date: 'תאריך קבלה',
  sender: 'גורם שולח',
  commitment_number: 'מספר התחייבות',
}

const getFieldConfidenceLabel = (field) => {
  if (field?.status === 'not_found') return 'לא נמצא בטופס'
  if (field?.status === 'uncertain') return 'לא ודאי'
  if (field?.status === 'unverified') return 'לא מאומת'
  if (field?.status === 'confirmed') return 'מאושר'
  return 'מאושר'
}

const getReasonText = (field) => {
  if (field?.reason) return field.reason
  if (field?.status === 'not_found') return 'שדה לא נמצא בטופס'
  if (field?.status === 'uncertain') return 'ערך לא ודאי – יש לבדוק שוב'
  if (field?.status === 'unverified') return 'שדה עדיין לא אומת'
  return 'אין סיבת ספק זמינה'
}

const getFieldDisplayValue = (field) => {
  if (!field) return ''
  if (field.corrected_value !== null && field.corrected_value !== undefined && field.corrected_value !== '') return String(field.corrected_value)
  if (field.value !== null && field.value !== undefined && field.value !== '') return String(field.value)
  if (field.raw_value !== null && field.raw_value !== undefined && field.raw_value !== '') return String(field.raw_value)
  return ''
}

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

  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || 'Request failed')
  }

  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) return response.json()
  return response.text()
}

export default function ValidationModal({ form, fieldKey, field, onClose, onSave, onUndoApproval }) {
  const [value, setValue] = useState(getFieldDisplayValue(field))
  const [saveError, setSaveError] = useState('')
  const [zoom, setZoom] = useState(1)
  const [saving, setSaving] = useState(false)
  const [imageFailed, setImageFailed] = useState(false)
  const inputRef = useRef(null)

  useEffect(() => {
    setValue(getFieldDisplayValue(field))
    setSaveError('')
    setImageFailed(false)
    const timer = setTimeout(() => inputRef.current?.focus(), 80)
    return () => clearTimeout(timer)
  }, [field])

  // ה-hooks חייבים להיות לפני ה-return המוקדם
  const bboxData = useMemo(() => {
    if (!field?.bbox) return null
    try {
      return typeof field.bbox === 'string' ? JSON.parse(field.bbox) : field.bbox
    } catch {
      return null
    }
  }, [field])

  const highlightStyle = useMemo(() => {
    if (bboxData && bboxData.x != null && bboxData.y != null && bboxData.width != null && bboxData.height != null) {
      return {
        left: `${Math.max(0, bboxData.x / 12)}%`,
        top: `${Math.max(0, bboxData.y / 16)}%`,
        width: `${Math.max(40, (bboxData.width || 120) / 12)}%`,
        height: `${Math.max(32, (bboxData.height || 60) / 16)}%`,
      }
    }
    if (field && field.x != null && field.y != null && field.width && field.height) {
      return {
        left: `${field.x / 12}%`,
        top: `${field.y / 16}%`,
        width: `${Math.max(40, (field.width || 120) / 12)}%`,
        height: `${Math.max(32, (field.height || 60) / 16)}%`,
      }
    }
    return null
  }, [field, bboxData])

  if (!form || !field) return null

  const ocrValue = field.ocr_value ?? field.raw_value ?? field.value ?? null
  const llmValue = field.llm_value ?? field.value ?? field.raw_value ?? null
  const currentValue = value || getFieldDisplayValue(field) || ''
  const fileName = form.source_file ?? form.fileName ?? '—'

  const posX = field.x ?? bboxData?.x
  const posY = field.y ?? bboxData?.y
  const positionText = posX != null && posY != null ? `${posX}\u200F, ${posY}` : '—'

  const persistSave = async (nextValue) => {
    if (!fieldKey || !form?.id) return false
    try {
      setSaving(true)
      setSaveError('')

      const payload = { corrected_value: nextValue, status: 'confirmed' }
      const result = await request(`/forms/${form.id}/fields/${encodeURIComponent(fieldKey)}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      })

      if (onSave) {
        const ok = await onSave(form.id, fieldKey, nextValue, result)
        if (ok === false) {
          setSaveError('שמירה נכשלה. אנא נסה שוב.')
          return false
        }
      }

      return true
    } catch (error) {
      setSaveError(error.message || 'שמירה נכשלה. אנא נסה שוב.')
      return false
    } finally {
      setSaving(false)
    }
  }

  const handleSave = async () => {
    const trimmed = value.trim()
    if (!trimmed) {
      setSaveError('הערך שהוזן ריק. יש להזין ערך תקין או לבטל את הפעולה.')
      return
    }

    const ok = await persistSave(trimmed)
    if (!ok) return

    onClose()
  }

  const handleUseValue = (chosenValue) => {
    if (chosenValue == null || chosenValue === '') return
    setValue(String(chosenValue))
    setSaveError('')
    inputRef.current?.focus()
  }

  const handleUndo = () => {
    if (onUndoApproval) onUndoApproval(form.id, fieldKey)
    onClose()
  }

  const imageNode = (
    <div className="relative overflow-hidden rounded-xl border border-gray-200 bg-white">
      <div className="overflow-auto max-h-[400px]">
        <div
          className="relative transition-transform duration-200 ease-out"
          style={{ transform: `scale(${zoom})`, transformOrigin: 'top center', width: `${100 / zoom}%` }}
        >
          {form.image_url && !imageFailed ? (
            <img
              src={form.image_url}
              alt="צילום דוגמה של טופס"
              onError={() => setImageFailed(true)}
              className="w-full h-auto block"
            />
          ) : (
            <div className="flex min-h-[260px] items-center justify-center rounded-lg border border-dashed border-slate-300 bg-slate-100 text-sm text-gray-500 dark:border-slate-700 dark:bg-slate-800 dark:text-gray-400">
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
      <div className="flex items-center justify-between gap-2 border-t border-gray-200 bg-white p-2.5">
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span>זום</span>
          <button
            type="button"
            aria-label="הקטנת זום"
            onClick={() => setZoom((v) => Math.max(1, Number((v - 0.25).toFixed(2))))}
            className="rounded-lg border border-gray-300 bg-white p-2 text-gray-600 hover:bg-gray-50"
          >
            <ZoomOut size={16} />
          </button>
          <button
            type="button"
            aria-label="הגדלת זום"
            onClick={() => setZoom((v) => Math.min(2, Number((v + 0.25).toFixed(2))))}
            className="rounded-lg border border-gray-300 bg-white p-2 text-gray-600 hover:bg-gray-50"
          >
            <ZoomIn size={16} />
          </button>
        </div>
        <span className="text-xs text-gray-500">מיקום: {positionText}</span>
      </div>
    </div>
  )

  const valueCard = (label, val) => (
    <div className="rounded-2xl border border-gray-200 bg-gray-50 p-4">
      <div className="mb-2.5 flex items-center justify-between gap-3">
        <span className="text-sm font-medium text-gray-700">{label}</span>
        <button
          type="button"
          onClick={() => handleUseValue(val)}
          className="text-sm font-medium text-teal-700 hover:text-teal-900 transition-colors"
          disabled={val == null || val === ''}
        >
          השתמש בערך הזה
        </button>
      </div>
      <div className="flex h-11 items-center rounded-lg bg-white px-2.5 text-right text-base tracking-wide text-gray-800 break-all">
        {val ?? '—'}
      </div>
    </div>
  )

  return (
    <ModalShell
      title={`אימות שדה: ${FIELD_LABELS[fieldKey] || fieldKey}`}
      icon={AlertTriangle}
      onClose={onClose}
      footer={
        <>
          <button type="button" onClick={onClose} className="px-3 text-[15px] text-gray-600 hover:text-gray-900" disabled={saving}>
            ביטול
          </button>
          {field.status === 'approved' && onUndoApproval && (
            <button
              type="button"
              onClick={handleUndo}
              className="inline-flex h-[45px] items-center gap-2 rounded-lg bg-amber-500 px-[26px] text-[15px] font-semibold text-white hover:bg-amber-600"
              disabled={saving}
            >
              <Undo2 size={17} /> בטל אישור
            </button>
          )}
          <button
            type="button"
            onClick={() => persistSave(value.trim())}
            className="inline-flex h-[45px] items-center gap-2 rounded-lg bg-teal-700 px-[26px] text-[15px] font-semibold text-white shadow-sm transition-colors duration-150 hover:bg-teal-800 disabled:opacity-60"
            disabled={saving}
          >
            <CheckCircle2 size={17} /> {saving ? 'ממתין...' : 'אישור שדה'}
          </button>
          <button
            type="button"
            onClick={handleSave}
            className="inline-flex h-[45px] items-center gap-2 rounded-lg bg-[#0A2540] px-[26px] text-[15px] font-semibold text-white shadow-sm transition-colors duration-150 hover:bg-[#081d2f] disabled:opacity-60"
            disabled={saving}
          >
            <Save size={17} /> {saving ? 'שומר...' : 'שמירה וסגירה'}
          </button>
        </>
      }
      maxWidth="max-w-[1120px]"
    >
      <div className="space-y-6">
        <div className="flex items-center text-[13px] text-gray-500">
          <span>
            קובץ: <span className="font-medium text-gray-700">{fileName}</span>
            {field.page && <> · עמוד <span className="font-medium text-gray-700">{field.page}</span></>}
          </span>
          <span className="mr-2.5 inline-flex items-center rounded-full bg-gray-100 px-2.5 py-1 text-[11px] font-medium text-gray-600">
            {getFieldConfidenceLabel(field)}
          </span>
        </div>

        <div className="grid items-start gap-5 lg:grid-cols-[1.3fr_1fr]">
          <div>{imageNode}</div>

          <div className="space-y-5">
            <div className="rounded-xl border border-pink-200 bg-pink-50 px-5 py-4 text-right text-[15px] leading-6 text-pink-700">
              <span className="font-bold">סיבת הספק:</span> {getReasonText(field)}
            </div>

            <div className="grid gap-4">
              {valueCard('ערך OCR', ocrValue)}
              {valueCard('ערך LLM', llmValue)}
            </div>
          </div>
        </div>

        {saveError && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {saveError}
          </div>
        )}

        <div className="w-full">
          <label className="mb-2.5 block text-[15px] font-semibold text-gray-900">ערך מתוקן</label>
          <input
            ref={inputRef}
            type="text"
            value={value}
            onChange={(e) => {
              setValue(e.target.value)
              setSaveError('')
            }}
            onKeyDown={(e) => e.key === 'Enter' && handleSave()}
            placeholder="הזן ערך מתוקן..."
            className="h-[54px] w-full rounded-xl border-2 border-teal-400 bg-white px-4 text-sm text-gray-900 shadow-sm focus:outline-none focus:ring-4 focus:ring-teal-400/20"
            dir="ltr"
            aria-label="ערך מתוקן"
          />
          <p className="mt-2 text-xs text-gray-400">ערך נוכחי: {currentValue || '—'}</p>
        </div>
      </div>
    </ModalShell>
  )
}