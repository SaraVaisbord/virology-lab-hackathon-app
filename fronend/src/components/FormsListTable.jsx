import { useMemo, useState } from 'react'
import { Eye, FileText, RefreshCw, Search, X } from 'lucide-react'
import StatusBadge from './ui/StatusBadge'
import { api } from '../api'

const formatDate = (value) => {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('he-IL', { dateStyle: 'short', timeStyle: 'short' }).format(date)
}

export default function FormsListTable({ forms, loading, error, onSelectForm, onRefresh }) {
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [searchOpen, setSearchOpen] = useState(false)

  const filteredForms = useMemo(() => {
    return forms.filter((form) => {
      const matchesStatus = statusFilter === 'all' || form.status === statusFilter
      const text = `${form.source_file || ''} ${form.id || ''} ${form.page_number || ''}`.toLowerCase()
      const matchesQuery = !query || text.includes(query.toLowerCase())
      return matchesStatus && matchesQuery
    })
  }, [forms, query, statusFilter])

  const clearFilters = () => {
    setQuery('')
    setStatusFilter('all')
    setSearchOpen(false)
  }

  return (
    <div className="card flex-1 min-h-0 flex flex-col overflow-hidden rounded-xl" dir="rtl">
      {error && (
        <div className="border-b border-red-200 bg-red-50 px-5 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">
          {error}
        </div>
      )}

      <div className="flex-none flex items-center gap-3 px-4 py-2 border-b border-slate-100 dark:border-slate-800">
        {searchOpen ? (
          <div className="relative flex-1 max-w-md">
            <Search className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400" size={16} />
            <input
              autoFocus
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="חיפוש לפי שם או מזהה"
              className="w-full pr-9 pl-9 py-1.5 text-sm rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-teal-400"
            />
            <button type="button" onClick={() => setQuery('')} className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
              <X size={16} />
            </button>
          </div>
        ) : (
          <button type="button" onClick={() => setSearchOpen(true)} className="p-2 rounded-lg text-gray-500 hover:bg-slate-100 dark:hover:bg-slate-800">
            <Search size={18} />
          </button>
        )}

        <select
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value)}
          className="border border-slate-200 rounded-lg px-3 py-1.5 text-sm bg-white"
        >
          <option value="all">הכל</option>
          <option value="uploaded">הועלה</option>
          <option value="processing">מעבד</option>
          <option value="extracted">נשלף</option>
        </select>

        <button type="button" onClick={onRefresh} className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-gray-600 hover:bg-slate-50 dark:border-slate-700 dark:text-gray-300">
          <RefreshCw size={14} /> רענון
        </button>
      </div>

      <div className="flex-1 min-h-0 overflow-auto bg-white dark:bg-slate-900">
        <table className="w-full text-sm min-w-[760px]" dir="rtl">
          <thead className="sticky top-0 z-10 bg-slate-50 dark:bg-slate-800 border-b">
            <tr>
              <th className="p-3 text-center font-bold text-navy-700 dark:text-gray-300 text-xs tracking-wide">מזהה</th>
              <th className="p-3 text-center font-bold text-navy-700 dark:text-gray-300 text-xs tracking-wide">שם קובץ</th>
              <th className="p-3 text-center font-bold text-navy-700 dark:text-gray-300 text-xs tracking-wide">עמוד</th>
              <th className="p-3 text-center font-bold text-navy-700 dark:text-gray-300 text-xs tracking-wide">סטטוס</th>
              <th className="p-3 text-center font-bold text-navy-700 dark:text-gray-300 text-xs tracking-wide">תאריך העלאה</th>
              <th className="p-3 text-center font-bold text-navy-700 dark:text-gray-300 text-xs tracking-wide">תצוגה</th>
            </tr>
          </thead>

          <tbody className="divide-y divide-gray-50 dark:divide-gray-800">
            {loading ? (
              <tr>
                <td colSpan={6} className="p-8 text-center text-sm text-gray-500 dark:text-gray-400">טוען...</td>
              </tr>
            ) : filteredForms.length === 0 ? (
              <tr>
                <td colSpan={6} className="p-8 text-center text-sm text-gray-500 dark:text-gray-400">
                  <div className="flex flex-col items-center gap-3">
                    <FileText size={24} className="text-gray-400" />
                    <div>אין טפסים להצגה</div>
                  </div>
                </td>
              </tr>
            ) : (
              filteredForms.map((form) => (
                <tr key={form.id} className="hover:bg-slate-50 dark:hover:bg-slate-800">
                  <td className="p-3 text-center text-sm font-medium text-gray-700 dark:text-gray-200">{form.id}</td>
                  <td className="p-3 text-center text-sm font-medium text-gray-700 dark:text-gray-200 max-w-[220px] truncate">{form.source_file || '—'}</td>
                  <td className="p-3 text-center text-sm text-gray-700 dark:text-gray-200">{form.page_number || '—'}</td>
                  <td className="p-3 text-center"><StatusBadge status={form.status || 'pending'} /></td>
                  <td className="p-3 text-center text-xs text-gray-500 dark:text-gray-400">{formatDate(form.uploaded_at)}</td>
                  <td className="p-3 text-center">
                    <button type="button" onClick={() => onSelectForm(form)} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs text-gray-600 hover:bg-slate-50 dark:border-slate-700 dark:text-gray-300">
                      <Eye size={14} /> פרטים
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
