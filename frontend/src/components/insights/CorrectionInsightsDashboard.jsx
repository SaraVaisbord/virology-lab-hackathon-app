import { useMemo, useState } from 'react'
import { FlaskConical, Inbox, Loader2, SearchX } from 'lucide-react'
import { useMeta } from '../../meta/MetaContext'
import { useCorrectionInsights } from '../../hooks/useCorrectionInsights'
import { SUSPICION_SUPPORT_LEVELS } from '../../theme'
import FieldCorrectionChart from './FieldCorrectionChart'
import InsightCard from './InsightCard'

const DAY_MS = 24 * 60 * 60 * 1000
const PERIODS = [
  { key: '7', label: '7 ימים', days: 7 },
  { key: '30', label: '30 ימים', days: 30 },
  { key: '90', label: '90 ימים', days: 90 },
  { key: 'all', label: 'הכול', days: null },
]
const DEFAULT_PERIOD = '30'

const percentOf = (part, whole) => (whole ? Math.round((part / whole) * 100) : 0)

function Stat({ label, value, sub }) {
  return (
    <div className="card rounded-xl p-4">
      <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
      <p className="mt-1 text-2xl font-bold tabular-nums text-navy-800 dark:text-gray-100">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-gray-400 dark:text-gray-500">{sub}</p>}
    </div>
  )
}

function EmptyState({ icon: Icon, title, children }) {
  return (
    <div className="card flex flex-col items-center gap-2 rounded-xl px-6 py-10 text-center">
      <Icon size={28} className="text-gray-300 dark:text-gray-600" aria-hidden="true" />
      <p className="text-sm font-semibold text-navy-800 dark:text-gray-100">{title}</p>
      <div className="max-w-md text-sm text-gray-500 dark:text-gray-400">{children}</div>
    </div>
  )
}

/** Insights of one kind (established / first suspicions), grouped by field. */
function InsightGroup({ title, description, insights }) {
  const meta = useMeta()
  const byField = insights.reduce((groups, insight) => {
    ;(groups[insight.field_name] ||= []).push(insight)
    return groups
  }, {})
  if (insights.length === 0) return null
  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-base font-bold text-navy-800 dark:text-gray-100">{title} <span className="text-sm font-normal text-gray-400">({insights.length})</span></h2>
        <p className="text-xs text-gray-500 dark:text-gray-400">{description}</p>
      </div>
      {Object.entries(byField).map(([fieldName, items]) => (
        <div key={fieldName} className="space-y-2">
          <h3 className="text-sm font-semibold text-gray-600 dark:text-gray-300">{meta.fieldLabel(fieldName)}</h3>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {items.map((insight) => (
              <InsightCard key={`${insight.pattern_type}-${insight.field_name}-${insight.matched_field ?? insight.digit_swap ?? insight.source ?? ''}`} insight={insight} />
            ))}
          </div>
        </div>
      ))}
    </section>
  )
}

function Content({ data }) {
  const { coverage, insights } = data

  if (data.status === 'insufficient_data') {
    return (
      <EmptyState icon={Inbox} title="אין עדיין מספיק נתונים לתובנות">
        <p>{data.message}</p>
        <div className="mx-auto mt-4 h-2 w-56 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800" role="progressbar"
          aria-valuemin={0} aria-valuemax={coverage.required_reviewed_fields} aria-valuenow={coverage.reviewed_fields} aria-label="ערכים שנבדקו">
          <div className="h-full rounded-full bg-teal-600 dark:bg-teal-400" style={{ width: `${percentOf(coverage.reviewed_fields, coverage.required_reviewed_fields)}%` }} />
        </div>
        <p className="mt-2 text-xs">התובנות יופיעו כאן אחרי שהלבורנטית תאשר ותתקן עוד ערכים בטפסים.</p>
      </EmptyState>
    )
  }

  const suspicions = insights.filter((insight) => SUSPICION_SUPPORT_LEVELS.includes(insight.support))
  const established = insights.filter((insight) => !SUSPICION_SUPPORT_LEVELS.includes(insight.support))
  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label="ערכים שתוקנו בתקופה" value={coverage.corrected_fields} sub={`מתוך ${coverage.reviewed_fields} ערכים שהלבורנטית בדקה`} />
        <Stat label="שיעור התיקון בערכים שנבדקו" value={`${percentOf(coverage.corrected_fields, coverage.reviewed_fields)}%`} sub="לא מדד דיוק – רק ערכים שנבדקו נספרים" />
        <Stat label="ערכים שאושרו בלי בדיקה" value={coverage.auto_accepted_fields} sub="סומנו 'אומת' ולא נפתחו – לא נכללים בחישוב" />
      </div>

      {coverage.by_field.length > 0 && <FieldCorrectionChart fields={coverage.by_field} />}

      {insights.length === 0 ? (
        <EmptyState icon={SearchX} title="לא נמצאו דפוסים חוזרים בתקופה זו">
          התיקונים שנאספו לא חוזרים על עצמם מספיק פעמים כדי להצביע על דפוס.
        </EmptyState>
      ) : (
        <>
          <InsightGroup title="תובנות מבוססות" description="דפוסים שחוזרים במספר אירועים מספיק כדי לפעול לפיהם" insights={established} />
          <InsightGroup title="חשדות ראשוניים" description="מעט אירועים – כדאי לבדוק אותם, אבל עוד לא להסיק מהם מסקנות" insights={suspicions} />
        </>
      )}
    </div>
  )
}

export default function CorrectionInsightsDashboard() {
  const meta = useMeta()
  const [period, setPeriod] = useState(DEFAULT_PERIOD)
  const [fieldName, setFieldName] = useState('')
  const [sample, setSample] = useState(false)
  const since = useMemo(() => {
    const days = PERIODS.find((item) => item.key === period).days
    return days ? new Date(Date.now() - days * DAY_MS).toISOString() : undefined
  }, [period])
  const { data, loading, error, reload } = useCorrectionInsights({ since, fieldName: fieldName || undefined, sample })

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto max-w-6xl space-y-4 pb-4">
        <div>
          <h1 className="text-lg font-bold text-navy-800 dark:text-gray-100 sm:text-xl">Correction Intelligence – תובנות מתיקונים</h1>
          <p className="mt-0.5 text-sm text-gray-400 dark:text-gray-500">דפוסים חוזרים בתיקונים של הלבורנטית, ומה כדאי לבדוק בעקבותיהם</p>
        </div>

        {/* One filter row for everything below it. */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex rounded-lg border border-slate-200 bg-white p-0.5 dark:border-slate-700 dark:bg-slate-900" role="group" aria-label="תקופה">
            {PERIODS.map((item) => (
              <button
                key={item.key}
                type="button"
                aria-pressed={period === item.key}
                onClick={() => setPeriod(item.key)}
                disabled={sample}
                className={`rounded-md px-3 py-1 text-sm transition-colors disabled:opacity-50 ${
                  period === item.key ? 'bg-teal-600 text-white dark:bg-teal-500' : 'text-gray-600 hover:bg-slate-100 dark:text-gray-300 dark:hover:bg-slate-800'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
          <select
            value={fieldName}
            onChange={(event) => setFieldName(event.target.value)}
            disabled={sample}
            aria-label="שדה"
            className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm text-gray-700 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-gray-200"
          >
            <option value="">כל השדות</option>
            {meta.fields.map((field) => <option key={field.key} value={field.key}>{field.label}</option>)}
          </select>
          {import.meta.env.DEV && (
            <label className="ms-auto inline-flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
              <input type="checkbox" checked={sample} onChange={(event) => setSample(event.target.checked)} />
              נתוני דוגמה (פיתוח בלבד)
            </label>
          )}
        </div>

        {sample && (
          <div role="note" className="flex items-center gap-2 rounded-lg border border-review-300 bg-review-50 px-3 py-2 text-sm font-medium text-review-800 dark:border-review-800 dark:bg-review-950/40 dark:text-review-300">
            <FlaskConical size={16} aria-hidden="true" />
            נתוני דוגמה לבדיקת התצוגה בפיתוח – אלה אינן תובנות אמיתיות
          </div>
        )}

        {error && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">
            <span>לא ניתן לטעון את התובנות: {error}</span>
            <button type="button" className="btn-ghost text-sm" onClick={reload}>נסה שוב</button>
          </div>
        )}

        {!data && loading && (
          <div className="flex justify-center p-10 text-gray-500"><Loader2 className="animate-spin" size={22} aria-label="טוען" /></div>
        )}

        {data && (
          // A refetch keeps the last result on screen, dimmed, instead of flashing a loader.
          <div aria-busy={loading} className={`transition-opacity ${loading ? 'opacity-60' : ''}`}>
            <Content data={data} />
          </div>
        )}
      </div>
    </div>
  )
}
