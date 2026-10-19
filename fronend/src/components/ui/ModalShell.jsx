import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'

// מחסנית מודאלים: רק העליון מגיב למקלדת
const modalStack = []

export default function ModalShell({ title, icon: Icon, onClose, children, footer, maxWidth = 'max-w-lg' }) {
  const modalRef = useRef(null)
  const lastFocusedRef = useRef(null)
  const onCloseRef = useRef(onClose)

  useEffect(() => {
    onCloseRef.current = onClose
  }, [onClose])

  useEffect(() => {
    const id = Symbol('modal')
    modalStack.push(id)
    const isTop = () => modalStack[modalStack.length - 1] === id

    lastFocusedRef.current = document.activeElement

    const focusableSelector = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'

    const handleKeyDown = (e) => {
      if (!isTop()) return

      if (e.key === 'Escape') {
        onCloseRef.current?.()
        return
      }

      if (e.key !== 'Tab' || !modalRef.current) return
      const focusableElements = Array.from(modalRef.current.querySelectorAll(focusableSelector)).filter((el) => !el.disabled)
      if (!focusableElements.length) {
        e.preventDefault()
        return
      }
      const first = focusableElements[0]
      const last = focusableElements[focusableElements.length - 1]

      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }

    window.addEventListener('keydown', handleKeyDown)

    const focusTimer = setTimeout(() => {
      if (!isTop()) return
      const focusable = modalRef.current?.querySelectorAll(focusableSelector)
      if (focusable && focusable.length > 0) focusable[0].focus()
    }, 50)

    return () => {
      clearTimeout(focusTimer)
      window.removeEventListener('keydown', handleKeyDown)
      const index = modalStack.indexOf(id)
      if (index !== -1) modalStack.splice(index, 1)
      lastFocusedRef.current?.focus?.()
    }
  }, [])

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-0 animate-fade-in dark:bg-black/60 sm:items-center sm:p-6"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        ref={modalRef}
        className={`flex max-h-[100dvh] w-full flex-col rounded-t-2xl bg-white shadow-2xl animate-slide-up dark:bg-gray-900 sm:max-h-[calc(100dvh-48px)] sm:rounded-2xl ${maxWidth}`}
        dir="rtl"
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-gray-100 px-4 py-4 dark:border-gray-800 sm:px-[30px] sm:py-5">
          <div className="flex min-w-0 items-center gap-2.5">
            {Icon && <Icon size={22} className="shrink-0 text-pink-500" />}
            <h2 dir="auto" className="truncate text-lg font-bold text-navy-800 dark:text-gray-100">{title}</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="btn-ghost p-2.5 text-gray-600"
            aria-label="סגור חלון"
          >
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4 sm:space-y-5 sm:px-[30px] sm:py-[26px]">{children}</div>

        {/* Footer */}
        {footer && (
          <div className="flex shrink-0 flex-wrap items-center justify-end gap-3 border-t border-gray-100 px-4 py-4 dark:border-gray-800 sm:gap-4 sm:px-[30px] sm:py-5">
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}