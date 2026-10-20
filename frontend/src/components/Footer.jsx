const LINKS = ['מדיניות פרטיות', 'תנאי שימוש', 'תמיכה טכנית']

export default function Footer() {
  return (
    <footer className="flex-none border-t border-slate-200 bg-slate-50 px-4 py-2 dark:border-gray-800 dark:bg-slate-900 sm:px-8 sm:py-4" dir="rtl">
      <div className="flex flex-wrap items-center justify-between gap-x-8 gap-y-2">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <div className="hidden md:block">
            <p className="text-sm font-bold text-gray-600 dark:text-gray-300">אודות המערכת</p>
            <p className="mt-0.5 text-xs leading-relaxed text-gray-500 dark:text-gray-400">
              מערכת אימות טפסים רפואיים לחילוץ ואימות נתונים מטפסי התחייבות באמצעות OCR ובינה מלאכותית.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <img
              src="/logos/open-code.png"
              alt="קוד פתוח"
              className="h-5 object-contain opacity-70 sm:h-6"
              onError={(e) => { e.target.style.display = 'none' }}
            />
            <p className="text-xs text-gray-500 dark:text-gray-400">האקתון קוד פתוח – בשיתוף משרד הבריאות 2026</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-x-6 gap-y-1">
          {LINKS.map((label) => (
            <a key={label} href="#" className="hidden text-xs text-gray-500 transition-colors hover:text-teal-600 dark:text-gray-400 dark:hover:text-teal-400 sm:inline">
              {label}
            </a>
          ))}
          <p className="text-xs text-gray-400 dark:text-gray-500">© 2026 Sara Vaisbord</p>
        </div>
      </div>
    </footer>
  )
}
