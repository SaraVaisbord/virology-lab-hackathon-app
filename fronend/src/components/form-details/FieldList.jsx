import StatusBadge from '../ui/StatusBadge'
import { useMeta } from '../../meta/MetaContext'
import { EMPTY, fieldDisplayValue, groupFieldsByName } from '../../lib/format'

export default function FieldList({ fields, activeFieldId, onSelect }) {
  const meta = useMeta()
  const groups = groupFieldsByName(fields)
  const toReview = fields.filter(meta.needsReview).length

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">שדות שחולצו</p>
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${toReview ? 'bg-pink-100 text-pink-700 dark:bg-pink-950/60 dark:text-pink-200' : 'bg-teal-50 text-teal-700 dark:bg-teal-950/60 dark:text-teal-300'}`}>
          {toReview ? `${toReview} לאימות` : 'הכל מאומת'}
        </span>
      </div>

      {fields.length === 0 ? (
        <p className="text-sm text-gray-500 dark:text-gray-400">אין שדות עדיין.</p>
      ) : (
        <ul className="space-y-1.5">
          {meta.fields.filter(({ key }) => groups[key]).map(({ key, label }) =>
            groups[key].map((field, index) => {
              const active = field.id === activeFieldId
              return (
                <li key={field.id}>
                  <button
                    type="button"
                    onClick={() => onSelect(field.id)}
                    aria-current={active ? 'true' : undefined}
                    className={`flex w-full items-center justify-between gap-2 rounded-lg border px-3 py-2 text-right transition ${
                      active
                        ? 'border-teal-500 bg-teal-50 dark:border-teal-400 dark:bg-teal-950/30'
                        : 'border-slate-200 bg-white hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800'
                    }`}
                  >
                    <span className="min-w-0">
                      <span className="block text-xs text-gray-500 dark:text-gray-400">
                        {label}{groups[key].length > 1 ? ` ${index + 1}` : ''}
                      </span>
                      <span className="block truncate text-sm font-medium text-gray-800 dark:text-gray-100">{fieldDisplayValue(field) || EMPTY}</span>
                    </span>
                    <StatusBadge status={field.status} kind="field" />
                  </button>
                </li>
              )
            }),
          )}
        </ul>
      )}
    </div>
  )
}
