export default function Toggle({ enabled, onChange }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!enabled)}
      role="switch"
      aria-checked={enabled}
      aria-label={enabled ? 'כיבוי מצב' : 'הפעלת מצב'}
      className={`w-12 h-6 rounded-full transition-colors duration-200 relative flex-shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 ${enabled ? 'bg-teal-600 dark:bg-teal-500' : 'bg-gray-300 dark:bg-gray-600'}`}
    >
      <span className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform duration-200 ${enabled ? 'translate-x-1' : 'translate-x-6'}`} />
    </button>
  )
}
