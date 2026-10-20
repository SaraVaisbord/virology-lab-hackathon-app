import { useMeta } from '../../meta/MetaContext'
import { fieldsUsing } from '../../lib/pageNumbers'
import PageNumberRow from './PageNumberRow'

/**
 * Every number the sources found on the page, in one list: unassigned numbers first (they need a decision),
 * each with "show on the document" and "assign to a field" — so nothing read from the page is a dead end.
 */
export default function PageSources({ sources, fields, numbers, focusKey, onShow, onAssign, saving }) {
  const meta = useMeta()
  if (!sources) return null
  const errors = Object.entries(sources.source_errors ?? {})
  const statusOf = (result) => (!result ? 'לא הורץ' : meta.source_status_labels[result.status] ?? result.status)
  const ocrLabels = [...new Set((sources.ocr_result?.labels ?? []).map((label) => meta.fieldLabel(label.field)))]

  const rows = numbers
    .map((item) => ({ item, usedBy: fieldsUsing(fields, item.key) }))
    .sort((a, b) => (a.usedBy.length > 0) - (b.usedBy.length > 0))
  const assignOptions = meta.fields.map(({ key, label }) => ({ key, label }))

  return (
    <div className="space-y-2 rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800">
      <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">מספרים שנמצאו בעמוד</p>
      <p className="text-[11px] text-gray-500 dark:text-gray-400">
        {meta.source_labels.barcode}: {statusOf(sources.barcode_result)} · {meta.source_labels.ocr}: {statusOf(sources.ocr_result)}
        {ocrLabels.length > 0 && ` (תוויות: ${ocrLabels.join(', ')})`} · {meta.source_labels.llm}: {sources.llm_result ? 'הורץ' : 'לא הופעל'}
      </p>

      {errors.length > 0 && (
        <ul className="space-y-1 text-xs text-red-700 dark:text-red-300">
          {errors.map(([source, message]) => <li key={source}>{meta.source_labels[source] ?? source}: {message}</li>)}
        </ul>
      )}

      {rows.length === 0 ? (
        <p className="text-xs text-gray-500 dark:text-gray-400">לא נמצאו מספרים בעמוד</p>
      ) : (
        <ul className="space-y-1.5">
          {rows.map(({ item, usedBy }) => (
            <PageNumberRow
              key={item.key}
              item={item}
              usedBy={usedBy}
              focused={item.key === focusKey}
              onShow={onShow}
              assignOptions={assignOptions}
              onAssign={onAssign}
              disabled={saving}
            />
          ))}
        </ul>
      )}
    </div>
  )
}
