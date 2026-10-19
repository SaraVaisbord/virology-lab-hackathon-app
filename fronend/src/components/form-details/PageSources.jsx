import { Barcode, Bot, ScanText } from 'lucide-react'
import { useMeta } from '../../meta/MetaContext'

const UNASSIGNED = 'none'

function Chip({ value, note, tone = 'neutral', children }) {
  const tones = {
    neutral: 'border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900',
    warn: 'border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-950/30',
  }
  return (
    <li className={`rounded-lg border px-2 py-1 text-xs ${tones[tone]}`}>
      <span dir="ltr" className="font-mono text-gray-800 dark:text-gray-100">{value}</span>
      {note && <span className="text-gray-400"> · {note}</span>}
      {children && <span className="block">{children}</span>}
    </li>
  )
}

function Section({ icon: Icon, title, children }) {
  return (
    <div>
      <p className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-gray-600 dark:text-gray-300">
        <Icon size={14} aria-hidden="true" /> {title}
      </p>
      {children}
    </div>
  )
}

/**
 * Everything each source found on the page — including numbers no field took, so no number read from the page
 * is silently dropped and the lab worker can decide.
 */
export default function PageSources({ sources, fields, onSelectField }) {
  const meta = useMeta()
  if (!sources) return null
  const { barcode_result: barcodeResult, ocr_result: ocrResult, llm_result: llmResult } = sources
  const errors = Object.entries(sources.source_errors ?? {})
  const statusText = (result) => (!result ? 'לא הורץ' : `${meta.source_status_labels[result.status] ?? result.status}${result.reason || result.error ? ` – ${result.reason || result.error}` : ''}`)

  // Field rows that use a value (barcode match, OCR reading or LLM reading).
  const usage = (value) => fields.filter((field) => [field.barcode_value, field.ocr_value, field.llm_value].includes(value)
    || field.evidence?.barcode_candidates?.some((candidate) => candidate.data === value))
  const llmUnassigned = (llmResult?.all_numbers ?? []).filter((item) => item.assigned_to === UNASSIGNED)

  return (
    <div className="space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800">
      <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">מה כל מקור מצא בעמוד</p>

      {errors.length > 0 && (
        <ul className="space-y-1 text-xs text-red-700 dark:text-red-300">
          {errors.map(([source, message]) => <li key={source}>{meta.source_labels[source] ?? source}: {message}</li>)}
        </ul>
      )}

      <Section icon={Barcode} title={meta.source_labels.barcode}>
        {barcodeResult?.status !== 'ok' ? (
          <p className="text-xs text-gray-500">{statusText(barcodeResult)}</p>
        ) : barcodeResult.items.length === 0 ? (
          <p className="text-xs text-gray-500">לא נמצאו ברקודים בעמוד</p>
        ) : (
          <ul className="flex flex-wrap gap-1.5">
            {barcodeResult.items.map((item, index) => {
              const usedBy = usage(item.data)
              return (
                <Chip key={`${item.data}-${index}`} value={item.data} note={item.type} tone={usedBy.length ? 'neutral' : 'warn'}>
                  {usedBy.length === 0 ? (
                    <span className="text-amber-700 dark:text-amber-300">לא שויך לשום שדה</span>
                  ) : usedBy.map((field) => (
                    <button key={field.id} type="button" onClick={() => onSelectField(field.id)} className="ml-2 text-teal-700 hover:underline dark:text-teal-300">
                      {meta.fieldLabel(field.field_name)}
                    </button>
                  ))}
                </Chip>
              )
            })}
          </ul>
        )}
      </Section>

      <Section icon={ScanText} title={meta.source_labels.ocr}>
        {ocrResult?.status !== 'ok' ? (
          <p className="text-xs text-gray-500">{statusText(ocrResult)}</p>
        ) : (
          <>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              תוויות שזוהו: {ocrResult.labels?.length ? [...new Set(ocrResult.labels.map((label) => meta.fieldLabel(label.field)))].join(', ') : 'אין'}
            </p>
            {ocrResult.unassigned_numbers?.length > 0 && (
              <>
                <p className="mt-1.5 text-xs text-gray-500 dark:text-gray-400">מספרים שנקראו בלי תווית ליד (לא שויכו):</p>
                <ul className="mt-1 flex flex-wrap gap-1.5">
                  {ocrResult.unassigned_numbers.map((item, index) => (
                    <Chip key={`${item.value}-${item.source}-${index}`} value={item.raw} note={meta.source_labels[item.source] ?? item.source} tone="warn" />
                  ))}
                </ul>
              </>
            )}
          </>
        )}
      </Section>

      <Section icon={Bot} title={meta.source_labels.llm}>
        {!llmResult ? (
          <p className="text-xs text-gray-500">לא הופעל לעמוד זה</p>
        ) : llmUnassigned.length === 0 ? (
          <p className="text-xs text-gray-500 dark:text-gray-400">כל המספרים שה-AI רשם שויכו לשדות</p>
        ) : (
          <>
            <p className="text-xs text-gray-500 dark:text-gray-400">מספרים שה-AI ראה ולא ידע לשייך:</p>
            <ul className="mt-1 flex flex-wrap gap-1.5">
              {llmUnassigned.map((item, index) => (
                <Chip key={`${item.value}-${index}`} value={item.value} note={item.label || item.kind} tone="warn" />
              ))}
            </ul>
          </>
        )}
      </Section>
    </div>
  )
}
