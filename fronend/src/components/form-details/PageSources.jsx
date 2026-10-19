import { Barcode, ScanText } from 'lucide-react'
import { useMeta } from '../../meta/MetaContext'

/**
 * Everything the local sources found on the page — including barcodes that were not assigned to any field,
 * so no number read from the page is silently dropped.
 */
export default function PageSources({ sources, fields, onSelectField }) {
  const meta = useMeta()
  if (!sources) return null
  const barcodeResult = sources.barcode_result
  const ocrResult = sources.ocr_result
  const errors = Object.entries(sources.source_errors ?? {})

  // Which field rows reference each barcode (exactly or as a near match).
  const usage = (data) => fields.filter((field) => field.evidence?.barcode_candidates?.some((candidate) => candidate.data === data))

  return (
    <div className="space-y-2 rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800">
      <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">מה המקורות המקומיים מצאו בעמוד</p>

      {errors.length > 0 && (
        <ul className="space-y-1 text-xs text-red-700 dark:text-red-300">
          {errors.map(([source, message]) => <li key={source}>{meta.source_labels[source] ?? source}: {message}</li>)}
        </ul>
      )}

      <div>
        <p className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-gray-600 dark:text-gray-300">
          <Barcode size={14} aria-hidden="true" /> {meta.source_labels.barcode}
        </p>
        {!barcodeResult ? (
          <p className="text-xs text-gray-500">לא הורץ</p>
        ) : barcodeResult.status !== 'ok' ? (
          <p className="text-xs text-gray-500">{meta.source_status_labels[barcodeResult.status]}</p>
        ) : barcodeResult.items.length === 0 ? (
          <p className="text-xs text-gray-500">לא נמצאו ברקודים בעמוד</p>
        ) : (
          <ul className="flex flex-wrap gap-1.5">
            {barcodeResult.items.map((item, index) => {
              const usedBy = usage(item.data)
              return (
                <li key={`${item.data}-${index}`} className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900">
                  <span dir="ltr" className="font-mono text-gray-800 dark:text-gray-100">{item.data}</span>
                  <span className="text-gray-400"> · {item.type}</span>
                  <span className="block">
                    {usedBy.length === 0 ? (
                      <span className="text-amber-700 dark:text-amber-300">לא שויך לשום שדה</span>
                    ) : (
                      usedBy.map((field) => (
                        <button key={field.id} type="button" onClick={() => onSelectField(field.id)} className="ml-2 text-teal-700 hover:underline dark:text-teal-300">
                          {meta.fieldLabel(field.field_name)}
                        </button>
                      ))
                    )}
                  </span>
                </li>
              )
            })}
          </ul>
        )}
      </div>

      <div>
        <p className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-gray-600 dark:text-gray-300">
          <ScanText size={14} aria-hidden="true" /> {meta.source_labels.ocr}
        </p>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          {!ocrResult ? 'לא הורץ' : ocrResult.status === 'ok' ? `${ocrResult.items.length} פריטים` : `${meta.source_status_labels[ocrResult.status]}${ocrResult.reason ? ` – ${ocrResult.reason}` : ''}`}
        </p>
      </div>
    </div>
  )
}
