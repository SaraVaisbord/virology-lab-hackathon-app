/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        navy: {
          50:  '#eef4ff',
          100: '#dfeafc',
          500: '#2d5ea8',
          600: '#1e3a6e',
          700: '#162d57',
          800: '#0f2040',
          900: '#091827',
        },
        brand: {
          // Sky – כרטיסיית ממתינים + hover עיפרון
          sky:     '#0ea5e9',
          // Teal – כפתורים ראשיים, badge אושר, כרטיסיית דיוק
          teal:    '#14b8a6',
          // Amber – כרטיסיית לאימות, badge ממתין
          amber:   '#d97706',
          // Pink – שדות uncertain, סיבת ספק
          pink:    '#db2777',
        },
        // "Needs the lab worker's review" (uncertain / unverified / not-found fields) — the ONE place to change
        // this colour. Amber: matches the "awaiting review" form status, warm against navy/teal, not an error red.
        review: {
          50:  '#fffbeb',
          100: '#fef3c7',
          200: '#fde68a',
          300: '#fcd34d',
          400: '#fbbf24',
          500: '#f59e0b',
          600: '#d97706',
          700: '#b45309',
          800: '#92400e',
          900: '#78350f',
          950: '#451a03',
        },
        surface: {
          // רקע כללי
          page:   '#F4F7F6',
          // רקע פוטר
          footer: '#F0F4F3',
          // רקע כרטיסיות
          card:   '#FFFFFF',
        },
        teal: {
          400: '#2dd4bf',
          500: '#0f9d94',
          600: '#0d7c76',
          700: '#0c6d69',
        },
        amber: {
          400: '#fbbf24',
          500: '#d97706',
          600: '#b45309',
          700: '#92400e',
        },
        pink: {
          100: '#fdf2f8',
          200: '#fbcfe8',
          400: '#f472b6',
          500: '#ec4899',
          600: '#db2777',
          700: '#be185d',
        },
      },
      fontFamily: {
        sans: ['Heebo', 'Assistant', 'sans-serif'],
      },
      animation: {
        'fade-in':  'fadeIn 0.2s ease-out',
        'slide-up': 'slideUp 0.25s ease-out',
        'progress-flow': 'progressFlow 2s linear infinite',
        'shimmer': 'shimmer 1.6s ease-in-out infinite',
      },
      keyframes: {
        fadeIn:  { '0%': { opacity: '0' }, '100%': { opacity: '1' } },
        slideUp: { '0%': { opacity: '0', transform: 'translateY(16px)' }, '100%': { opacity: '1', transform: 'translateY(0)' } },
        progressFlow: { '0%': { backgroundPosition: '0% 0' }, '100%': { backgroundPosition: '200% 0' } },
        shimmer: { '0%, 100%': { opacity: '0.45' }, '50%': { opacity: '1' } },
      },
    },
  },
  plugins: [],
}
