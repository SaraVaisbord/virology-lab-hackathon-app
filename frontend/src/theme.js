// Correction insights by support (CorrectionInsightsDashboard): a pattern backed by enough events looks settled;
// a first suspicion is dashed and in the "needs review" colour, so it is never read as an established finding.
export const insightSupportStyles = {
  established: {
    card: 'border border-slate-200 border-s-4 border-s-teal-500 bg-white dark:border-slate-700 dark:border-s-teal-400 dark:bg-slate-900',
    badge: 'text-teal-700 bg-teal-50 dark:text-teal-300 dark:bg-teal-950/60',
  },
  suspicion: {
    card: 'border border-dashed border-review-400 bg-review-50/40 dark:border-review-700 dark:bg-review-950/20',
    badge: 'text-review-800 bg-review-100 dark:text-review-300 dark:bg-review-950/60',
  },
}
// Support levels shown as a first suspicion (the rest are established).
export const SUSPICION_SUPPORT_LEVELS = ['low']

// Visual variants for the stats cards (StatsCards.jsx)

export const cardVariants = {
  pending: {
    iconColor: 'text-sky-600 dark:text-sky-400',
    iconBg: 'bg-sky-50 dark:bg-sky-950/60',
    activeBorder: 'ring-2 ring-sky-400 dark:ring-sky-500',
    activeBg: 'bg-sky-50/70 dark:bg-sky-950/40',
  },
  accuracy: {
    iconColor: 'text-teal-600 dark:text-teal-400',
    iconBg: 'bg-teal-50 dark:bg-teal-950/50',
    activeBorder: '',
    activeBg: '',
  },
  uncertain: {
    iconColor: 'text-amber-600 dark:text-amber-400',
    iconBg: 'bg-amber-50/90 dark:bg-amber-950/50',
    activeBorder: 'ring-2 ring-amber-400 dark:ring-amber-500',
    activeBg: 'bg-amber-50/80 dark:bg-amber-950/30',
  },
  // ורוד – בהשראת הלוגו של שיבא
  senders: {
    iconColor: 'text-pink-500 dark:text-pink-400',
    iconBg: 'bg-pink-100/80 dark:bg-pink-950/50',
    numberColor: 'text-pink-600 dark:text-pink-300',
    ring: 'ring-pink-200 dark:ring-pink-900/60',
    activeBorder: '',
    activeBg: '',
  },
}