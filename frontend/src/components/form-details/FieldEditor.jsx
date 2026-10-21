import { useEffect, useRef, useState } from 'react'
import { Barcode, Bot, CheckCircle2, Loader2, ScanText } from 'lucide-react'
import StatusBadge from '../ui/StatusBadge'
import { useMeta } from '../../meta/MetaContext'
import { EMPTY, fieldDisplayValue } from '../../lib/format'
import { fieldsUsing, fitsKind, valueKey } from '../../lib/pageNumbers'
import PageNumberRow from './PageNumberRow'

const AGREEMENT_STYLES = {
  agree: 'border-teal-200 bg-teal-50 text-teal-800 dark:border-teal-900 dark:bg-teal-950/30 dark:text-teal-200',
  conflict: 'border-orange-300 bg-orange-50 text-orange-800 dark:border-orange-900 dark:bg-orange-950/30 dark:text-orange-200',
  insufficient: 'border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200',
}

function SourceRow({ icon: Icon, title, children }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-slate-700 dark:bg-slate-800">
      <div className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-gray-600 dark:text-gray-300">
        <Icon size={14} aria-hidden="true" /> {title}
      </div>
      {children}
    </div>
  )
}

function ValueLine({ value, note, onUse }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg bg-white px-2.5 py-2 dark:bg-slate-900">
      <span className="min-w-0">
        <span dir="auto" className="block break-all text-base tracking-wide text-gray-800 dark:text-gray-100">{value}</span>
        {note && <span className="block text-[11px] text-gray-500 dark:text-gray-400">{note}</span>}
      </span>
      {onUse && (
        <button type="button" onClick={() => onUse(value)} className="shrink-0 text-xs font-medium text-teal-700 hover:text-teal-900 dark:text-teal-300">
          השתמש בערך
        </button>
      )}
    </div>
  )
}

/** What each source (AI / barcode / OCR) read for this field, plus the agreement verdict. */
function SourceEvidence({ field, sources, onUse }) {
  const meta = useMeta()
  const evidence = field.evidence
  if (!evidence) return null
  if (evidence.manual) {
    return (
      <div className="rounded-lg border border-teal-200 bg-teal-50 px-3 py-2 text-sm text-teal-800 dark:border-teal-900 dark:bg-teal-950/30 dark:text-teal-200">
        הערך הוזן ידנית על ידי הלבורנטית
      </div>
    )
  }
  const { llm, barcode_candidates: barcodes = [], assignment, agreement } = evidence
  const barcodeSource = sources?.barcode_result
  const ocrSource = sources?.ocr_result

  const sourceStatusText = (source) => {
    if (!source) return 'לא הורץ'
    if (source.status === 'ok') return null
    return `${meta.source_status_labels[source.status] ?? source.status}${source.error || source.reason ? ` – ${source.error || source.reason}` : ''}`
  }

  return (
    <div className="space-y-2">
      <div className={`rounded-lg border px-3 py-2 text-sm font-medium ${AGREEMENT_STYLES[agreement] ?? AGREEMENT_STYLES.insufficient}`}>
        {meta.agreement_labels[agreement]}
      </div>

      <SourceRow icon={Bot} title={meta.source_labels.llm}>
        {llm ? (
          <>
            <ValueLine
              value={llm.value}
              note={[meta.confidence_labels[llm.confidence], llm.label ? `תווית ליד הערך: "${llm.label}"` : 'לא זוהתה תווית ליד הערך'].filter(Boolean).join(' · ')}
              onUse={onUse}
            />
            {assignment?.also_claimed_by?.length > 0 && (
              <p className="mt-1.5 text-xs text-orange-700 dark:text-orange-300">
                אותו מספר זוהה גם כ: {assignment.also_claimed_by.map(meta.fieldLabel).join(', ')}
              </p>
            )}
          </>
        ) : <p className="text-sm text-gray-500 dark:text-gray-400">ה-AI לא החזיר ערך זה{sources?.llm_result ? '' : ' (לא הופעל לעמוד זה)'}</p>}
        {evidence.alternatives?.length > 0 && (
          <p className="mt-1.5 text-xs text-gray-600 dark:text-gray-300">ערכים נוספים שנמצאו לשדה: {evidence.alternatives.join(', ')}</p>
        )}
      </SourceRow>

      <SourceRow icon={Barcode} title={meta.source_labels.barcode}>
        {sourceStatusText(barcodeSource) ? (
          <p className="text-sm text-gray-500 dark:text-gray-400">{sourceStatusText(barcodeSource)}</p>
        ) : barcodes.length === 0 ? (
          <p className="text-sm text-gray-500 dark:text-gray-400">אין ברקוד בעמוד שקורא ערך זה</p>
        ) : (
          <div className="space-y-1.5">
            {barcodes.map((barcode) => (
              <ValueLine
                key={`${barcode.data}-${barcode.match}`}
                value={barcode.data}
                note={[meta.barcode_match_labels[barcode.match], barcode.type].filter(Boolean).join(' · ')}
                onUse={onUse}
              />
            ))}
          </div>
        )}
      </SourceRow>

      <SourceRow icon={ScanText} title={meta.source_labels.ocr}>
        {sourceStatusText(ocrSource) ? (
          <p className="text-sm text-gray-500 dark:text-gray-400">{sourceStatusText(ocrSource)}</p>
        ) : evidence.ocr ? (
          <ValueLine
            value={evidence.ocr.raw}
            note={[
              evidence.ocr.anchor ? `נמצא ${evidence.ocr.label}` // e.g. "under the central number 12043017"
                : evidence.ocr.label ? `ליד התווית "${evidence.ocr.label}"` : 'נקרא בעמוד, בלי תווית ליד – מאשר את הקריאה, לא את השדה',
              evidence.ocr.source === 'barcode' ? 'הערך נקרא מברקוד שליד התווית' : null,
              evidence.ocr.confidence != null && evidence.ocr.source !== 'barcode' ? `ביטחון OCR ${Math.round(evidence.ocr.confidence)}` : null,
            ].filter(Boolean).join(' · ')}
            onUse={onUse}
          />
        ) : (
          <p className="text-sm text-gray-500 dark:text-gray-400">לא נמצאה תווית מתאימה עם ערך זה בסריקה המקומית</p>
        )}
        {assignment?.ocr_assigned_elsewhere?.length > 0 && (
          <p className="mt-1.5 text-xs text-orange-700 dark:text-orange-300">
            בסריקה המקומית המספר נמצא ליד תווית של: {assignment.ocr_assigned_elsewhere.map(meta.fieldLabel).join(', ')}
          </p>
        )}
      </SourceRow>
    </div>
  )
}

export default function FieldEditor({ field, sources, numbers, fields, focusKey, onShow, onApprove, saving, error }) {
  const meta = useMeta()
  const [draft, setDraft] = useState('')
  const inputRef = useRef(null)

  useEffect(() => {
    setDraft(fieldDisplayValue(field))
    const timer = setTimeout(() => inputRef.current?.focus(), 80)
    return () => clearTimeout(timer)
  }, [field])

  const useValue = (value) => {
    setDraft(value)
    inputRef.current?.focus()
  }

  // Other numbers / dates on the page that fit this field — the value the worker needs is often one the field didn't get.
  const kind = meta.fieldKind(field.field_name)
  const ownKeys = new Set([field.value, field.llm_value, field.ocr_value, field.barcode_value].filter(Boolean).map((v) => valueKey(v, meta.datePattern)))
  const otherNumbers = (numbers ?? [])
    .filter((item) => fitsKind(item, kind) && !ownKeys.has(item.key))
    .map((item) => ({ item, usedBy: fieldsUsing(fields ?? [], item.key, meta.datePattern) }))
    .sort((a, b) => (a.usedBy.length > 0) - (b.usedBy.length > 0))

  const submit = (event) => {
    event.preventDefault()
    onApprove(draft.trim())
  }

  return (
    <form onSubmit={submit} className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-semibold text-gray-800 dark:text-gray-100">{meta.fieldLabel(field.field_name)}</span>
        <StatusBadge status={field.status} kind="field" />
      </div>

      {field.reason && (
        <div className="rounded-lg border border-review-200 bg-review-50 px-3 py-2 text-sm leading-6 text-review-900 dark:border-review-900 dark:bg-review-950/20 dark:text-review-200">
          <span className="font-bold">סיבת הספק: </span>{field.reason}
        </div>
      )}

      <SourceEvidence field={field} sources={sources} onUse={useValue} />

      {otherNumbers.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-slate-700 dark:bg-slate-800">
          <p className="mb-1.5 text-xs font-semibold text-gray-600 dark:text-gray-300">
            {kind === 'date' ? 'תאריכים נוספים שנמצאו בעמוד' : 'אפשרויות נוספות שנמצאו בעמוד'}
          </p>
          <ul className="space-y-1.5">
            {otherNumbers.map(({ item, usedBy }) => (
              <PageNumberRow key={item.key} item={item} usedBy={usedBy} focused={item.key === focusKey} onShow={onShow} onUse={useValue} />
            ))}
          </ul>
        </div>
      )}

      <label className="block">
        <span className="mb-1.5 block text-sm font-semibold text-gray-900 dark:text-gray-100">ערך מאושר</span>
        <input
          ref={inputRef}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="הזן את הערך הנכון..."
          dir="auto"
          className="h-12 w-full rounded-xl border-2 border-teal-400 bg-white px-4 text-base text-gray-900 shadow-sm focus:outline-none focus:ring-4 focus:ring-teal-400/20 dark:bg-slate-800 dark:text-gray-100"
        />
      </label>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">{error}</div>
      )}

      <div className="flex flex-wrap items-center justify-end gap-3">
        <button type="button" onClick={() => setDraft(fieldDisplayValue(field))} disabled={saving} className="px-3 py-2 text-sm text-gray-600 hover:text-gray-900 dark:text-gray-300">
          איפוס
        </button>
        <button type="submit" disabled={saving} className="inline-flex h-11 items-center gap-2 rounded-lg bg-teal-700 px-5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-teal-800 disabled:opacity-60">
          {saving ? <Loader2 size={17} className="animate-spin" /> : <CheckCircle2 size={17} />}
          {saving ? 'שומר...' : 'אשר שדה'}
        </button>
      </div>
    </form>
  )
}
