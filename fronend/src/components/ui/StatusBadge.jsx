import { CheckCircle2, Clock } from 'lucide-react'
import { colors } from '../../theme'

const config = {
  approved: { label: 'אושר', icon: CheckCircle2, style: colors.badgeApproved },
  pending: { label: 'ממתין', icon: Clock, style: colors.badgePending },
  confirmed: { label: 'אושר', icon: CheckCircle2, style: colors.badgeApproved },
  edited: { label: 'תוקן', icon: Clock, style: 'text-pink-700 dark:text-pink-300 bg-pink-50 dark:bg-pink-950/60' },
}

export default function StatusBadge({ status }) {
  const { label, icon: Icon, style } = config[status] ?? config.pending
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1 rounded-full ${style}`}>
      <Icon size={11} /> {label}
    </span>
  )
}
