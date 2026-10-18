import { useMemo, useState } from 'react'
import { Download, Eye, FileText, Plus, Search, X, ChevronDown, ChevronUp } from 'lucide-react'
import StatusBadge from './ui/StatusBadge'

const FIELD_LABELS = {
  source_file: 'שם קובץ',
  page_number: 'עמוד',
  status: 'סטטוס',
  first_name: 'שם פרטי',
  last_name: 'שם משפחה',
  id_number: 'ת"ז',
  central_number: 'מספר מרכזי',
  received_date: 'תאריך קבלה',
  sender: 'גורם שולח',
  commitment_number: 'מספר התחייבות',
  uploaded_at: 'תאריך העלאה',
  actions: 'פעולות',
}

const EMPTY = '—'

function normalizeText(value) {
  return String(value ?? '').trim().toLowerCase()
}

function toDisplay(value) {
  if (value === null || value === undefined || value === '') return EMPTY
  return String(value)
}

function getFieldValue(form, fieldName) {
  if (!Array.isArray(form?.fields)) return EMPTY
  const match = form.fields.find((field) => field.field_name === fieldName)
  if (!match) return EMPTY
  if (match.value !== null && match.value !== undefined && match.value !== '') return match.value
  if (match.raw_value !== null && match.raw_value !== undefined && match.raw_value !== '') return match.raw_value
  return EMPTY
}

function getRowValue(form, key) {
  if (key === 'source_file') return form.source_file ?? ''
  if (key === 'page_number') return form.page_number ?? ''
  if (key === 'status') return form.status ?? ''
  if (key === 'received_date') return getFieldValue(form, 'received_date')
  if (key === 'uploaded_at') return form.uploaded_at ?? ''
  if (key === 'sender') return getFieldValue(form, 'sender')
  if (key === 'central_number') {
    return Array.isArray(form.central_number) ? form.central_number.map((item) => item.value ?? '').join(' ') : getFieldValue(form, 'central_number')
  }
  if (key === 'commitment_number') {
    return Array.isArray(form.commitment_number) ? form.commitment_number.map((item) => item.value ?? '').join(' ') : getFieldValue(form, 'commitment_number')
  }
  return form[key] ?? getFieldValue(form, key) ?? ''
}

function HeaderDropdown({ columnKey, value, onSortAsc, onSortDesc, onFilterChange, onClose }) {
  return (
    <div className="absolute left-0 top-full z-30 mt-2 w-52 rounded-xl border border-slate-200 bg-white p-2 shadow-lg dark:border-slate-700 dark:bg-slate-900" dir="rtl">
      <div className="mb-2 flex items-center justify-between gap-2 border-b border-slate-100 pb-2 dark:border-slate-700">
        <span className="text-[11px] font-semibold text-slate-600 dark:text-slate-300">{FIELD_LABELS[columnKey] || columnKey}</span>
        <button type="button" onClick={onClose} className="rounded p-1 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800" aria-label="סגור">
          <X size={12} />
        </button>
      </div>

      <div className="space-y-2">
        <button type="button" onClick={onSortAsc} className="block w-full rounded-lg px-2 py-1.5 text-right text-xs text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800">
          מיין סדר עולה
        </button>
        <button type="button" onClick={onSortDesc} className="block w-full rounded-lg px-2 py-1.5 text-right text-xs text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800">
          מיין סדר יורד
        </button>

        <div className="pt-1">
          <label className="mb-1 block text-[10px] font-medium text-slate-500 dark:text-slate-400">סינון...</label>
          <input
            autoFocus
            value={value ?? ''}
            onChange={(event) => onFilterChange(event.target.value)}
            placeholder="סינון..."
            className="w-full rounded-md border border-slate-200 bg-white px-2 py-1.5 text-xs text-gray-700 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-400 dark:border-slate-700 dark:bg-slate-950 dark:text-gray-200"
          />
        </div>
      </div>
    </div>
  )
}

export default function DataTable({
  forms = [],
  loading = false,
  error = '',
  onSelectForm,
  onAddFile,
  onExport,
  exportMenuOpen,
  onToggleExportMenu,
  exportLoading = false,
  hasUploadOpen = false,
  statusFilter = 'all',
  onChangeStatusFilter,
  query = '',
  onChangeQuery,
  columnFilters = {},
  onChangeColumnFilter,
}) {
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' })
  const [headerMenuKey, setHeaderMenuKey] = useState(null)

  const columns = [
    { key: 'source_file' },
    { key: 'page_number' },
    { key: 'status' },
    { key: 'first_name' },
    { key: 'last_name' },
    { key: 'id_number' },
    { key: 'central_number' },
    { key: 'received_date' },
    { key: 'sender' },
    { key: 'commitment_number' },
    { key: 'uploaded_at' },
    { key: 'actions' },
  ]

  const filteredForms = useMemo(() => {
    const rows = forms.filter((form) => {
      const matchesStatus = statusFilter === 'all' || form.status === statusFilter
      const haystack = [
        getRowValue(form, 'source_file'),
        getRowValue(form, 'page_number'),
        getRowValue(form, 'status'),
        getRowValue(form, 'first_name'),
        getRowValue(form, 'last_name'),
        getRowValue(form, 'id_number'),
        getRowValue(form, 'sender'),
        getRowValue(form, 'central_number'),
        getRowValue(form, 'commitment_number'),
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()

      const searchMatches = !query || haystack.includes(normalizeText(query))

      const columnFilterMatches = Object.entries(columnFilters).every(([key, filterValue]) => {
        if (!filterValue || !String(filterValue).trim()) return true
        const value = String(getRowValue(form, key) ?? '').toLowerCase()
        return value.includes(String(filterValue).trim().toLowerCase())
      })

      return matchesStatus && searchMatches && columnFilterMatches
    })

    if (!sortConfig.key) return rows

    return [...rows].sort((a, b) => {
      let left = getRowValue(a, sortConfig.key)
      let right = getRowValue(b, sortConfig.key)

      if (left === null || left === undefined || left === '') left = ''
      if (right === null || right === undefined || right === '') right = ''

      const leftValue = typeof left === 'string' ? left.toLowerCase() : left
      const rightValue = typeof right === 'string' ? right.toLowerCase() : right

      if (leftValue < rightValue) return sortConfig.direction === 'asc' ? -1 : 1
      if (leftValue > rightValue) return sortConfig.direction === 'asc' ? 1 : -1
      return 0
    })
  }, [forms, query, statusFilter, columnFilters, sortConfig])

  const handleSort = (key, direction) => {
    setSortConfig({ key, direction })
    setHeaderMenuKey(null)
  }

  const renderCell = (form, key) => {
    if (key === 'source_file') {
      return (
        <button
          type="button"
          onClick={() => onSelectForm?.(form)}
          className="block w-full truncate text-right text-sm font-medium text-gray-700 hover:text-teal-700 dark:text-gray-200 dark:hover:text-teal-300"
          title={form.source_file || EMPTY}
        >
          {form.source_file || EMPTY}
        </button>
      )
    }

    if (key === 'page_number') {
      return <span className="block whitespace-nowrap text-right text-sm text-gray-700 dark:text-gray-200">{form.page_number ?? EMPTY}</span>
    }

    if (key === 'status') {
      return <div className="flex justify-start"><StatusBadge status={form.status || 'pending'} /></div>
    }

    if (key === 'received_date' || key === 'uploaded_at') {
      const value = key === 'received_date' ? getRowValue(form, 'received_date') : form.uploaded_at
      if (!value) return <span className="block whitespace-nowrap text-right text-sm text-gray-500 dark:text-gray-400">{EMPTY}</span>
      const date = new Date(value)
      const display = Number.isNaN(date.getTime()) ? String(value) : date.toLocaleDateString('he-IL')
      return <span className="block whitespace-nowrap text-right text-sm text-gray-700 dark:text-gray-200">{display}</span>
    }

    if (key === 'sender') {
      const value = getRowValue(form, 'sender')
      return <span className="block whitespace-nowrap text-right text-sm text-gray-700 dark:text-gray-200">{value || EMPTY}</span>
    }

    if (key === 'actions') {
      return (
        <div className="flex justify-center">
          <button
            type="button"
            onClick={() => onSelectForm?.(form)}
            className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600 transition hover:bg-slate-100 hover:text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white"
            aria-label={`צפה בטופס ${form.source_file || form.id}`}
            title="צפייה"
          >
            <Eye size={14} />
          </button>
        </div>
      )
    }

    const value = form[key] ?? getFieldValue(form, key)
    const fieldEntry = Array.isArray(form?.fields) ? form.fields.find((item) => item.field_name === key) : null
    const isUnverified = fieldEntry && ['unverified', 'uncertain', 'not_found'].includes(fieldEntry.status)

    if (isUnverified) {
      return (
        <button
          type="button"
          onClick={() => onSelectForm?.(form)}
          className="block w-full cursor-pointer rounded-md border border-pink-300 bg-pink-50/80 px-2 py-1 text-right text-sm text-gray-700 transition hover:border-pink-400 hover:bg-pink-50 focus:outline-none focus:ring-2 focus:ring-pink-300 dark:border-pink-700 dark:bg-pink-950/30 dark:text-gray-200 dark:hover:bg-pink-900/40"
          title="פתח את תצוגת האימות"
        >
          {toDisplay(value)}
        </button>
      )
    }

    return <span className="block whitespace-nowrap text-right text-sm text-gray-700 dark:text-gray-200">{toDisplay(value)}</span>
  }

  return (
    <div className="card flex h-full min-h-0 flex-col overflow-hidden rounded-xl" dir="rtl">
      {error && (
        <div className="border-b border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">
          {error}
        </div>
      )}

      <div className="flex-none border-b border-slate-100 px-3 py-2 dark:border-slate-800">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onAddFile}
            className="inline-flex items-center gap-2 rounded-lg bg-teal-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-teal-700 dark:bg-teal-500 dark:hover:bg-teal-400"
          >
            <Plus size={15} />
            הוסף קובץ
          </button>

          <div className="relative">
            <button
              type="button"
              onClick={onToggleExportMenu}
              disabled={exportLoading}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
            >
              {exportLoading ? (
                <>
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-500 border-t-transparent" />
                  מייצא...
                </>
              ) : (
                <>
                  <Download size={15} />
                  ייצא לאקסל
                </>
              )}
              <ChevronDown size={14} />
            </button>

            {exportMenuOpen && (
              <div className="absolute left-0 z-30 mt-2 w-48 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900">
                <button type="button" onClick={() => onExport('all')} className="block w-full px-3 py-2 text-right text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800">ייצא הכל</button>
                <button type="button" onClick={() => onExport('filtered')} className="block w-full px-3 py-2 text-right text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800">ייצא מסוננים</button>
                <button type="button" onClick={() => onExport('new')} className="block w-full px-3 py-2 text-right text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800">ייצא חדשים בלבד</button>
              </div>
            )}
          </div>

          <div className="ml-auto flex items-center gap-2">
            <div className="relative w-[240px]">
              <Search className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400" size={15} />
              <input
                value={query}
                onChange={(event) => onChangeQuery?.(event.target.value)}
                placeholder="חיפוש"
                className="w-full rounded-lg border border-slate-200 bg-white py-1.5 pr-9 pl-2 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-teal-400"
              />
            </div>

            <select
              value={statusFilter}
              onChange={(event) => onChangeStatusFilter?.(event.target.value)}
              className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm text-gray-700"
            >
              <option value="all">הכל</option>
              <option value="uploaded">הועלה</option>
              <option value="processing">מעבד</option>
              <option value="extracted">נשלף</option>
            </select>
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden">
        <div className="h-full w-full overflow-x-auto">
          <div className="min-w-[1200px] w-full">
            <div className="grid grid-cols-[2.5fr_1fr_1fr_1.5fr_1.5fr_1.5fr_1.5fr_1.5fr_1.5fr_1.5fr_1.5fr_60px]">
              {columns.map((column) => {
                const isActionColumn = column.key === 'actions'
                return (
                  <div
                    key={`header-${column.key}`}
                    className={`relative border-b border-slate-200 bg-slate-50 p-3 text-right text-[11px] font-bold text-navy-700 dark:border-slate-700 dark:bg-slate-800 dark:text-gray-200 ${isActionColumn ? 'flex items-center justify-center' : 'cursor-pointer select-none'}`}
                  >
                    {isActionColumn ? (
                      <span>{FIELD_LABELS[column.key]}</span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => setHeaderMenuKey((current) => (current === column.key ? null : column.key))}
                        className="flex w-full items-center justify-start gap-2 text-right"
                      >
                        <span className="inline-flex items-center gap-1">
                          {FIELD_LABELS[column.key]}
                          {sortConfig.key === column.key && (
                            sortConfig.direction === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />
                          )}
                        </span>
                      </button>
                    )}

                    {!isActionColumn && headerMenuKey === column.key && (
                      <HeaderDropdown
                        columnKey={column.key}
                        value={columnFilters[column.key] ?? ''}
                        onSortAsc={() => handleSort(column.key, 'asc')}
                        onSortDesc={() => handleSort(column.key, 'desc')}
                        onFilterChange={(value) => onChangeColumnFilter?.(column.key, value)}
                        onClose={() => setHeaderMenuKey(null)}
                      />
                    )}
                  </div>
                )
              })}

              {loading ? (
                <div className="col-span-full p-4 text-center text-sm text-gray-500 dark:text-gray-400">טוען...</div>
              ) : filteredForms.length === 0 ? (
                <div className="col-span-full p-8 text-center text-sm text-gray-500 dark:text-gray-400">
                  <div className="flex flex-col items-center gap-3">
                    <FileText size={22} className="text-gray-400" />
                    <span>אין טפסים להצגה</span>
                  </div>
                </div>
              ) : (
                filteredForms.map((form) => (
                  <div key={form.id} className="contents">
                    {columns.map((column) => (
                      <div
                        key={`${form.id}-${column.key}`}
                        className={`border-l border-slate-100 p-3 text-right align-top last:border-l-0 dark:border-slate-800 ${column.key === 'actions' ? 'flex items-center justify-center' : ''}`}
                      >
                        {renderCell(form, column.key)}
                      </div>
                    ))}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}