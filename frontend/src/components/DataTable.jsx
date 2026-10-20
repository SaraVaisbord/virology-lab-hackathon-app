import { useEffect, useRef, useState } from 'react'
import { ChevronDown, ChevronUp, Eye, FileText, Loader2, Pencil, RotateCcw, X } from 'lucide-react'
import StatusBadge from './ui/StatusBadge'
import { useMeta } from '../meta/MetaContext'
import { useClickOutside } from '../hooks/useClickOutside'
import { EMPTY, fieldDisplayValue, formatDateTime, groupFieldsByName } from '../lib/format'

const LEADING_COLUMNS = ['source_file', 'page_number', 'status']
const TRAILING_COLUMNS = ['uploaded_at']

function ColumnMenu({ label, filterValue, onSort, onFilter, onClose }) {
  const ref = useClickOutside(onClose)
  return (
    <div ref={ref} className="absolute right-0 top-full z-30 mt-1 w-52 rounded-xl border border-slate-200 bg-white p-2 text-right shadow-lg dark:border-slate-700 dark:bg-slate-900">
      <div className="mb-2 flex items-center justify-between border-b border-slate-100 pb-2 dark:border-slate-700">
        <span className="text-xs font-semibold text-slate-600 dark:text-slate-300">{label}</span>
        <button type="button" onClick={onClose} className="rounded p-1 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800" aria-label="סגור">
          <X size={12} />
        </button>
      </div>
      {[['asc', 'מיין סדר עולה'], ['desc', 'מיין סדר יורד']].map(([direction, text]) => (
        <button
          key={direction}
          type="button"
          onClick={() => onSort(direction)}
          className="block w-full rounded-lg px-2 py-1.5 text-right text-xs font-normal text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          {text}
        </button>
      ))}
      <input
        autoFocus
        value={filterValue}
        onChange={(event) => onFilter(event.target.value)}
        placeholder="סינון..."
        className="mt-2 w-full rounded-md border border-slate-200 bg-white px-2 py-1.5 text-xs font-normal text-gray-700 focus:outline-none focus:ring-2 focus:ring-teal-400 dark:border-slate-700 dark:bg-slate-950 dark:text-gray-200"
      />
    </div>
  )
}

function FieldValues({ form, fieldKey, rows, onOpenField }) {
  const meta = useMeta()
  if (meta.isPendingForm(form.status)) {
    return <span className="block h-4 w-20 animate-shimmer rounded bg-slate-200 dark:bg-slate-700" aria-label="בעיבוד" />
  }
  const values = (rows || []).filter((row) => fieldDisplayValue(row) || meta.needsReview(row))
  if (values.length === 0) return <span className="text-gray-400">{EMPTY}</span>

  return (
    <div className="flex flex-wrap gap-1">
      {values.map((row) => {
        const text = fieldDisplayValue(row) || meta.field_statuses[row.status]
        const review = meta.needsReview(row)
        return (
          <button
            key={row.id}
            type="button"
            onClick={() => onOpenField(form, row.id)}
            title={review ? row.reason || meta.field_statuses[row.status] : meta.field_statuses[row.status]}
            className={
              review
                ? 'uncertain-cell max-w-[12rem] truncate text-right'
                : `max-w-[12rem] truncate rounded-full px-2 py-0.5 text-right text-sm text-gray-700 hover:bg-slate-100 dark:text-gray-200 dark:hover:bg-slate-800 ${meta.isMultiValue(fieldKey) ? 'border border-slate-200 dark:border-slate-700' : ''}`
            }
          >
            {text}
          </button>
        )
      })}
    </div>
  )
}

export default function DataTable({ forms, total, loading, loadingMore, hasMore, onLoadMore, error, filters, onChangeFilters, onOpenForm, onEditForm, onRetry }) {
  const meta = useMeta()
  const [menuColumn, setMenuColumn] = useState(null)
  const sentinelRef = useRef(null)

  const columns = [...LEADING_COLUMNS, ...meta.fields.map((field) => field.key), ...TRAILING_COLUMNS]

  // Infinite scroll: load the next page when the bottom of the list becomes visible.
  useEffect(() => {
    const node = sentinelRef.current
    if (!node || !hasMore) return undefined
    const observer = new IntersectionObserver(([entry]) => { if (entry.isIntersecting) onLoadMore() }, { rootMargin: '200px' })
    observer.observe(node)
    return () => observer.disconnect()
  }, [hasMore, onLoadMore])

  const renderCell = (form, key, groups) => {
    switch (key) {
      case 'source_file':
        return (
          <button type="button" dir="auto" onClick={() => onOpenForm(form)} className="block max-w-[14rem] truncate text-right font-medium text-gray-800 hover:text-teal-700 dark:text-gray-100 dark:hover:text-teal-300" title={form.source_file}>
            {form.source_file}
          </button>
        )
      case 'page_number':
        return form.page_number
      case 'status':
        return (
          <div className="flex flex-col items-start gap-1">
            <StatusBadge status={form.status} />
            {form.status === 'failed' && form.error && (
              <span className="max-w-[14rem] text-[11px] leading-4 text-red-600 dark:text-red-400">{form.error}</span>
            )}
          </div>
        )
      case 'uploaded_at':
        return <span className="whitespace-nowrap text-xs text-gray-500 dark:text-gray-400">{formatDateTime(form.uploaded_at)}</span>
      default:
        return <FieldValues form={form} fieldKey={key} rows={groups[key]} onOpenField={onOpenForm} />
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {error && (
        <div className="border-b border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">{error}</div>
      )}

      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full min-w-[1100px] border-separate border-spacing-0 text-sm">
          <thead className="sticky top-0 z-20">
            <tr>
              {columns.map((key, index) => {
                const label = meta.fieldLabel(key)
                const sorted = filters.sortBy === key
                const filtered = Boolean(filters.columnFilters[key]?.trim())
                return (
                  <th
                    key={key}
                    scope="col"
                    className={`relative whitespace-nowrap border-b border-slate-200 bg-slate-50 px-3 py-2.5 text-right text-xs font-bold text-navy-700 dark:border-slate-700 dark:bg-slate-800 dark:text-gray-200 ${index === 0 ? 'sticky right-0 z-10' : ''}`}
                  >
                    <button type="button" onClick={() => setMenuColumn(menuColumn === key ? null : key)} className="inline-flex items-center gap-1 hover:text-teal-700 dark:hover:text-teal-300" aria-haspopup="menu">
                      {label}
                      {sorted && (filters.sortDir === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
                      {filtered && <span className="h-1.5 w-1.5 rounded-full bg-teal-500" aria-label="מסונן" />}
                    </button>
                    {menuColumn === key && (
                      <ColumnMenu
                        label={label}
                        filterValue={filters.columnFilters[key] ?? ''}
                        onSort={(direction) => { onChangeFilters({ sortBy: key, sortDir: direction }); setMenuColumn(null) }}
                        onFilter={(value) => onChangeFilters({ columnFilters: { ...filters.columnFilters, [key]: value } })}
                        onClose={() => setMenuColumn(null)}
                      />
                    )}
                  </th>
                )
              })}
              <th scope="col" className="sticky left-0 z-10 border-b border-slate-200 bg-slate-50 px-3 py-2.5 text-center text-xs font-bold text-navy-700 dark:border-slate-700 dark:bg-slate-800 dark:text-gray-200">
                פעולות
              </th>
            </tr>
          </thead>

          <tbody>
            {loading ? (
              <tr><td colSpan={columns.length + 1} className="p-8 text-center text-gray-500"><Loader2 className="mx-auto animate-spin" size={20} /></td></tr>
            ) : forms.length === 0 ? (
              <tr>
                <td colSpan={columns.length + 1} className="p-10 text-center text-gray-500 dark:text-gray-400">
                  <FileText size={24} className="mx-auto mb-2 text-gray-400" />
                  אין טפסים להצגה
                </td>
              </tr>
            ) : (
              forms.map((form) => {
                const groups = groupFieldsByName(form.fields)
                return (
                  <tr key={form.id} className="group">
                    {columns.map((key, index) => (
                      <td
                        key={key}
                        className={`border-b border-slate-100 px-3 py-2.5 align-top text-gray-700 group-hover:bg-slate-50 dark:border-slate-800 dark:text-gray-200 dark:group-hover:bg-slate-800/60 ${index === 0 ? 'sticky right-0 z-[5] bg-white dark:bg-slate-900' : ''}`}
                      >
                        {renderCell(form, key, groups)}
                      </td>
                    ))}
                    <td className="sticky left-0 z-[5] border-b border-slate-100 bg-white px-3 py-2.5 text-center align-top shadow-[4px_0_6px_-4px_rgba(15,23,42,0.12)] group-hover:bg-slate-50 dark:bg-slate-900 dark:border-slate-800 dark:group-hover:bg-slate-800/60">
                      <div className="flex justify-center gap-1">
                        <button type="button" onClick={() => onOpenForm(form)} className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-slate-200 text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800" aria-label={`צפה בטופס ${form.source_file}`} title="צפייה ואימות">
                          <Eye size={15} />
                        </button>
                        <button type="button" onClick={() => onEditForm(form)} className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-slate-200 text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800" aria-label={`ערוך את שדות ${form.source_file}`} title="עריכת שדות">
                          <Pencil size={15} />
                        </button>
                        {form.status === 'failed' && (
                          <button type="button" onClick={() => onRetry(form)} className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-red-200 text-red-600 hover:bg-red-50 dark:border-red-900 dark:text-red-300 dark:hover:bg-red-950/40" aria-label={`נסה שוב לעבד את ${form.source_file}`} title="נסה שוב">
                            <RotateCcw size={15} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>

        {!loading && forms.length > 0 && (
          <div ref={sentinelRef} className="flex items-center justify-center gap-3 px-4 py-3 text-xs text-gray-500 dark:text-gray-400">
            <span>מוצגים {forms.length} מתוך {total}</span>
            {hasMore && (
              <button type="button" onClick={onLoadMore} disabled={loadingMore} className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-1.5 text-gray-600 hover:bg-slate-50 disabled:opacity-60 dark:border-slate-700 dark:text-gray-300 dark:hover:bg-slate-800">
                {loadingMore && <Loader2 size={12} className="animate-spin" />} טען עוד
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
