import { useState, useEffect } from 'react'
import Header from './components/Header'
import Footer from './components/Footer'
import UploadPanel from './components/UploadPanel'
import DataTable from './components/DataTable'
import FormDetailsModal from './components/FormDetailsModal'
import ProfilePage from './components/ProfilePage'
import { api } from './api'

export default function App() {
  const [darkMode, setDarkMode] = useState(false)
  const [forms, setForms] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedForm, setSelectedForm] = useState(null)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const [exportMenuOpen, setExportMenuOpen] = useState(false)
  const [exportLoading, setExportLoading] = useState(false)
  const [toast, setToast] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [query, setQuery] = useState('')
  const [columnFilters, setColumnFilters] = useState({})

  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode)
  }, [darkMode])

  const loadForms = async () => {
    setLoading(true)
    setError('')

    try {
      const data = await api.listForms({ limit: 100, offset: 0 })
      setForms(data || [])
    } catch (err) {
      setError(err.message || 'שגיאה בטעינת הטפסים.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadForms()
  }, [])

  useEffect(() => {
    if (!toast) return
    const timeout = setTimeout(() => setToast(''), 2500)
    return () => clearTimeout(timeout)
  }, [toast])

  const handleExport = async (mode = 'all') => {
    try {
      setExportLoading(true)
      setExportMenuOpen(false)
      const response = await api.exportForms({ mode, status: statusFilter === 'all' ? undefined : statusFilter, query, filters: columnFilters })
      const blob = new Blob([response.data], { type: response.contentType || 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = response.fileName || 'forms_export.xlsx'
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
      setToast('הקובץ הורד בהצלחה')
    } catch (err) {
      setError(err.message || 'ייצוא לא הצליח.')
      setToast('ייצוא נכשל')
    } finally {
      setExportLoading(false)
    }
  }

  return (
    <div className="h-screen overflow-hidden flex flex-col bg-surface-page dark:bg-slate-950 transition-colors duration-200" dir="rtl">
      <Header
        darkMode={darkMode}
        onToggleDark={() => setDarkMode((value) => !value)}
        onOpenProfile={() => setProfileOpen(true)}
      />

      <main className="flex-1 min-h-0 flex flex-col gap-3 p-4 overflow-hidden">
        <div className="flex-none">
          <h1 className="text-xl font-bold text-navy-800 dark:text-gray-100">לוח בקרה – אימות טפסים</h1>
          <p className="text-sm text-gray-400 dark:text-gray-500 mt-0.5">
            העלאה, צפייה וסטטוסים של טפסים שנשמרו ב-API
          </p>
        </div>

        <div className="flex-1 min-h-0 overflow-hidden">
          <div className="h-full flex flex-col gap-3">
            <div className="min-h-0 flex-1 overflow-hidden">
              <DataTable
                forms={forms}
                loading={loading}
                error={error}
                onSelectForm={setSelectedForm}
                onAddFile={() => setUploadOpen((value) => !value)}
                onExport={handleExport}
                exportMenuOpen={exportMenuOpen}
                onToggleExportMenu={() => setExportMenuOpen((value) => !value)}
                exportLoading={exportLoading}
                hasUploadOpen={uploadOpen}
                statusFilter={statusFilter}
                onChangeStatusFilter={setStatusFilter}
                query={query}
                onChangeQuery={setQuery}
                columnFilters={columnFilters}
                onChangeColumnFilter={(key, value) => setColumnFilters((prev) => ({ ...prev, [key]: value }))}
              />
            </div>
          </div>
        </div>
      </main>

      <Footer />

      {uploadOpen && (
        <div className="fixed inset-0 bg-slate-900/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl p-6 w-full max-w-2xl relative">
            <UploadPanel
              onUploadComplete={async () => {
                await loadForms()
                setUploadOpen(false)
              }}
              onClose={() => setUploadOpen(false)}
            />
          </div>
        </div>
      )}

      {profileOpen && (
        <ProfilePage
          darkMode={darkMode}
          onToggleDark={() => setDarkMode((value) => !value)}
          onClose={() => setProfileOpen(false)}
          forms={forms}
          onUndoApproval={() => {}}
        />
      )}

      {selectedForm && <FormDetailsModal form={selectedForm} onClose={() => setSelectedForm(null)} />}

      {toast && (
        <div className="fixed bottom-6 left-6 z-[60] rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm font-medium text-emerald-700 shadow-lg dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300">
          {toast}
        </div>
      )}
    </div>
  )
}