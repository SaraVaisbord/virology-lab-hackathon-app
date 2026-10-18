import { useMemo, useState } from 'react'
import {
  User, Mail, Phone, Building2, BadgeCheck, Clock,
  CheckCircle2, FileText, Bell, Globe, Moon, Sun, X, Pencil, Check
} from 'lucide-react'
import Toggle from './ui/Toggle'
import StatusBadge from './ui/StatusBadge'

// TODO: introduce role-based permissions and authenticated user context before enabling write operations in production.

const statusStyle = {
  confirmed: 'text-teal-600 dark:text-teal-400 bg-teal-50 dark:bg-teal-950',
  edited: 'text-pink-600 dark:text-pink-400 bg-pink-50 dark:bg-pink-950',
  approved: 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950',
  undo: 'text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950',
}

const statusLabel = { confirmed: 'אושר', edited: 'תוקן', approved: 'טופס אושר', undo: 'בוטל אישור' }

const initialFields = [
  { key: 'name',     icon: User,       label: 'שם מלא',   value: 'ד"ר מיכל לוי' },
  { key: 'email',    icon: Mail,       label: 'דוא"ל',    value: 'michal.levi@sheba.health.gov.il' },
  { key: 'phone',    icon: Phone,      label: 'טלפון',    value: '03-530-XXXX' },
  { key: 'dept',     icon: Building2,  label: 'מחלקה',    value: 'המעבדה המרכזית לנגיפים' },
  { key: 'role',     icon: BadgeCheck, label: 'תפקיד',    value: 'לבורנטית ראשית – אימות נתונים' },
  { key: 'shift',    icon: Clock,      label: 'משמרת',    value: 'ראשון–חמישי, 07:00–15:00' },
]

function EditableField({ field, onSave }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(field.value)
  const Icon = field.icon

  const handleSave = () => {
    onSave(field.key, draft)
    setEditing(false)
  }

  const handleCancel = () => {
    setDraft(field.value)
    setEditing(false)
  }

  return (
    <div className={`flex items-center gap-3 p-3 rounded-xl transition-colors ${editing ? 'bg-teal-50 dark:bg-teal-950/30 ring-1 ring-teal-200 dark:ring-teal-800' : 'bg-gray-50 dark:bg-gray-800'}`}>
      <div className="w-9 h-9 rounded-lg bg-navy-600 flex items-center justify-center flex-shrink-0">
        <Icon size={18} className="text-white" />
      </div>

      <div className="flex-1 min-w-0">
        <p className="text-xs text-gray-400 dark:text-gray-500 mb-0.5">{field.label}</p>
        {editing ? (
          <input
            autoFocus
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handleSave(); if (e.key === 'Escape') handleCancel() }}
            className="w-full text-sm font-medium bg-white dark:bg-gray-800 border border-teal-300 dark:border-teal-700 rounded-lg px-2 py-1 text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-teal-400"
            dir="rtl"
          />
        ) : (
          <p 
            className="text-sm font-medium text-gray-800 dark:text-gray-200 truncate"
            dir={field.key === 'phone' ? 'ltr' : 'auto'}
            style={{ textAlign: field.key === 'phone' ? 'left' : 'right' }}
          >
            {field.value}
          </p>
        )}
      </div>

      <div className="flex items-center gap-1 flex-shrink-0">
        {editing ? (
          <>
            <button
              type="button"
              onClick={handleSave}
              className="w-7 h-7 flex items-center justify-center rounded-lg bg-teal-500 hover:bg-teal-600 text-white transition-colors"
              title="שמור"
              aria-label="שמור"
            >
              <Check size={13} />
            </button>
            <button
              type="button"
              onClick={handleCancel}
              className="w-7 h-7 flex items-center justify-center rounded-lg bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 text-gray-500 dark:text-gray-400 transition-colors"
              title="ביטול"
              aria-label="ביטול"
            >
              <X size={13} />
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={() => { setDraft(field.value); setEditing(true) }}
            className="w-8 h-8 flex items-center justify-center rounded-lg text-gray-500 dark:text-gray-400 hover:text-sky-600 hover:bg-sky-50 dark:hover:bg-sky-950/40 transition-all"
            title="ערוך שדה"
            aria-label="ערוך שדה"
          >
            <Pencil size={15} />
          </button>
        )}
      </div>
    </div>
  )
}

export default function ProfilePage({ darkMode, onToggleDark, onClose, forms = [], onUndoApproval }) {
  const [notifications, setNotifications] = useState(true)
  const [language, setLanguage] = useState('he')
  const [activeTab, setActiveTab] = useState('info')
  const [fields, setFields] = useState(initialFields)

  const formAuditEntries = useMemo(() =>
    forms.flatMap(form =>
      (form.auditLog || []).map(entry => ({
        ...entry,
        formName: form.fileName,
      }))
    ),
    [forms]
  )

  const handleSaveField = (key, newValue) => {
    setFields(prev => prev.map(f => f.key === key ? { ...f, value: newValue } : f))
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/40 dark:bg-black/60 animate-fade-in flex items-start justify-end" onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="h-full w-full max-w-xl bg-white dark:bg-gray-900 shadow-2xl overflow-y-auto animate-slide-up flex flex-col" dir="rtl" role="dialog" aria-modal="true" aria-label="פרופיל משתמש">
        <div className="bg-navy-700 dark:bg-navy-900 px-6 pt-8 pb-6 relative">
          <button type="button" onClick={onClose} className="absolute top-4 left-4 text-white/60 hover:text-white transition-colors" aria-label="סגור פרופיל">
            <X size={20} />
          </button>
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-full bg-gradient-to-br from-teal-400 to-teal-600 flex items-center justify-center text-white text-2xl font-bold shadow-lg">
              מ
            </div>
            <div>
              <h2 className="text-xl font-bold text-white">{fields.find(f => f.key === 'name')?.value}</h2>
              <p className="text-teal-300 text-sm font-medium">{fields.find(f => f.key === 'role')?.value}</p>
              <p className="text-white/50 text-xs mt-0.5">המעבדה המרכזית לנגיפים</p>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3 mt-6">
            {[
              { label: 'טפסים אושרו', value: '47' },
              { label: 'שדות תוקנו', value: '12' },
              { label: 'דיוק אישי', value: '94%' },
            ].map(s => (
              <div key={s.label} className="bg-white/10 rounded-xl px-3 py-2.5 text-center">
                <p className="text-white font-bold text-lg leading-tight">{s.value}</p>
                <p className="text-white/60 text-xs mt-0.5">{s.label}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="flex border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 sticky top-0 z-10">
          {[
            { key: 'info', label: 'פרטים אישיים' },
            { key: 'activity', label: 'היסטוריה' },
            { key: 'settings', label: 'הגדרות' },
          ].map(tab => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveTab(tab.key)}
              className="flex-1 py-3 text-sm font-medium transition-colors flex justify-center"
            >
              <span className={`pb-2 border-b-2 ${activeTab === tab.key ? 'border-teal-500 text-teal-600 dark:text-teal-400' : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'}`}>
                {tab.label}
              </span>
            </button>
          ))}
        </div>

        <div className="flex-1 px-6 py-6 space-y-3">
          {activeTab === 'info' && (
            <div className="space-y-3">
              <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide mb-1">
                פרטי קשר · לחץ על עיפרון לעריכה
              </p>
              {fields.map(field => (
                <EditableField key={field.key} field={field} onSave={handleSaveField} />
              ))}
            </div>
          )}

          {activeTab === 'activity' && (
            <div className="space-y-3">
              <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide">פעולות אחרונות</p>
              {formAuditEntries.length === 0 ? (
                <div className="rounded-xl bg-gray-50 dark:bg-gray-800 p-3 text-sm text-gray-500 dark:text-gray-400">
                  אין פעילות עדיין.
                </div>
              ) : (
                formAuditEntries.map((item, index) => (
                  <div key={`${item.id}-${index}`} className="flex items-center gap-3 p-3 rounded-xl bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
                    <div className="w-9 h-9 rounded-lg bg-navy-600 flex items-center justify-center flex-shrink-0">
                      <FileText size={15} className="text-white" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">{item.formName}</p>
                      <p className="text-xs text-gray-400 dark:text-gray-500">
                        {item.action === 'undo' ? 'ביטול אישור' : item.action === 'approval' ? 'אישור שדה' : item.action}
                        {item.field && ` · ${item.field}`}
                      </p>
                    </div>
                    <div className="flex flex-col items-end gap-1 flex-shrink-0">
                      <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${statusStyle[item.action === 'undo' ? 'undo' : 'confirmed']}`}>
                        {statusLabel[item.action === 'undo' ? 'undo' : 'confirmed']}
                      </span>
                      <span className="text-xs text-gray-400 dark:text-gray-500">{new Date(item.timestamp).toLocaleString('he-IL')}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === 'settings' && (
            <div className="space-y-4">
              <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide">העדפות תצוגה</p>

              <div className="flex items-center justify-between p-4 rounded-xl bg-gray-50 dark:bg-gray-800">
                <div className="flex items-center gap-3">
                  {darkMode ? <Moon size={18} className="text-teal-400" /> : <Sun size={18} className="text-amber-500" />}
                  <div>
                    <p className="text-sm font-medium text-gray-800 dark:text-gray-200">מצב תצוגה</p>
                    <p className="text-xs text-gray-400">{darkMode ? 'מצב כהה פעיל' : 'מצב בהיר פעיל'}</p>
                  </div>
                </div>
                <Toggle enabled={darkMode} onChange={onToggleDark} />
              </div>

              <div className="flex items-center justify-between p-4 rounded-xl bg-gray-50 dark:bg-gray-800">
                <div className="flex items-center gap-3">
                  <Bell size={18} className="text-navy-600 dark:text-teal-400" />
                  <div>
                    <p className="text-sm font-medium text-gray-800 dark:text-gray-200">התראות</p>
                    <p className="text-xs text-gray-400">קבלת התראה על שדות חדשים לאימות</p>
                  </div>
                </div>
                <Toggle enabled={notifications} onChange={setNotifications} />
              </div>

              <div className="flex items-center justify-between p-4 rounded-xl bg-gray-50 dark:bg-gray-800">
                <div className="flex items-center gap-3">
                  <Globe size={18} className="text-navy-600 dark:text-teal-400" />
                  <div>
                    <p className="text-sm font-medium text-gray-800 dark:text-gray-200">שפת ממשק</p>
                    <p className="text-xs text-gray-400">בחר שפה מועדפת</p>
                  </div>
                </div>
                <select value={language} onChange={e => setLanguage(e.target.value)} className="text-sm bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 text-gray-700 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-teal-400">
                  <option value="he">עברית</option>
                  <option value="en">English</option>
                </select>
              </div>

              <div className="pt-2">
                <button type="button" className="w-full py-2.5 rounded-xl border border-red-200 dark:border-red-900 text-red-500 dark:text-red-400 text-sm font-medium hover:bg-red-50 dark:hover:bg-red-950 transition-colors">
                  התנתקות
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}