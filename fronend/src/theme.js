// Central theme tokens – all components import from here, no hardcoded values elsewhere

export const colors = {
  // Backgrounds
  pageBg: 'bg-surface-page dark:bg-slate-950',
  footerBg: 'bg-surface-footer dark:bg-slate-900',
  cardBg: 'bg-white dark:bg-slate-900',

  // Text
  textPrimary: 'text-navy-800 dark:text-slate-100',
  textSecondary: 'text-navy-700 dark:text-slate-200',
  textMuted: 'text-gray-500 dark:text-slate-400',
  textFaint: 'text-gray-300 dark:text-slate-600',

  // Brand actions
  actionPrimary: 'bg-teal-600 hover:bg-teal-700 text-white dark:bg-teal-500 dark:hover:bg-teal-400',
  actionNavy: 'bg-navy-700 hover:bg-navy-800 text-white dark:bg-sky-700 dark:hover:bg-sky-600',

  // Status badges
  badgeApproved: 'text-teal-700 dark:text-teal-300 bg-teal-50 dark:bg-teal-950/60',
  badgePending: 'text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/60',

  // Uncertain field
  uncertainText: 'text-pink-700 dark:text-pink-300',
  uncertainBg: 'bg-pink-50 dark:bg-pink-950/25',
  uncertainBorder: 'border-pink-200 dark:border-pink-800',
  uncertainReason: 'bg-pink-50 dark:bg-pink-950/30 text-pink-700 dark:text-pink-300 border border-pink-200 dark:border-pink-800',
}

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