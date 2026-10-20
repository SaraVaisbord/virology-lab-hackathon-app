import { Crosshair } from 'lucide-react'
import { useMeta } from '../../meta/MetaContext'

const SOURCE_TAG = {
  barcode: 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-200',
  ocr: 'bg-sky-50 text-sky-800 dark:bg-sky-950/50 dark:text-sky-200',
  llm: 'bg-indigo-50 text-indigo-800 dark:bg-indigo-950/50 dark:text-indigo-200',
}

/**
 * One number found on the page: its value, which sources read it, and actions — show it on the document,
 * and (optionally) put it into a field (`assignOptions` → select) or use it in the editor (`onUse`).
 */
export default function PageNumberRow({ item, focused, usedBy = [], onShow, assignOptions, onAssign, onUse, disabled }) {
  const meta = useMeta()
  return (
    <li className={`rounded-lg border px-2.5 py-2 text-xs transition ${focused ? 'border-teal-500 bg-teal-50 dark:border-teal-400 dark:bg-teal-950/30' : 'border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900'}`}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span dir="ltr" className="font-mono text-sm font-semibold text-gray-800 dark:text-gray-100">{item.value}</span>
        {item.sources.map((source) => (
          <span key={source} className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${SOURCE_TAG[source]}`}>{meta.source_labels[source]}</span>
        ))}
        {item.notes.length > 0 && <span className="truncate text-[11px] text-gray-400" dir="auto">{item.notes.join(' · ')}</span>}
        <span className="ms-auto flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => onShow(item)}
            disabled={!item.box}
            title={item.box ? `הצג במסמך (מיקום לפי ${meta.source_labels[item.boxSource]})` : 'אין מיקום לערך זה'}
            aria-label={`הצג את ${item.value} במסמך`}
            className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-1.5 py-1 text-[11px] text-gray-600 hover:bg-slate-100 disabled:opacity-40 dark:border-slate-600 dark:text-gray-300 dark:hover:bg-slate-800"
          >
            <Crosshair size={12} /> הצג
          </button>
          {onUse && (
            <button type="button" onClick={() => onUse(item.value)} disabled={disabled} className="rounded-md px-1.5 py-1 text-[11px] font-medium text-teal-700 hover:bg-teal-50 dark:text-teal-300 dark:hover:bg-teal-950/40">
              השתמש בערך
            </button>
          )}
          {assignOptions && (
            <select
              value=""
              disabled={disabled}
              onChange={(event) => event.target.value && onAssign(event.target.value, item)}
              aria-label={`שייך את ${item.value} לשדה`}
              className="rounded-md border border-slate-200 bg-white px-1 py-1 text-[11px] text-gray-700 dark:border-slate-600 dark:bg-slate-900 dark:text-gray-200"
            >
              <option value="">שייך לשדה…</option>
              {assignOptions.map(({ key, label }) => <option key={key} value={key}>{label}</option>)}
            </select>
          )}
        </span>
      </div>
      <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
        {usedBy.length ? `בשימוש ב: ${[...new Set(usedBy.map((field) => meta.fieldLabel(field.field_name)))].join(', ')}` : 'לא שויך לאף שדה'}
      </p>
    </li>
  )
}
