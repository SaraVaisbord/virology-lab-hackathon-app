import { useEffect, useRef, useState } from 'react'
import { Clock, ScanLine, XCircle } from 'lucide-react'
import { useMeta } from '../meta/MetaContext'

const COUNTDOWN_TICK_MS = 30_000

function formatRemaining(untilIso) {
  const minutes = Math.max(1, Math.round((new Date(untilIso).getTime() - Date.now()) / 60_000))
  if (minutes < 60) return `${minutes} דק׳`
  const hours = Math.floor(minutes / 60)
  return `${hours}:${String(minutes % 60).padStart(2, '0')} שע׳`
}

/** Tracks the size of the current processing batch so the progress bar is meaningful. */
function useBatchProgress(pending) {
  const batchSize = useRef(0)
  if (pending === 0) batchSize.current = 0
  else batchSize.current = Math.max(batchSize.current, pending)
  const size = batchSize.current
  return { done: size - pending, size, percent: size ? Math.round(((size - pending) / size) * 100) : 0 }
}

function useNow(enabled) {
  const [, setTick] = useState(0)
  useEffect(() => {
    if (!enabled) return undefined
    const timer = setInterval(() => setTick((value) => value + 1), COUNTDOWN_TICK_MS)
    return () => clearInterval(timer)
  }, [enabled])
}

export default function ProcessingBanner({ summary, onShowFailed }) {
  const meta = useMeta()
  const pending = summary?.pending ?? 0
  const failed = summary?.by_status?.failed ?? 0
  const pausedUntil = summary?.queue?.paused_until
  const pauseReason = summary?.queue?.pause_reason
  const progress = useBatchProgress(pending)
  useNow(Boolean(pausedUntil))

  if (!pending && !failed) return null

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-stretch" role="status" aria-live="polite">
      {pending > 0 && (
        pauseReason ? (
          <div className="card flex flex-1 items-center gap-3 border border-amber-200 bg-amber-50/80 px-4 py-3 dark:border-amber-900 dark:bg-amber-950/30">
            <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300">
              <Clock size={20} />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-amber-800 dark:text-amber-200">
                {meta.queue_pause_reasons[pauseReason] ?? 'העיבוד מושהה'}
              </p>
              <p className="text-xs text-amber-700/80 dark:text-amber-300/80">
                {pending} טפסים ממתינים בתור{pausedUntil ? ` · ממשיך בעוד ${formatRemaining(pausedUntil)}` : ''}
              </p>
            </div>
          </div>
        ) : (
          <div className="card relative flex flex-1 items-center gap-3 overflow-hidden px-4 py-3">
            <div className="relative flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600 dark:bg-indigo-950/60 dark:text-indigo-300">
              <span className="absolute inset-0 animate-ping rounded-xl bg-indigo-400/20" aria-hidden="true" />
              <ScanLine size={20} className="animate-pulse" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                <p className="text-sm font-semibold text-navy-800 dark:text-gray-100">
                  מחלץ נתונים מ-{pending} {pending === 1 ? 'טופס' : 'טפסים'}…
                </p>
                {progress.size > 1 && (
                  <span className="text-xs tabular-nums text-gray-500 dark:text-gray-400">{progress.done}/{progress.size} הושלמו</span>
                )}
              </div>
              <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-indigo-100 dark:bg-indigo-950">
                <div
                  className="h-full rounded-full bg-gradient-to-l from-teal-500 via-indigo-500 to-teal-500 bg-[length:200%_100%] animate-progress-flow transition-[width] duration-700 ease-out"
                  style={{ width: `${Math.max(progress.percent, 8)}%` }}
                />
              </div>
            </div>
          </div>
        )
      )}

      {failed > 0 && (
        <button
          type="button"
          onClick={onShowFailed}
          className="card flex items-center gap-2 border border-red-200 px-4 py-3 text-sm font-medium text-red-700 transition hover:bg-red-50 dark:border-red-900 dark:text-red-300 dark:hover:bg-red-950/30"
        >
          <XCircle size={18} />
          {failed} {failed === 1 ? 'טופס נכשל' : 'טפסים נכשלו'} · הצג
        </button>
      )}
    </div>
  )
}
