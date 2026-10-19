import { useEffect, useState } from 'react'
import { FileSearch, Loader2, RotateCcw } from 'lucide-react'
import ModalShell from '../ui/ModalShell'
import StatusBadge from '../ui/StatusBadge'
import DocumentViewer from './DocumentViewer'
import FieldEditor from './FieldEditor'
import FieldList from './FieldList'
import PageSources from './PageSources'
import { api } from '../../api'
import { useMeta } from '../../meta/MetaContext'
import { fieldDisplayValue, formatDateTime } from '../../lib/format'

/** Next field that still needs a decision, searching forward from the current one (wrapping around). */
function nextFieldToReview(fields, currentId, needsReview) {
  const start = fields.findIndex((field) => field.id === currentId)
  const ordered = [...fields.slice(start + 1), ...fields.slice(0, start + 1)]
  return ordered.find(needsReview)?.id ?? currentId
}

export default function FormDetailsModal({ form: initialForm, initialFieldId, onClose, onFormUpdated, onRetry }) {
  const meta = useMeta()
  const [form, setForm] = useState(initialForm)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [activeFieldId, setActiveFieldId] = useState(initialFieldId ?? null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')

  useEffect(() => {
    let cancelled = false
    api.getForm(initialForm.id)
      .then((data) => {
        if (cancelled) return
        setForm(data)
        setActiveFieldId((current) => current ?? (data.fields.find(meta.needsReview) ?? data.fields[0])?.id ?? null)
      })
      .catch((err) => { if (!cancelled) setLoadError(err.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [initialForm.id, meta])

  const fields = form.fields ?? []
  const activeField = fields.find((field) => field.id === activeFieldId) ?? null
  const pending = meta.isPendingForm(form.status)

  const selectField = (id) => {
    setActiveFieldId(id)
    setSaveError('')
  }

  const approve = async (value) => {
    if (!value && fieldDisplayValue(activeField)) {
      setSaveError('יש להזין ערך לפני האישור.')
      return
    }
    setSaving(true)
    setSaveError('')
    try {
      const updated = await api.confirmField(form.id, activeField.id, value || null)
      setForm(updated)
      onFormUpdated(updated)
      setActiveFieldId(nextFieldToReview(updated.fields, activeField.id, meta.needsReview))
    } catch (err) {
      setSaveError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <ModalShell title={form.source_file} icon={FileSearch} onClose={onClose} maxWidth="max-w-7xl">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-gray-600 dark:text-gray-300">
        <StatusBadge status={form.status} />
        <span>עמוד {form.page_number}</span>
        <span>הועלה {formatDateTime(form.uploaded_at)}</span>
        {form.status === 'failed' && (
          <button type="button" onClick={() => onRetry(form)} className="inline-flex items-center gap-1 rounded-lg border border-red-200 px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-50 dark:border-red-900 dark:text-red-300">
            <RotateCcw size={13} /> נסה שוב
          </button>
        )}
      </div>

      {form.error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">{form.error}</div>
      )}
      {loadError && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">{loadError}</div>
      )}

      {/* Mobile order: editor → document → field list. Desktop: editor + list on one side, document on the other. */}
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
        <div className="lg:col-start-1">
          {loading ? (
            <div className="flex items-center gap-2 text-sm text-gray-500"><Loader2 size={16} className="animate-spin" /> טוען פרטים...</div>
          ) : pending ? (
            <div className="flex items-center gap-2 rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm text-indigo-700 dark:border-indigo-900 dark:bg-indigo-950/30 dark:text-indigo-200">
              <Loader2 size={16} className="animate-spin" /> הטופס עדיין בעיבוד – השדות יופיעו כשהחילוץ יסתיים.
            </div>
          ) : (
            activeField && <FieldEditor field={activeField} sources={form.sources} onApprove={approve} saving={saving} error={saveError} />
          )}
        </div>

        <div className="h-[60vh] lg:sticky lg:top-0 lg:col-start-2 lg:row-span-2 lg:row-start-1 lg:h-[calc(100dvh-14rem)]">
          <DocumentViewer imageUrl={api.getFormImageUrl(form.id)} field={activeField} alt={`עמוד ${form.page_number} של ${form.source_file}`} />
        </div>

        {!loading && (
          <div className="space-y-4 lg:col-start-1">
            {!pending && <FieldList fields={fields} activeFieldId={activeFieldId} onSelect={selectField} />}
            <PageSources sources={form.sources} fields={fields} onSelectField={selectField} />
          </div>
        )}
      </div>
    </ModalShell>
  )
}
