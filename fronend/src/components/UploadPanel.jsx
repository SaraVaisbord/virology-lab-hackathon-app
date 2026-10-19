import { useRef, useState } from 'react'
import { CheckCircle2, FileUp, Loader2, UploadCloud, X } from 'lucide-react'
import ModalShell from './ui/ModalShell'
import { api } from '../api'
import { useMeta } from '../meta/MetaContext'

const MB = 1024 * 1024

const RESULT_STYLES = {
  created: { label: 'נקלט – נכנס לתור העיבוד', className: 'bg-teal-50 text-teal-700 border-teal-200 dark:bg-teal-950/40 dark:text-teal-300 dark:border-teal-900' },
  duplicate: { label: 'כבר הועלה בעבר', className: 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-900' },
  rejected: { label: 'נדחה', className: 'bg-red-50 text-red-700 border-red-200 dark:bg-red-950/40 dark:text-red-300 dark:border-red-900' },
}

const fileKey = (file) => `${file.name}-${file.size}-${file.lastModified}`
const extensionOf = (name = '') => (name.includes('.') ? name.slice(name.lastIndexOf('.')).toLowerCase() : '')

export default function UploadPanel({ onUploaded, onClose }) {
  const { upload } = useMeta()
  const inputRef = useRef(null)
  const [files, setFiles] = useState([])
  const [results, setResults] = useState([])
  const [dragActive, setDragActive] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')

  const validate = (file) => {
    if (file.size <= 0) return 'הקובץ ריק'
    if (file.size > upload.max_file_size_mb * MB) return `גדול מ-${upload.max_file_size_mb}MB`
    if (!upload.accepted_mime_types.includes(file.type) && !upload.accepted_extensions.includes(extensionOf(file.name))) {
      return 'סוג קובץ לא נתמך'
    }
    return ''
  }

  const addFiles = (incoming) => {
    const list = Array.from(incoming || [])
    const rejected = list.map((file) => [file, validate(file)]).filter(([, reason]) => reason)
    setError(rejected.map(([file, reason]) => `${file.name}: ${reason}`).join(' · '))
    const valid = list.filter((file) => !validate(file))
    setFiles((current) => {
      const seen = new Set(current.map(fileKey))
      return [...current, ...valid.filter((file) => !seen.has(fileKey(file)))]
    })
  }

  const handleUpload = async () => {
    setUploading(true)
    setError('')
    try {
      const response = await api.uploadFiles(files)
      setFiles([])
      onUploaded()
      // Everything accepted: close right away — progress is shown in the processing banner.
      if (response.every((result) => result.status === 'created')) onClose()
      else setResults(response)
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
    }
  }

  const footer = (
    <>
      <button type="button" className="btn-ghost" onClick={onClose}>{results.length ? 'סגור' : 'ביטול'}</button>
      <button type="button" className="btn-primary inline-flex items-center gap-2 disabled:cursor-not-allowed disabled:opacity-60" onClick={handleUpload} disabled={uploading || files.length === 0}>
        {uploading ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
        {uploading ? 'מעלה...' : `שלח${files.length ? ` (${files.length})` : ''}`}
      </button>
    </>
  )

  const acceptedLabel = upload.accepted_extensions.map((ext) => ext.slice(1).toUpperCase()).join(', ')

  return (
    <ModalShell title="העלאת טפסים" icon={UploadCloud} onClose={onClose} footer={footer} maxWidth="sm:max-w-2xl">
      <input
        ref={inputRef}
        type="file"
        multiple
        hidden
        accept={[...upload.accepted_mime_types, ...upload.accepted_extensions].join(',')}
        onChange={(event) => { addFiles(event.target.files); event.target.value = '' }}
      />

      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={(event) => { event.preventDefault(); setDragActive(true) }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(event) => { event.preventDefault(); setDragActive(false); addFiles(event.dataTransfer.files) }}
        className={`flex w-full flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed p-6 text-center transition-colors sm:p-8 ${dragActive ? 'border-teal-500 bg-teal-50 dark:bg-teal-950/20' : 'border-slate-200 bg-slate-50 hover:border-teal-300 dark:border-slate-700 dark:bg-slate-900/60'}`}
      >
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-teal-100 text-teal-700 dark:bg-teal-950/40 dark:text-teal-300">
          <FileUp size={22} />
        </span>
        <span className="text-sm font-medium text-gray-700 dark:text-gray-200">גרור קבצים לכאן או לחץ לבחירה</span>
        <span className="text-xs text-gray-500 dark:text-gray-400">{acceptedLabel} · עד {upload.max_file_size_mb}MB לקובץ · כל עמוד נכנס אוטומטית לתור העיבוד</span>
      </button>

      {files.length > 0 && (
        <ul className="space-y-2">
          {files.map((file) => (
            <li key={fileKey(file)} className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950/40">
              <span className="flex min-w-0 items-center gap-2">
                <FileUp size={14} className="shrink-0 text-gray-500" />
                <span dir="auto" className="truncate text-gray-700 dark:text-gray-200">{file.name}</span>
              </span>
              <button type="button" onClick={() => setFiles((current) => current.filter((item) => fileKey(item) !== fileKey(file)))} className="btn-ghost p-1.5" aria-label={`הסר ${file.name}`}>
                <X size={15} />
              </button>
            </li>
          ))}
        </ul>
      )}

      {error && <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">{error}</div>}

      {results.length > 0 && (
        <ul className="space-y-2">
          {results.map((result, index) => {
            const style = RESULT_STYLES[result.status] ?? RESULT_STYLES.rejected
            return (
              <li key={`${result.filename}-${index}`} className="rounded-xl border border-slate-200 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-950/40">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span dir="auto" className="truncate text-sm font-medium text-gray-700 dark:text-gray-200">{result.filename}</span>
                  <span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${style.className}`}>{style.label}</span>
                </div>
                {result.error && <p className="mt-1 text-xs text-red-600 dark:text-red-300">{result.error}</p>}
                {result.status === 'created' && <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{result.form_ids.length} עמודים</p>}
              </li>
            )
          })}
        </ul>
      )}
    </ModalShell>
  )
}
