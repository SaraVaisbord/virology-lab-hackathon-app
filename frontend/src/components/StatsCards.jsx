import { useEffect, useState } from 'react'
import { ClipboardList, CheckCircle2, AlertTriangle, Building2 } from 'lucide-react'
import { cardVariants } from '../theme'

function useCountUp(target, duration = 1200) {
  const [value, setValue] = useState(0)

  useEffect(() => {
    const isFloat = String(target).includes('.')
    const numeric = parseFloat(target)
    const start = performance.now()

    const tick = (now) => {
      const elapsed = now - start
      const progress = Math.min(elapsed / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      const current = eased * numeric
      setValue(isFloat ? parseFloat(current.toFixed(1)) : Math.floor(current))
      if (progress < 1) requestAnimationFrame(tick)
    }

    requestAnimationFrame(tick)
  }, [target, duration])

  return value
}

const cards = [
  {
    key: 'pending',
    icon: ClipboardList,
    label: 'טפסים ממתינים לבדיקה',
    title: 'ממתינים',
    sub: (s) => `מתוך ${s.totalForms} טפסים`,
    value: (s) => s.pendingForms,
    suffix: '',
    clickable: true,
    tooltip: 'ממתינים סופר טפסים (סטטוס טופס)',
  },
  {
    key: 'uncertain',
    icon: AlertTriangle,
    label: 'שדות לאימות ידני',
    title: 'לאימות',
    sub: () => 'דורשים בדיקה של לבורנטית',
    value: (s) => s.uncertainFields,
    suffix: '',
    clickable: true,
    tooltip: 'לאימות סופר שדות (סטטוס שדה)',
  },
  {
    key: 'senders',
    icon: Building2,
    label: 'בתי חולים ומרפאות ששלחו',
    sub: (s) => `${s.hospitalCount} בתי חולים · ${s.clinicCount} מרפאות`,
    value: (s) => s.senderTotal,
    suffix: '',
    clickable: false,
    tooltip: 'מספר הגופים השולחים השונים שהעלו טפסים',
  },
  {
    key: 'accuracy',
    icon: CheckCircle2,
    label: 'אחוז דיוק מערכת',
    sub: () => 'מבוסס על נתוני טבלת האמת',
    value: (s) => s.accuracyRate,
    suffix: '%',
    clickable: false,
    tooltip: 'דיוק מערכת',
  },
]

function StatCard({ card, stats, activeFilter, onFilter, isLoading = false }) {
  const { key, icon: Icon, label, sub, value, suffix, clickable, tooltip } = card
  const { iconColor, iconBg, activeBorder, activeBg, numberColor, ring } = cardVariants[key]
  const counted = useCountUp(Number(value(stats)) || 0)
  const isActive = activeFilter === key

  return (
    <div
      className={[
        'card px-5 py-4 flex flex-col justify-center relative overflow-hidden transition-all duration-200 group min-h-[88px]',
        clickable ? 'cursor-pointer hover:-translate-y-0.5 hover:shadow-md' : 'cursor-default',
        isActive ? `${activeBorder} ${activeBg}` : '',
      ].join(' ')}
      onClick={() => clickable && onFilter(key)}
      role={clickable ? 'button' : undefined}
      tabIndex={clickable ? 0 : undefined}
      onKeyDown={e => clickable && e.key === 'Enter' && onFilter(key)}
      aria-pressed={clickable ? isActive : undefined}
      aria-label={tooltip}
      title={tooltip}
    >
      <div className={`absolute inset-0 rounded-2xl ring-1 pointer-events-none ${ring || 'ring-gray-200/80 dark:ring-gray-700/50'}`} />

      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          {isLoading ? (
            <>
              <div className="h-8 w-16 rounded-lg bg-gray-200 dark:bg-slate-700 animate-pulse" />
              <div className="mt-2 h-4 w-28 rounded bg-gray-200 dark:bg-slate-700 animate-pulse" />
              <div className="mt-1.5 h-3 w-20 rounded bg-gray-200 dark:bg-slate-700 animate-pulse" />
            </>
          ) : (
            <>
              <p className={`text-3xl font-black leading-none tracking-tight tabular-nums ${numberColor || 'text-navy-800 dark:text-gray-100'}`}>
                {counted}{suffix}
              </p>
              <p className="text-sm font-semibold text-navy-700 dark:text-gray-300 mt-1.5 leading-tight">{label}</p>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{sub(stats)}</p>
              {clickable && isActive && (
                <span className="inline-block mt-1.5 text-xs font-medium bg-navy-600 text-white px-2 py-0.5 rounded-full">
                  מסנן פעיל
                </span>
              )}
            </>
          )}
        </div>

        <div className={`w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0 ${iconBg} transition-transform duration-200 ${clickable ? 'group-hover:scale-110' : ''}`}>
          <Icon size={22} className={iconColor} />
        </div>
      </div>
    </div>
  )
}

export default function StatsCards({ stats, activeFilter, onFilter, isLoading = false }) {
  return (
    <div className="flex-none grid grid-cols-1 sm:grid-cols-3 xl:grid-cols-1 xl:w-72 xl:self-start gap-3">
      {cards.map(card => (
        <StatCard key={card.key} card={card} stats={stats} activeFilter={activeFilter} onFilter={onFilter} isLoading={isLoading} />
      ))}
    </div>
  )
}