import { CalendarRange, HelpCircle, Lightbulb, ShieldCheck } from 'lucide-react'
import { useMeta } from '../../meta/MetaContext'
import { formatDate } from '../../lib/format'
import { SUSPICION_SUPPORT_LEVELS, insightSupportStyles } from '../../theme'

/** The detail that refines a pattern, in words (which field, which digits, which source). */
function describeDetail(insight, meta) {
  if (insight.matched_field) return `הערך היה שייך לשדה ${meta.fieldLabel(insight.matched_field)}`
  if (insight.digit_swap) {
    const [read, correct] = insight.digit_swap.split('>')
    return `הספרה ${correct} נקראה כ-${read}`
  }
  if (insight.source) return `${meta.source_labels[insight.source] ?? insight.source} קרא את הערך הנכון`
  return null
}

function period(first, last) {
  const [from, to] = [formatDate(first), formatDate(last)]
  return from === to ? from : `${from} – ${to}`
}

export default function InsightCard({ insight }) {
  const meta = useMeta()
  const suspicion = SUSPICION_SUPPORT_LEVELS.includes(insight.support)
  const style = insightSupportStyles[suspicion ? 'suspicion' : 'established']
  const SupportIcon = suspicion ? HelpCircle : ShieldCheck
  const detail = describeDetail(insight, meta)
  const { form_type: formType, sender, written_as: writtenAs } = insight.concentrated_in
  const context = [
    formType && `טפסי ${meta.form_types[formType] ?? formType}`,
    sender,
    writtenAs && (meta.written_as_labels[writtenAs] ?? writtenAs),
  ].filter(Boolean)

  return (
    <article className={`flex flex-col gap-2.5 rounded-xl p-4 ${style.card}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ${style.badge}`}>
          <SupportIcon size={12} aria-hidden="true" />
          {suspicion ? 'חשד ראשוני – דורש בדיקה' : 'תובנה מבוססת'}
        </span>
        <span className="text-xs text-gray-500 dark:text-gray-400">{meta.insight_support_levels[insight.support]}</span>
      </div>

      <h3 className="text-sm font-bold text-navy-800 dark:text-gray-100">
        {meta.insight_patterns[insight.pattern_type] ?? insight.pattern_type}
        {detail && <span className="font-normal text-gray-600 dark:text-gray-300"> · {detail}</span>}
      </h3>

      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs text-gray-600 dark:text-gray-300">
        <dt className="text-gray-400 dark:text-gray-500">אירועים</dt>
        <dd className="tabular-nums">
          {insight.event_count} מתוך {insight.reviewed_count} ערכים שנבדקו בשדה ({Math.round(insight.share * 100)}%)
        </dd>
        <dt className="text-gray-400 dark:text-gray-500">תקופה</dt>
        <dd className="inline-flex items-center gap-1">
          <CalendarRange size={12} aria-hidden="true" /> {period(insight.first_seen, insight.last_seen)}
        </dd>
        {context.length > 0 && (
          <>
            <dt className="text-gray-400 dark:text-gray-500">מרוכז ב</dt>
            <dd className="flex flex-wrap gap-1">
              {context.map((item) => (
                <span key={item} className="rounded-full bg-slate-100 px-2 py-0.5 text-gray-700 dark:bg-slate-800 dark:text-gray-200">{item}</span>
              ))}
            </dd>
          </>
        )}
      </dl>

      <p className="flex gap-2 rounded-lg bg-slate-50 p-2.5 text-xs leading-5 text-gray-700 dark:bg-slate-800/60 dark:text-gray-200">
        <Lightbulb size={14} className="mt-0.5 shrink-0 text-teal-600 dark:text-teal-400" aria-hidden="true" />
        <span>{insight.recommendation}</span>
      </p>
    </article>
  )
}
