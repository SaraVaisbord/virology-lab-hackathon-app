import { Moon, Sun, ChevronDown } from 'lucide-react'

export default function Header({ darkMode, onToggleDark, onOpenProfile }) {
  return (
    <header className="sticky top-0 z-40 border-b border-gray-200/80 dark:border-gray-800"
      style={{ background: 'rgba(255,255,255,0.95)', backdropFilter: 'blur(12px)' }}>
      <div className="w-full px-4 h-20 flex items-center justify-between">

        {/* Right: Brand + Logos */}
        <div className="flex items-center gap-6">

          {/* Primary: Virus Lab logo + title */}
          <div className="flex items-center gap-4">
            <a
              href="#"
              target="_blank"
              rel="noopener noreferrer"
              title="המעבדה המרכזית לנגיפים"
              className="opacity-90 hover:opacity-100 transition-opacity duration-150"
            >
              <img
                src="/logos/virus-lab.png"
                alt="המעבדה המרכזית לנגיפים"
                className="h-12 object-contain"
                onError={e => { e.target.style.display = 'none' }}
              />
            </a>
            <div className="hidden sm:block">
              <p className="text-xs text-gray-400 leading-tight">מערכת אימות טפסים</p>
              <p className="text-base font-bold text-navy-800 dark:text-gray-100 leading-tight">
                המעבדה המרכזית לנגיפים
              </p>
            </div>
          </div>

          <div className="w-px h-10 bg-gray-200 dark:bg-gray-700" />

          {/* Secondary: MOH + Sheba */}
          <div className="flex items-center gap-5">
            <a
              href="https://www.gov.il/he/departments/ministry_of_health"
              target="_blank"
              rel="noopener noreferrer"
              title="משרד הבריאות"
              className="opacity-70 hover:opacity-100 transition-opacity duration-150"
            >
              <img
                src="/logos/moh.png"
                alt="משרד הבריאות"
                className="h-10 object-contain"
                onError={e => { e.target.style.display = 'none' }}
              />
            </a>

            <div className="w-px h-10 bg-gray-200 dark:bg-gray-700" />

            <a
              href="https://www.sheba.co.il"
              target="_blank"
              rel="noopener noreferrer"
              title="מרכז רפואי שיבא"
              className="opacity-70 hover:opacity-100 transition-opacity duration-150"
            >
              <img
                src="/logos/sheba.svg"
                alt="שיבא"
                className="h-9 object-contain"
                onError={e => { e.target.style.display = 'none' }}
              />
            </a>
          </div>
        </div>

        {/* Left: Actions */}
        <div className="flex items-center gap-2">

          {/* Dark mode toggle */}
          <button
            type="button"
            onClick={onToggleDark}
            aria-label={darkMode ? 'החלף למצב בהיר' : 'החלף למצב כהה'}
            className="w-11 h-11 flex items-center justify-center rounded-xl text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400"
          >
            {darkMode ? <Sun size={20} /> : <Moon size={20} />}
          </button>

          <div className="w-px h-7 bg-gray-200 dark:bg-gray-700 mx-1" />

          {/* User profile */}
          <button
            type="button"
            onClick={onOpenProfile}
            className="flex items-center gap-3 px-4 py-2 rounded-xl hover:bg-gray-100 dark:hover:bg-gray-800 transition-all group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400"
            aria-label="פתח פרופיל משתמש"
          >
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-navy-600 to-teal-500 flex items-center justify-center text-white text-sm font-bold shadow-sm">
              מ
            </div>
            <div className="hidden sm:block text-right">
              <p className="text-sm font-semibold text-gray-800 dark:text-gray-200 leading-tight">ד"ר מיכל לוי</p>
              <p className="text-xs text-gray-400 dark:text-gray-500 leading-tight">לבורנטית ראשית</p>
            </div>
            <ChevronDown size={16} className="text-gray-400 group-hover:text-gray-600 dark:group-hover:text-gray-300 transition-colors" />
          </button>
        </div>

      </div>
    </header>
  )
}