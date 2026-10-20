import { Moon, Sun } from 'lucide-react'

export default function Header({ darkMode, onToggleDark }) {
  return (
    <header className="sticky top-0 z-40 border-b border-gray-200/80 dark:border-gray-800"
      style={{ background: 'rgba(255,255,255,0.95)', backdropFilter: 'blur(12px)' }}>
      <div className="flex h-16 w-full items-center justify-between gap-3 px-3 sm:h-20 sm:px-4">

        {/* Right: Brand + Logos */}
        <div className="flex min-w-0 items-center gap-4 lg:gap-6">

          {/* Primary: Virus Lab logo + title */}
          <div className="flex min-w-0 items-center gap-3 sm:gap-4">
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
                className="h-10 object-contain sm:h-12"
                onError={e => { e.target.style.display = 'none' }}
              />
            </a>
            <div className="min-w-0">
              <p className="hidden text-xs leading-tight text-gray-400 sm:block">מערכת אימות טפסים</p>
              <p className="truncate text-sm font-bold leading-tight text-navy-800 dark:text-gray-100 sm:text-base">
                המעבדה המרכזית לנגיפים
              </p>
            </div>
          </div>

          <div className="hidden h-10 w-px bg-gray-200 dark:bg-gray-700 lg:block" />

          {/* Secondary: MOH + Sheba (hidden on small screens) */}
          <div className="hidden items-center gap-5 lg:flex">
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
        <div className="flex flex-shrink-0 items-center gap-1 sm:gap-2">

          {/* Dark mode toggle */}
          <button
            type="button"
            onClick={onToggleDark}
            aria-label={darkMode ? 'החלף למצב בהיר' : 'החלף למצב כהה'}
            className="w-11 h-11 flex items-center justify-center rounded-xl text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400"
          >
            {darkMode ? <Sun size={20} /> : <Moon size={20} />}
          </button>
        </div>

      </div>
    </header>
  )
}