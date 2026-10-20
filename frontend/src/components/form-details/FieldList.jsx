import { useEffect, useRef, useState } from 'react'
import { Check, Loader2, Pencil, Plus, Trash2, X } from 'lucide-react'
import StatusBadge from '../ui/StatusBadge'
import { useMeta } from '../../meta/MetaContext'
import { EMPTY, fieldDisplayValue, groupFieldsByName } from '../../lib/format'

const iconButton = 'inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-gray-500 hover:bg-slate-200 hover:text-gray-800 disabled:opacity-40 dark:text-gray-400 dark:hover:bg-slate-700 dark:hover:text-gray-100'

/** Inline text input with save / cancel (Enter / Escape). */
function InlineInput({ initial, onSave, onCancel, saving }) {
  const [value, setValue] = useState(initial)
  const ref = useRef(null)
  useEffect(() => { ref.current?.focus(); ref.current?.select() }, [])
  const save = () => { if (value.trim()) onSave(value.trim()) }
  return (
    <div className="flex w-full items-center gap-1">
      <input
        ref={ref}
        value={value}
        dir="auto"
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') save()
          if (event.key === 'Escape') { event.stopPropagation(); onCancel() }
        }}
        className="h-8 min-w-0 flex-1 rounded-md border-2 border-teal-400 bg-white px-2 text-sm text-gray-900 focus:outline-none dark:bg-slate-800 dark:text-gray-100"
        aria-label="ערך"
      />
      <button type="button" onClick={save} disabled={saving || !value.trim()} className={iconButton} aria-label="שמור">
        {saving ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />}
      </button>
      <button type="button" onClick={onCancel} disabled={saving} className={iconButton} aria-label="ביטול">
        <X size={15} />
      </button>
    </div>
  )
}

/**
 * Every field of the form, always editable by the lab worker — independent of extraction (works for queued,
 * failed or never-extracted forms too). Pencil = edit a value, trash = remove it, plus = add a value.
 */
export default function FieldList({ fields, activeFieldId, onSelect, onEdit, onAdd, onDelete, saving, error }) {
  const meta = useMeta()
  const groups = groupFieldsByName(fields)
  const toReview = fields.filter(meta.needsReview).length
  const [editing, setEditing] = useState(null) // field id being edited, or `add:<field_name>`
  const [confirmDelete, setConfirmDelete] = useState(null)

  const run = async (action) => {
    if (await action()) setEditing(null)
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">שדות הטופס</p>
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${toReview ? 'bg-pink-100 text-pink-700 dark:bg-pink-950/60 dark:text-pink-200' : 'bg-teal-50 text-teal-700 dark:bg-teal-950/60 dark:text-teal-300'}`}>
          {toReview ? `${toReview} לאימות` : 'אין שדות לאימות'}
        </span>
      </div>

      {error && <div className="mb-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">{error}</div>}

      <ul className="space-y-1.5">
        {meta.fields.map(({ key, label, multi_value: multi }) => {
          // Multi-value fields hide their "not found" placeholder (adding a value replaces it); a single-value
          // field keeps it as its one editable row.
          const rows = (groups[key] ?? []).filter((row) => row.status !== 'not_found' || !multi)
          const hasValue = rows.some((row) => fieldDisplayValue(row))
          const canAdd = multi || rows.length === 0
          return (
            <li key={key} className="space-y-1">
              {rows.map((field, index) => {
                const active = field.id === activeFieldId
                const value = fieldDisplayValue(field)
                return (
                  <div
                    key={field.id}
                    className={`flex items-center gap-2 rounded-lg border px-3 py-2 transition ${
                      active ? 'border-teal-500 bg-teal-50 dark:border-teal-400 dark:bg-teal-950/30' : 'border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900'
                    }`}
                  >
                    {editing === field.id ? (
                      <InlineInput initial={value} saving={saving} onCancel={() => setEditing(null)} onSave={(text) => run(() => onEdit(field.id, text))} />
                    ) : (
                      <>
                        <button type="button" onClick={() => onSelect(field.id)} aria-current={active ? 'true' : undefined} className="min-w-0 flex-1 text-right">
                          <span className="block text-xs text-gray-500 dark:text-gray-400">{label}{rows.length > 1 ? ` ${index + 1}` : ''}</span>
                          <span dir="auto" className="block truncate text-sm font-medium text-gray-800 dark:text-gray-100">{value || EMPTY}</span>
                        </button>
                        <StatusBadge status={field.status} kind="field" />
                        <button type="button" onClick={() => { setConfirmDelete(null); setEditing(field.id) }} className={iconButton} aria-label={`ערוך ${label}`} title="עריכה">
                          <Pencil size={14} />
                        </button>
                        {value && (confirmDelete === field.id ? (
                          <button type="button" onClick={() => { setConfirmDelete(null); onDelete(field.id) }} disabled={saving} className="rounded-md bg-red-600 px-2 py-1 text-[11px] font-semibold text-white hover:bg-red-700">
                            מחק?
                          </button>
                        ) : (
                          <button type="button" onClick={() => setConfirmDelete(field.id)} className={iconButton} aria-label={`מחק ${label}`} title="מחיקת ערך">
                            <Trash2 size={14} />
                          </button>
                        ))}
                      </>
                    )}
                  </div>
                )
              })}

              {canAdd && (editing === `add:${key}` ? (
                <div className="rounded-lg border border-dashed border-teal-300 bg-white px-3 py-2 dark:border-teal-800 dark:bg-slate-900">
                  <span className="mb-1 block text-xs text-gray-500 dark:text-gray-400">{label}</span>
                  <InlineInput initial="" saving={saving} onCancel={() => setEditing(null)} onSave={(text) => run(() => onAdd(key, text))} />
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => { setConfirmDelete(null); setEditing(`add:${key}`) }}
                  className="flex w-full items-center gap-1.5 rounded-lg border border-dashed border-slate-300 px-3 py-1.5 text-right text-xs text-gray-500 hover:border-teal-400 hover:text-teal-700 dark:border-slate-600 dark:text-gray-400 dark:hover:text-teal-300"
                >
                  <Plus size={13} /> {hasValue ? `הוסף ${label} נוסף` : `הוסף ${label}`}
                </button>
              ))}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
