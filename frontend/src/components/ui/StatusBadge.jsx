import { AlertTriangle, CheckCircle2, Clock, GitCompareArrows, Loader2, ShieldCheck, XCircle } from 'lucide-react'
import { useMeta } from '../../meta/MetaContext'

// Visual style per status key; the Hebrew labels come from the backend (meta).
const STYLES = {
  uploaded: { icon: Clock, className: 'text-sky-700 bg-sky-50 dark:text-sky-300 dark:bg-sky-950/60' },
  processing: { icon: Loader2, spin: true, className: 'text-indigo-700 bg-indigo-50 dark:text-indigo-300 dark:bg-indigo-950/60' },
  extracted: { icon: AlertTriangle, className: 'text-amber-700 bg-amber-50 dark:text-amber-300 dark:bg-amber-950/60' },
  approved: { icon: CheckCircle2, className: 'text-teal-700 bg-teal-50 dark:text-teal-300 dark:bg-teal-950/60' },
  failed: { icon: XCircle, className: 'text-red-700 bg-red-50 dark:text-red-300 dark:bg-red-950/60' },
  verified: { icon: ShieldCheck, className: 'text-teal-700 bg-teal-50 dark:text-teal-300 dark:bg-teal-950/60' },
  confirmed: { icon: CheckCircle2, className: 'text-teal-700 bg-teal-50 dark:text-teal-300 dark:bg-teal-950/60' },
  conflict: { icon: GitCompareArrows, className: 'text-orange-800 bg-orange-100 ring-1 ring-orange-300 dark:text-orange-200 dark:bg-orange-950/60 dark:ring-orange-800' },
  unverified: { icon: AlertTriangle, className: 'text-pink-700 bg-pink-50 dark:text-pink-300 dark:bg-pink-950/60' },
  uncertain: { icon: AlertTriangle, className: 'text-pink-700 bg-pink-50 dark:text-pink-300 dark:bg-pink-950/60' },
  not_found: { icon: XCircle, className: 'text-gray-600 bg-gray-100 dark:text-gray-300 dark:bg-gray-800' },
}
const FALLBACK = { icon: Clock, className: 'text-gray-600 bg-gray-100 dark:text-gray-300 dark:bg-gray-800' }

/** kind: 'form' (form status) or 'field' (extracted-field status). */
export default function StatusBadge({ status, kind = 'form' }) {
  const meta = useMeta()
  const labels = kind === 'field' ? meta.field_statuses : meta.form_statuses
  const { icon: Icon, spin, className } = STYLES[status] ?? FALLBACK

  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold ${className}`}>
      <Icon size={12} className={spin ? 'animate-spin' : undefined} aria-hidden="true" />
      {labels[status] ?? status}
    </span>
  )
}
