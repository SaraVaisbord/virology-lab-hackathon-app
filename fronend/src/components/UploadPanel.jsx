import { useRef, useState } from 'react'
import { CheckCircle2, FileUp, Loader2, UploadCloud, X } from 'lucide-react'
import { api } from '../api'

const MAX_FILE_SIZE = 50 * 1024 * 1024
const ACCEPTED_MIME_TYPES = ['application/pdf', 'image/png', 'image/jpeg']
const ACCEPTED_EXTENSIONS = ['.pdf', '.png', '.jpg', '.jpeg']

const statusStyles = {
  created: 'bg-teal-50 text-teal-700 border-teal-200 dark:bg-teal-950/40 dark:text-teal-300 dark:border-teal-900',
  duplicate: 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-900',
  rejected: 'bg-red-50 text-red-700 border-red-200 dark:bg-red-950/40 dark:text-red-300 dark:border-red-900',
}

const statusLabels = {
  created: 'נוצר',
  duplicate: 'כפילות',
  rejected: 'נדחה',
}

const getFileExtension = (fileName = '') => {
  const lower = fileName.toLowerCase()
  const lastDot = lower.lastIndexOf('.')
  return lastDot >= 0 ? lower.slice(lastDot) : ''
}

const isSupportedFile = (file) => {
  const mime = (file.type || '').toLowerCase()
  const extension = getFileExtension(file.name)
  const supportedMime = ACCEPTED_MIME_TYPES.includes(mime)
  const supportedExtension = ACCEPTED_EXTENSIONS.includes(extension)

  return supportedMime || supportedExtension
}

const getFileError = (file) => {
  if (!file) {
    return 'קובץ לא תקין.'
  }

  if (file.size <= 0) {
    return `הקובץ "${file.name || 'לא ידוע'}" ריק.`
  }

  if (file.size > MAX_FILE_SIZE) {
    return `הקובץ "${file.name || 'לא ידוע'}" גדול מדי. המותר הוא עד 50MB.`
  }

  if (!isSupportedFile(file)) {
    return `סוג הקובץ "${file.name || 'לא ידוע'}" אינו נתמך. אפשר להעלות רק PDF, PNG ו-JPEG.`
  }

  return ''
}

export default function UploadPanel({ onUploadComplete, onClose }) {
  const fileInputRef = useRef(null)
  const [selectedFiles, setSelectedFiles] = useState([])
  const [uploadResults, setUploadResults] = useState([])
  const [dragActive, setDragActive] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState('')

  const addFiles = (files) => {
    const incoming = Array.from(files || [])
    if (!incoming.length) return

    const validFiles = []
    const rejectedFiles = []

    incoming.forEach((file) => {
      const validationError = getFileError(file)
      if (validationError) {
        rejectedFiles.push(`${file.name || 'קובץ'}: ${validationError}`)
        return
      }

      validFiles.push(file)
    })

    if (rejectedFiles.length > 0) {
      setError(rejectedFiles.join(' | '))
    } else {
      setError('')
    }

    if (validFiles.length === 0) {
      return
    }

    setSelectedFiles((prev) => {
      const seen = new Set(prev.map((file) => `${file.name}-${file.size}-${file.lastModified}`))
      const next = [...prev]
      validFiles.forEach((file) => {
        const key = `${file.name}-${file.size}-${file.lastModified}`
        if (!seen.has(key)) {
          next.push(file)
          seen.add(key)
        }
      })
      return next
    })
  }

  const removeFile = (name, size, lastModified) => {
    setSelectedFiles((prev) => prev.filter((file) => !(file.name === name && file.size === size && file.lastModified === lastModified)))
    setError('')
  }

  const handleUpload = async () => {
    if (!selectedFiles.length) {
      setError('בחר לפחות קובץ אחד להעלאה.')
      return
    }

    const invalidFiles = selectedFiles.filter((file) => !!getFileError(file))
    if (invalidFiles.length > 0) {
      setError(invalidFiles.map((file) => `${file.name}: ${getFileError(file)}`).join(' | '))
      return
    }

    setError('')
    setIsUploading(true)

    try {
      const results = await api.uploadFiles(selectedFiles)
      setUploadResults(results)
      setSelectedFiles([])
      await onUploadComplete?.()
    } catch (err) {
      setError(err.message || 'העלאה נכשלה.')
    } finally {
      setIsUploading(false)
    }
  }

  return (
    <div className="card p-4 md:p-5" dir="rtl">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-navy-800 dark:text-gray-100">העלאת טפסים</h2>
          <p className="text-xs text-gray-500 dark:text-gray-400">PDF, PNG, JPEG</p>
        </div>

        <button
          type="button"
          onClick={onClose}
          className="rounded-lg p-2 text-gray-500 hover:bg-slate-100 dark:hover:bg-slate-800"
          aria-label="סגור העלאה"
        >
          <X size={16} />
        </button>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        multiple
        hidden
        accept=".pdf,image/png,image/jpeg"
        onChange={(event) => {
          addFiles(event.target.files)
          event.target.value = ''
        }}
      />

      <div
        className={`rounded-2xl border-2 border-dashed p-5 transition-colors ${dragActive ? 'border-teal-500 bg-teal-50 dark:bg-teal-950/20' : 'border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/60'}`}
        onDragOver={(event) => {
          event.preventDefault()
          setDragActive(true)
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragActive(false)
          addFiles(event.dataTransfer.files)
        }}
      >
        <div className="flex flex-col items-center justify-center gap-3 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-teal-100 text-teal-700 dark:bg-teal-950/40 dark:text-teal-300">
            <FileUp size={22} />
          </div>
          <div>
            <p className="text-sm font-medium text-gray-700 dark:text-gray-200">גרור קבצים לכאן או לחץ כדי לבחור</p>
            <p className="text-xs text-gray-500 dark:text-gray-400">נתמכים: PDF, PNG, JPEG • עד 50MB לכל קובץ</p>
          </div>
        </div>
      </div>

      <div className="mt-4 flex items-center justify-between gap-3">
        <button type="button" className="btn-primary inline-flex items-center gap-2" onClick={() => fileInputRef.current?.click()}>
          <UploadCloud size={16} /> בחר קבצים
        </button>
        <button
          type="button"
          className="btn-primary inline-flex items-center gap-2 disabled:opacity-60 disabled:cursor-not-allowed"
          onClick={handleUpload}
          disabled={isUploading || selectedFiles.length === 0}
        >
          {isUploading ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
          {isUploading ? 'מעלה...' : 'שלח'}
        </button>
      </div>

      {selectedFiles.length > 0 && (
        <div className="mt-4 space-y-2">
          {selectedFiles.map((file) => (
            <div key={`${file.name}-${file.size}-${file.lastModified}`} className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950/40">
              <div className="flex min-w-0 items-center gap-2">
                <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-slate-100 text-gray-600 dark:bg-slate-800 dark:text-gray-300">
                  <FileUp size={14} />
                </span>
                <span className="truncate text-gray-700 dark:text-gray-200">{file.name}</span>
              </div>
              <button type="button" onClick={() => removeFile(file.name, file.size, file.lastModified)} className="btn-ghost p-1.5 text-gray-500" aria-label={`הסר ${file.name}`}>
                <X size={15} />
              </button>
            </div>
          ))}
        </div>
      )}

      {error && (
        <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">
          {error}
        </div>
      )}

      {uploadResults.length > 0 && (
        <div className="mt-5 space-y-2">
          {uploadResults.map((result, index) => (
            <div key={`${result.filename}-${index}`} className="rounded-xl border border-slate-200 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-950/40">
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm font-medium text-gray-700 dark:text-gray-200">{result.filename || 'קובץ'}</span>
                <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${statusStyles[result.status] || statusStyles.rejected}`}>
                  {statusLabels[result.status] || 'נדחה'}
                </span>
              </div>
              {result.error && <p className="mt-2 text-xs text-red-600 dark:text-red-300">{result.error}</p>}
              {result.form_ids?.length > 0 && <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">מזהים: {result.form_ids.join(', ')}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
