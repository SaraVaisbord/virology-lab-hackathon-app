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