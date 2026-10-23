import { useCallback, useEffect, useMemo, useState } from 'react'
import Header from './components/Header'
import Footer from './components/Footer'
import UploadPanel from './components/UploadPanel'
import DataTable from './components/DataTable'
import TableToolbar from './components/TableToolbar'
import ProcessingBanner from './components/ProcessingBanner'
import FormDetailsModal from './components/form-details/FormDetailsModal'
import CorrectionInsightsDashboard from './components/insights/CorrectionInsightsDashboard'
import { api } from './api'
import { useForms } from './hooks/useForms'
import { useDebouncedValue } from './hooks/useDebouncedValue'
import { useHashRoute } from './hooks/useHashRoute'
import { FORM_STATUS } from './lib/domainKeys'

const TOAST_DURATION_MS = 2500
const INITIAL_FILTERS = { status: '', query: '', columnFilters: {}, sortBy: 'id', sortDir: 'desc' }

function downloadBlob(blob, fileName) {
  const url = URL.createObjectURL(blob)
  const link = Object.assign(document.createElement('a'), { href: url, download: fileName })
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export default function App() {
  const route = useHashRoute()
  const [darkMode, setDarkMode] = useState(false)
  const [filters, setFilters] = useState(INITIAL_FILTERS)
  const [selected, setSelected] = useState(null) // { form, fieldId, editMode }
  const [uploadOpen, setUploadOpen] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [toast, setToast] = useState(null) // { text, tone }

  // Text inputs are debounced so typing doesn't fire a request per keystroke.
  const debouncedQuery = useDebouncedValue(filters.query)
  const debouncedColumnFilters = useDebouncedValue(filters.columnFilters)
  const { status, sortBy, sortDir } = filters
  const serverFilters = useMemo(
    () => ({ status, sortBy, sortDir, query: debouncedQuery, columnFilters: debouncedColumnFilters }),
    [status, sortBy, sortDir, debouncedQuery, debouncedColumnFilters],
  )
  const { items, total, summary, loading, loadingMore, error, hasMore, loadMore, refresh, updateItem } = useForms(serverFilters)

  useEffect(() => { document.documentElement.classList.toggle('dark', darkMode) }, [darkMode])

  useEffect(() => {
    if (!toast) return undefined
    const timer = setTimeout(() => setToast(null), TOAST_DURATION_MS)
    return () => clearTimeout(timer)
  }, [toast])

  const changeFilters = useCallback((patch) => setFilters((current) => ({ ...current, ...patch })), [])

  const handleExport = async (mode) => {
    setExporting(true)
    try {
      const { blob, fileName } = await api.exportForms(mode, serverFilters)
      downloadBlob(blob, fileName || 'forms_export.xlsx')
      setToast({ text: 'הקובץ הורד בהצלחה', tone: 'success' })
    } catch (err) {
      setToast({ text: `ייצוא נכשל: ${err.message}`, tone: 'error' })
    } finally {
      setExporting(false)
    }
  }

  const handleRetry = async (form) => {
    try {
      updateItem(await api.retryForm(form.id))
      setSelected(null)
      refresh()
    } catch (err) {
      setToast({ text: err.message, tone: 'error' })
    }
  }

  const handleDelete = async (form) => {
    try {
      await api.deleteForm(form.id)
      if (selected?.form.id === form.id) setSelected(null)
      refresh()
      setToast({ text: `הרשומה "${form.source_file}" (עמוד ${form.page_number}) נמחקה`, tone: 'success' })
    } catch (err) {
      setToast({ text: err.message, tone: 'error' })
    }
  }

  return (
    <div className="flex h-[100dvh] flex-col overflow-hidden bg-surface-page transition-colors duration-200 dark:bg-slate-950" dir="rtl">
      <Header darkMode={darkMode} onToggleDark={() => setDarkMode((value) => !value)} route={route} />

      <main className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden p-3 sm:p-4">
        {route === 'insights' ? <CorrectionInsightsDashboard /> : (
        <>
        <div className="flex-none">
          <h1 className="text-lg font-bold text-navy-800 dark:text-gray-100 sm:text-xl">לוח בקרה – אימות טפסים</h1>
          <p className="mt-0.5 hidden text-sm text-gray-400 dark:text-gray-500 sm:block">העלאה, חילוץ אוטומטי ואימות של טפסי התחייבות</p>
        </div>

        <ProcessingBanner summary={summary} onShowFailed={() => changeFilters({ status: FORM_STATUS.FAILED })} />

        <div className="card flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl">
          <TableToolbar filters={filters} onChangeFilters={changeFilters} onAddFile={() => setUploadOpen(true)} onExport={handleExport} exporting={exporting} />
          <div className="min-h-0 flex-1">
            <DataTable
              forms={items}
              total={total}
              loading={loading}
              loadingMore={loadingMore}
              hasMore={hasMore}
              onLoadMore={loadMore}
              error={error}
              filters={filters}
              onChangeFilters={changeFilters}
              onOpenForm={(form, fieldId) => setSelected({ form, fieldId })}
              onEditForm={(form) => setSelected({ form, editMode: true })}
              onRetry={handleRetry}
              onDelete={handleDelete}
            />
          </div>
        </div>
        </>
        )}
      </main>

      <Footer />

      {uploadOpen && <UploadPanel onUploaded={() => refresh()} onClose={() => setUploadOpen(false)} />}

      {selected && (
        <FormDetailsModal
          key={selected.form.id}
          form={selected.form}
          initialFieldId={selected.fieldId}
          editMode={selected.editMode}
          onClose={() => setSelected(null)}
          onFormUpdated={(form) => { updateItem(form); refresh() }}
          onRetry={handleRetry}
        />
      )}

      {toast && (
        <div
          role="status"
          className={`fixed bottom-4 left-4 right-4 z-[60] rounded-lg border px-4 py-2 text-sm font-medium shadow-lg sm:right-auto ${
            toast.tone === 'error'
              ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300'
              : 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300'
          }`}
        >
          {toast.text}
        </div>
      )}
    </div>
  )
}
