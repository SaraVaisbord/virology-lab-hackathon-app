import { Copy, X } from 'lucide-react'
import DocumentViewer from './DocumentViewer'
import { api } from '../../api'
import { useMeta } from '../../meta/MetaContext'

/** Commitment numbers of this form that other forms have too, each with a "compare" action. */
export function DuplicateBanner({ duplicates, onCompare }) {
  const meta = useMeta()
  if (!duplicates?.length) return null
  return (
    <div className="rounded-xl border border-orange-300 bg-orange-50 px-3 py-2 text-sm text-orange-900 dark:border-orange-900 dark:bg-orange-950/30 dark:text-orange-200">
      <p className="mb-1 flex items-center gap-1.5 font-semibold">
        <Copy size={15} aria-hidden="true" /> {meta.fieldLabel(meta.row_key_field)} מופיע גם בטופס אחר
      </p>
      <ul className="space-y-1">
        {duplicates.map((dup) => (
          <li key={`${dup.field_id}-${dup.other_field_id}`} className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span dir="ltr" className="font-mono font-semibold">{dup.value}</span>
            <span>גם ב־<span dir="auto">{dup.other_source_file}</span> עמ' {dup.other_page_number} ({meta.form_statuses[dup.other_status] ?? dup.other_status})</span>
            <button type="button" onClick={() => onCompare(dup)} className="rounded-md border border-orange-300 bg-white px-2 py-0.5 text-xs font-medium text-orange-800 hover:bg-orange-100 dark:border-orange-800 dark:bg-slate-900 dark:text-orange-200 dark:hover:bg-orange-950">
              השווה בין הטפסים
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** The two pages side by side, each with the repeated commitment number highlighted — so the lab worker sees whether
 * it is the same form uploaded twice or a misread number. Nothing is changed automatically. */
export default function DuplicateCompare({ form, duplicate, onClose }) {
  const meta = useMeta()
  const ownField = (form.fields ?? []).find((field) => field.id === duplicate.field_id) ?? null
  const otherField = {
    id: duplicate.other_field_id,
    field_name: meta.row_key_field,
    x: duplicate.x, y: duplicate.y, width: duplicate.width, height: duplicate.height, box_source: duplicate.box_source,
  }
  const pages = [
    { key: 'this', title: `הטופס הזה – ${form.source_file} עמ' ${form.page_number}`, formId: form.id, field: ownField, value: duplicate.value },
    { key: 'other', title: `${duplicate.other_source_file} עמ' ${duplicate.other_page_number}`, formId: duplicate.other_form_id, field: otherField, value: duplicate.other_value },
  ]

  return (
    <section className="space-y-2 rounded-xl border border-orange-300 bg-orange-50/60 p-3 dark:border-orange-900 dark:bg-orange-950/20" aria-label="השוואת טפסים">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-semibold text-orange-900 dark:text-orange-200">
          השוואה: {meta.fieldLabel(meta.row_key_field)} <span dir="ltr" className="font-mono">{duplicate.value}</span> בשני טפסים
        </p>
        <button type="button" onClick={onClose} aria-label="סגור השוואה" className="rounded-md p-1 text-orange-800 hover:bg-orange-100 dark:text-orange-200 dark:hover:bg-orange-950">
          <X size={16} />
        </button>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {pages.map((page) => (
          <div key={page.key} className="space-y-1">
            <p className="text-xs font-medium text-gray-700 dark:text-gray-200">
              <span dir="auto">{page.title}</span> · נקרא: <span dir="ltr" className="font-mono">{page.value}</span>
            </p>
            <div className="h-[55vh]">
              <DocumentViewer imageUrl={api.getFormImageUrl(page.formId)} field={page.field} alt={page.title} />
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
