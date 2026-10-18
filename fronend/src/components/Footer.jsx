export default function Footer() {
  return (
    <footer
      className="flex-none bg-slate-50 border-t border-slate-200 dark:border-gray-800 dark:bg-slate-900 px-8 py-4"
      dir="rtl"
    >
      <div className="flex items-center justify-between gap-x-8 gap-y-3 flex-wrap">
        {/* אודות + לוגו */}
        <div className="flex items-center gap-x-6 gap-y-2 flex-wrap">
          <div>
            <p className="text-sm font-bold text-gray-600 dark:text-gray-300">אודות המערכת</p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 leading-relaxed">
              מערכת אימות טפסים רפואיים לחילוץ ואימות נתונים מטפסי התחייבות באמצעות OCR ובינה מלאכותית.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <img
              src="/logos/open-code.png"
              alt="קוד פתוח"
              className="h-6 object-contain opacity-70"
              onError={e => { e.target.style.display = 'none' }}
            />
            <p className="text-xs text-gray-500 dark:text-gray-400">
              האקתון קוד פתוח – בשיתוף משרד הבריאות 2026
            </p>
          </div>
        </div>

        {/* קישורים + זכויות יוצרים */}
        <div className="flex items-center gap-x-6 gap-y-2 flex-wrap">
          {['מדיניות פרטיות', 'תנאי שימוש', 'תמיכה טכנית'].map(label => (
            <a
              key={label}
              href="#"
              className="text-xs text-gray-500 dark:text-gray-400 hover:text-teal-600 dark:hover:text-teal-400 transition-colors"
              aria-label={label}
            >
              {label}
            </a>
          ))}
          <p className="text-xs text-gray-400 dark:text-gray-500">© 2026 Sara Vaisbord</p>
        </div>
      </div>
    </footer>
  )
}