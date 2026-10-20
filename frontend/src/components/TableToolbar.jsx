import { useState } from 'react'
import { ChevronDown, Download, Plus, Search, X } from 'lucide-react'
import { useMeta } from '../meta/MetaContext'
import { useClickOutside } from '../hooks/useClickOutside'

const ALL_STATUSES = ''

export default function TableToolbar({ filters, onChangeFilters, onAddFile, onExport, exporting }) {
  const meta = useMeta()
  const [exportOpen, setExportOpen] = useState(false)
  const exportRef = useClickOutside(() => setExportOpen(false), exportOpen)
  const activeColumnFilters = Object.entries(filters.columnFilters).filter(([, value]) => value?.trim())

  return (
    <div className="flex-none space-y-2 border-b border-slate-100 px-3 py-2.5 dark:border-slate-800">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={onAddFile}
          className="inline-flex items-center gap-2 rounded-lg bg-teal-600 px-3 py-2 text-sm font-medium text-white hover:bg-teal-700 dark:bg-teal-500 dark:hover:bg-teal-400"
        >
          <Plus size={16} /> הוסף קובץ
        </button>

        <div ref={exportRef} className="relative">
          <button
            type="button"
            onClick={() => setExportOpen((open) => !open)}
            disabled={exporting}
            aria-expanded={exportOpen}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-slate-100 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-200 disabled:cursor-wait disabled:opacity-60 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
          >
            {exporting
              ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-500 border-t-transparent" />
              : <Download size={16} />}
            <span className="hidden sm:inline">{exporting ? 'מייצא...' : 'ייצא לאקסל'}</span>
            <ChevronDown size={14} />
          </button>
          {exportOpen && (
            <div className="absolute right-0 z-30 mt-2 w-56 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900">
              {Object.entries(meta.export_modes).map(([mode, label]) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => { setExportOpen(false); onExport(mode) }}
                  className="block w-full px-3 py-2 text-right text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
                >
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="flex w-full flex-1 items-center gap-2 sm:w-auto sm:justify-end">
          <label className="relative min-w-0 flex-1 sm:max-w-xs">
            <span className="sr-only">חיפוש</span>
            <Search className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-gray-400" size={15} />
            <input
              value={filters.query}
              onChange={(event) => onChangeFilters({ query: event.target.value })}
              placeholder="חיפוש בשם קובץ או בערכים"
              className="w-full rounded-lg border border-slate-200 bg-white py-2 pl-2 pr-9 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-teal-400 dark:border-slate-700 dark:bg-slate-950 dark:text-gray-200"
            />
          </label>
          <select
            value={filters.status}
            onChange={(event) => onChangeFilters({ status: event.target.value })}
            aria-label="סינון לפי סטטוס"
            className="rounded-lg border border-slate-200 bg-white px-2 py-2 text-sm text-gray-700 dark:border-slate-700 dark:bg-slate-950 dark:text-gray-200"
          >
            <option value={ALL_STATUSES}>כל הסטטוסים</option>
            {Object.entries(meta.form_statuses).map(([status, label]) => (
              <option key={status} value={status}>{label}</option>
            ))}
          </select>
        </div>
      </div>

      {activeColumnFilters.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          {activeColumnFilters.map(([key, value]) => (
            <span key={key} className="inline-flex items-center gap-1 rounded-full bg-navy-50 px-2.5 py-1 text-xs text-navy-700 dark:bg-slate-800 dark:text-slate-200">
              {meta.fieldLabel(key)}: {value}
              <button
                type="button"
                aria-label={`הסר סינון ${meta.fieldLabel(key)}`}
                onClick={() => onChangeFilters({ columnFilters: { ...filters.columnFilters, [key]: '' } })}
                className="rounded-full p-0.5 hover:bg-navy-100 dark:hover:bg-slate-700"
              >
                <X size={11} />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
