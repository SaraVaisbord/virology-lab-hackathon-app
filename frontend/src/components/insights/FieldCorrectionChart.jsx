import { useState } from 'react'
import { BarChart3, Table2 } from 'lucide-react'
import { useMeta } from '../../meta/MetaContext'

const percentOf = (part, whole) => (whole ? Math.round((part / whole) * 100) : 0)

/**
 * Answers "which field should we look at first?": per field, the share of the values the lab worker reviewed that
 * she had to correct. One series, so one colour and no legend; every value is written at the bar's end (the hover
 * text only adds the counts), and the table view shows the same numbers.
 */
export default function FieldCorrectionChart({ fields }) {
  const meta = useMeta()
  const [asTable, setAsTable] = useState(false)
  const rows = fields.map((row) => ({ ...row, label: meta.fieldLabel(row.field_name), percent: percentOf(row.corrected, row.reviewed) }))

  return (
    <section className="card rounded-xl p-4" aria-labelledby="field-corrections-title">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div>
          <h2 id="field-corrections-title" className="text-sm font-bold text-navy-800 dark:text-gray-100">אילו שדות מתוקנים הכי הרבה?</h2>
          <p className="text-xs text-gray-500 dark:text-gray-400">מתוך הערכים שהלבורנטית בדקה בכל שדה – כמה מהם היה צריך לתקן</p>
        </div>
        <button type="button" className="btn-ghost inline-flex shrink-0 items-center gap-1 text-xs" aria-pressed={asTable} onClick={() => setAsTable((value) => !value)}>
          {asTable ? <BarChart3 size={14} aria-hidden="true" /> : <Table2 size={14} aria-hidden="true" />}
          {asTable ? 'תרשים' : 'טבלה'}
        </button>
      </div>

      {asTable ? (
        <table className="w-full text-sm">
          <thead className="text-xs text-gray-500 dark:text-gray-400">
            <tr className="border-b border-slate-200 dark:border-slate-700">
              <th className="py-1.5 text-start font-medium">שדה</th>
              <th className="py-1.5 text-start font-medium">נבדקו</th>
              <th className="py-1.5 text-start font-medium">תוקנו</th>
              <th className="py-1.5 text-start font-medium">שיעור</th>
            </tr>
          </thead>
          <tbody className="text-gray-700 dark:text-gray-200">
            {rows.map((row) => (
              <tr key={row.field_name} className="border-b border-slate-100 last:border-0 dark:border-slate-800">
                <td className="py-1.5">{row.label}</td>
                <td className="py-1.5 tabular-nums">{row.reviewed}</td>
                <td className="py-1.5 tabular-nums">{row.corrected}</td>
                <td className="py-1.5 tabular-nums">{row.percent}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <ul className="space-y-0.5">
          {rows.map((row) => (
            <li
              key={row.field_name}
              tabIndex={0}
              title={`${row.label}: ${row.corrected} תוקנו מתוך ${row.reviewed} שנבדקו`}
              className="grid grid-cols-[7rem_1fr] items-center gap-3 rounded-md px-1 py-1.5 hover:bg-slate-50 focus-visible:bg-slate-50 dark:hover:bg-slate-800/60 dark:focus-visible:bg-slate-800/60"
            >
              <span className="truncate text-sm text-gray-700 dark:text-gray-200">{row.label}</span>
              <span className="flex min-w-0 items-center gap-2">
                {/* The bar grows from the start edge (right, in RTL); its rounded end is the data end. */}
                <span className="h-3 rounded-e bg-teal-600 dark:bg-teal-400" style={{ width: `${row.percent}%` }} aria-hidden="true" />
                <span className="shrink-0 text-xs tabular-nums text-gray-600 dark:text-gray-300">
                  {row.percent}% <span className="text-gray-400 dark:text-gray-500">({row.corrected}/{row.reviewed})</span>
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
